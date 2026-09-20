"""专家发现管线入口。

    python -m app.experts.run            # 完整：作品采集 → 专家构建
    python -m app.experts.run --build    # 只重建（使用已采集语料）
"""
from __future__ import annotations

import sys

from . import build_experts, collect_works


def main() -> None:
    if "--build" in sys.argv:
        result = build_experts.build()
        print(f"build done: {result}")
        return
    collect_result = collect_works.collect()
    print(f"collect done: {collect_result}")
    build_result = build_experts.build()
    print(f"build done: {build_result}")


if __name__ == "__main__":
    main()
