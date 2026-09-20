"""RSS/Atom 采集器：抓取白名单信源 → 归一化 → 去重 → 以 pending 状态入库。

用法：
    python -m app.collect.run          # 采集全部激活信源
    python -m app.collect.run --slug mining-com   # 只采集指定信源
"""
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import httpx

from .. import config, db
from html import unescape

# 部分 WordPress/Cloudflare 站点会拦截非浏览器 UA 的 RSS 请求，使用标准浏览器 UA
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
FETCH_TIMEOUT = 25.0

# URL 归一化时剔除的跟踪参数
STRIP_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "fbclid", "gclid", "ocid", "at_medium", "at_campaign",
}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if k not in STRIP_PARAMS]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(query), ""))


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_aggregator_title(title: str) -> str:
    """Google News 标题形如 '正文标题 - 来源名'，去掉尾部来源段。"""
    parts = title.rsplit(" - ", 1)
    return parts[0].strip() if len(parts) == 2 and parts[1] else title


def entry_published(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                from calendar import timegm
                return datetime.fromtimestamp(timegm(parsed), tz=timezone.utc)
            except Exception:
                continue
    return None


def fetch_feed(feed_url: str) -> list[dict]:
    resp = httpx.get(
        feed_url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"},
        timeout=FETCH_TIMEOUT,
        follow_redirects=True,
    )
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"feed parse error: {parsed.bozo_exception}")
    return parsed.entries


def entry_to_item(source: dict, entry: dict) -> dict | None:
    link = (entry.get("link") or "").strip()
    title = strip_html(entry.get("title") or "")
    if "news.google.com" in (source.get("feed_url") or ""):
        title = clean_aggregator_title(title)
    if not link or not title:
        return None
    link = normalize_url(link)
    summary = strip_html(entry.get("summary") or entry.get("description") or "")[:2000]
    return {
        "source_id": source["source_id"],
        "url": link,
        "title": title[:500],
        "author": strip_html(entry.get("author") or "")[:200] or None,
        "summary_raw": summary or None,
        "published_at": entry_published(entry),
        "lang": source["lang"],
    }


def collect_source(source: dict, max_items: int) -> int:
    if not source["feed_url"]:
        return 0
    entries = fetch_feed(source["feed_url"])
    inserted = 0
    for entry in entries[:max_items]:
        item = entry_to_item(source, entry)
        if item is None:
            continue
        exists = db.query_one(
            "SELECT 1 FROM mining.items WHERE url = %s", (item["url"],)
        )
        if exists:
            continue
        db.execute(
            """
            INSERT INTO mining.items
                (source_id, url, title, author, summary_raw, published_at, lang, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
            ON CONFLICT (url) DO NOTHING
            """,
            (
                item["source_id"], item["url"], item["title"], item["author"],
                item["summary_raw"], item["published_at"], item["lang"],
            ),
        )
        inserted += 1
    db.execute(
        "UPDATE mining.sources SET last_fetched_at = now() WHERE source_id = %s",
        (source["source_id"],),
    )
    return inserted


def run_collect(slug: str | None = None) -> dict:
    """执行一轮采集，返回运行摘要。"""
    run = db.query_one(
        "INSERT INTO mining.collect_runs DEFAULT VALUES RETURNING run_id, started_at"
    )
    where = "AND slug = %s" if slug else ""
    params = (slug,) if slug else ()
    sources = db.query(
        f"""
        SELECT source_id, slug, name, feed_url, lang
        FROM mining.sources
        WHERE active AND feed_url IS NOT NULL {where}
        ORDER BY source_id
        """,
        params,
    )

    detail, ok, failed, total_new = [], 0, 0, 0
    for source in sources:
        t0 = time.monotonic()
        try:
            new = collect_source(source, config.COLLECT_MAX_PER_SOURCE)
            ok += 1
            total_new += new
            detail.append({"slug": source["slug"], "ok": True, "new": new,
                           "seconds": round(time.monotonic() - t0, 1)})
            print(f"[ok] {source['slug']}: +{new}")
        except Exception as exc:  # 单源失败不影响整体
            failed += 1
            detail.append({"slug": source["slug"], "ok": False,
                           "error": str(exc)[:300]})
            print(f"[fail] {source['slug']}: {exc}")

    db.execute(
        """
        UPDATE mining.collect_runs
        SET finished_at = now(), sources_ok = %s, sources_failed = %s,
            items_new = %s, detail = %s
        WHERE run_id = %s
        """,
        (ok, failed, total_new, json.dumps(detail, ensure_ascii=False), run["run_id"]),
    )
    print(f"done: {ok} ok / {failed} failed / {total_new} new items")
    return {"run_id": run["run_id"], "sources_ok": ok, "sources_failed": failed,
            "items_new": total_new, "detail": detail}


if __name__ == "__main__":
    target = None
    if "--slug" in sys.argv:
        target = sys.argv[sys.argv.index("--slug") + 1]
    run_collect(target)
