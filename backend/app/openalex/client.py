"""OpenAlex 学术数据客户端。

- 免费无 Key；配置 OPENALEX_EMAIL 进入 polite pool（更高速率限制）
- cursor 分页（PDF 记录 §7：不要用 page=1,2,3 无限翻）
- abstract_inverted_index → 重建摘要（PDF 记录 §22）
"""
from __future__ import annotations

import os
import time
from typing import Any, Iterator

import httpx

BASE_URL = "https://api.openalex.org"
PER_PAGE = 200
TIMEOUT = 30.0

EMAIL = os.getenv("OPENALEX_EMAIL", "").strip()

WORKS_SELECT = (
    "id,doi,title,publication_year,publication_date,cited_by_count,type,"
    "authorships,primary_location,referenced_works,abstract_inverted_index"
)
AUTHORS_SELECT = (
    "id,orcid,display_name,display_name_alternatives,"
    "last_known_institutions,affiliations,works_count,cited_by_count,summary_stats"
)


def _params(extra: dict) -> dict:
    params = dict(extra)
    params.setdefault("per-page", PER_PAGE)
    params.setdefault("select", WORKS_SELECT)
    if EMAIL:
        params.setdefault("mailto", EMAIL)
    return params


def reconstruct_abstract(inverted: dict | None) -> str:
    """OpenAlex 的 abstract 是 {词: [位置]} 倒排索引，需重建为文本。"""
    if not inverted:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)


class BudgetExhausted(RuntimeError):
    """OpenAlex 免费/匿名信用点当日预算耗尽（每 IP 共享，每日重置）。"""


class OpenAlexClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("OPENALEX_API_KEY", "").strip()
        self._client = httpx.Client(timeout=TIMEOUT)
        self.request_count = 0
        self.credits_remaining: int | None = None

    def get(self, endpoint: str, params: dict | None = None) -> dict:
        if self.credits_remaining is not None and self.credits_remaining < 12:
            raise BudgetExhausted(
                f"剩余信用点不足（{self.credits_remaining}），已停止采集以保留配额"
            )
        params = _params(params or {})
        if self.api_key:
            params["api_key"] = self.api_key
        last_error: Exception | None = None
        for attempt in range(3):  # 限流退避重试
            resp = self._client.get(f"{BASE_URL}{endpoint}", params=params)
            self.request_count += 1
            remaining = resp.headers.get("x-ratelimit-remaining")
            if remaining is not None:
                try:
                    self.credits_remaining = int(remaining)
                except ValueError:
                    pass
            if resp.status_code == 429:
                # 预算耗尽时不要空转重试，直接抛出让上层优雅收尾
                raise BudgetExhausted(
                    f"429: {resp.json().get('message', 'rate limited')[:160]}"
                    if resp.headers.get("content-type", "").startswith("application/json")
                    else "429 rate limited"
                )
            if resp.status_code in (500, 502, 503):
                time.sleep(1.5 * (attempt + 1))
                last_error = RuntimeError(f"HTTP {resp.status_code}")
                continue
            resp.raise_for_status()
            return resp.json()
        raise last_error or RuntimeError("request failed")

    def works_search(
        self,
        query: str,
        from_year: int = 2019,
        max_records: int = 200,
        sort: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> Iterator[dict]:
        """按查询词取作品，cursor 分页，只往 max_records 条。

        sort=None（默认相关性排序）；"publication_date:desc" 用于补采最新论文，
        消除相关度排序语料对近期窗口的偏差；from_date/to_date 支持对称窗口补采。
        """
        cursor = "*"
        collected = 0
        fdate = from_date or f"{from_year}-01-01"
        filters = [f"from_publication_date:{fdate}"]
        if to_date:
            filters.append(f"to_publication_date:{to_date}")
        base = {
            "search": query,
            "filter": ",".join(filters),
            "select": WORKS_SELECT,
        }
        if sort:
            base["sort"] = sort
        while cursor and collected < max_records:
            data = self.get("/works", {**base, "cursor": cursor})
            for work in data.get("results", []):
                yield work
                collected += 1
                if collected >= max_records:
                    break
            cursor = (data.get("meta") or {}).get("next_cursor")
            time.sleep(0.12)  # polite pool 限速

    def authors_batch(self, openalex_ids: list[str]) -> list[dict]:
        """按 ids.openalex 批量取作者实体，每批最多 25 个（管道符过滤上限）。"""
        results: list[dict] = []
        clean = [i.rsplit("/", 1)[-1] for i in openalex_ids]
        for i in range(0, len(clean), 25):
            chunk = clean[i : i + 25]
            data = self.get(
                "/authors",
                {
                    "filter": f"ids.openalex:{'|'.join(chunk)}",
                    "select": AUTHORS_SELECT,
                    "per-page": 200,
                },
            )
            results.extend(data.get("results", []))
            time.sleep(0.12)
        return results

    def close(self) -> None:
        self._client.close()
