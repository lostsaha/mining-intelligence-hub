r"""Recoverit 恢复文件归位：EPUB 中文翻译成果 → E:\\syn 原书目录。

规则（用户 2026-10-04）：
- 放回原 e:\\syn 原书目录；不替换已有文件（保住唯一可用版本）
- 多版本并存，文件名带恢复标记，用户按日期判断最新
- 损坏 epub 尝试修复（local file header 重建）；修不好的保留原件待人工
- 不入库、不动 H 盘（后期再入库）
用法：python recoverit_restore_epubs.py [--dry]
"""
import re
import shutil
import struct
import sys
import zipfile
from pathlib import Path

import xml.etree.ElementTree as ET

REC = Path(r"H:\Recoverit 2026-10-04 at 10.16.26\Local Disk (E)")
SYN = Path(r"E:\syn")
STAGE = SYN / "_恢复损坏待修"  # 修复失败件停放区

# 关键词 → 原书目录（按特异性排序，先匹配先得）
MAP = [
    (r"岩石边坡工程|Rock Slope Engineering", "Rock Slope Engineering"),
    (r"SME露天采矿|SME Surface|translated_chapters|Chapter\s*\d+_.*运输|编辑简介|塑造未来", "SME Surface Mining Handbook (Peter Darling) (Z-Library)"),
    (r"露天矿爆破原理|爆破原理", "Blasting principles for open pit mining"),
    (r"岩石爆破|Rock Blasting", "Rock Blasting A Practical Treatise on the Means Employed in Blasting Rocks for Industrial Purposes"),
    (r"Slope_Stability|边坡稳定|SLOPESTABILITY", "Slope stability in surface mining"),
    (r"经济评价|Economic_Eval|Economic Evaluation", "Economic Evaluation and Investment Decision Methods"),
    (r"估值手册|Valuation Handbook", "The Mining Valuation Handbook 4th Edition Mining And Energy Valuation For Investors And Management"),
    (r"运输道路|HaulRoad|Haul Road", "HaulRoadDesign"),
    (r"废石场|排土场|waste.?dump", "Guidelines for mine waste dump and stockpile design"),
    (r"水评估|Water in Pit", "Guidelines for Evaluating Water in Pit Slope Stability"),
    (r"露天矿规划与设计|Open Pit Mine Planning|OPMD|Pit.?limits|Pit_Limits", "Open Pit Mine Planning and Design"),
    (r"采矿工程原理|Principles_and_Practice|Principles and Practice", "Principles and Practice in Mining Engineering.pdf"),
    (r"SME采矿工程手册|SME Mining Engineering", "SME Mining Engineering Handbook Third Edition"),
    (r"矿物资源估算|Mineral Resource|资源估算", "Mineral Resource Estimation (Mario E. Rossi, Clayton V. Deutsch (auth.))"),
    (r"硬岩采矿手册|Hard Rock", "Hard Rock Miner's Handbook Edition"),
    (r"数据分析在矿业|Data Analytics", "Data Analytics Applied to the Mining Industry"),
    (r"矿业项目管理|Project Management for Mining", "Project management for mining handbook for delivering project success"),
    (r"采矿经济学|Mining Economics", "Mining Economics and Strategy"),
    (r"Weak Rocks|软岩", "Guidelines for Open Pit Slope Design in Weak Rocks"),
    (r"性能监测|Slope Performance", "Guidelines for Slope Performance Monitoring"),
    (r"Open Pit Slope Design|边坡工程设计", "Guidelines for Open Pit Slope Design"),
    (r"矿山运输道路", "HaulRoadDesign"),
]


def epub_title(p: Path) -> str:
    try:
        with zipfile.ZipFile(p) as z:
            c = z.read("META-INF/container.xml").decode("utf-8", "ignore")
            opf = re.search(r'full-path="([^"]+)"', c).group(1)
            root = ET.fromstring(re.sub(r'xmlns="[^"]+"', "", z.read(opf).decode("utf-8", "ignore"), count=1))
            for el in root.iter():
                if el.tag.split("}")[-1] == "title":
                    return (el.text or "").strip()
    except Exception:
        pass
    return ""


def epub_ok(p: Path) -> bool:
    try:
        with zipfile.ZipFile(p) as z:
            if z.testzip() is not None:
                return False
            z.read("META-INF/container.xml")
        return True
    except Exception:
        return False


def rebuild_epub(p: Path, out: Path) -> bool:
    """central directory 损坏但 local header 完好时，逐条目切割重建。"""
    data = p.read_bytes()
    entries = []
    pos = 0
    while True:
        pos = data.find(b"PK\x03\x04", pos)
        if pos < 0:
            break
        try:
            (sig, ver, flag, comp, _, crc, csize, usize, nlen, elen) = struct.unpack_from(
                "<IHHHHHIIIH", data, pos)
            name = data[pos + 30: pos + 30 + nlen].decode("utf-8", "ignore")
            hsize = 30 + nlen + elen
            if csize > 0:
                body = data[pos + hsize: pos + hsize + csize]
            else:  # 数据描述符模式：找下一个 local header/central 签名
                nxt = min((x for x in (data.find(b"PK\x03\x04", pos + hsize),
                                       data.find(b"PK\x01\x02", pos + hsize)) if x > 0), default=-1)
                if nxt < 0:
                    nxt = len(data)
                body = data[pos + hsize: nxt]
                csize = len(body)
            if not name or (csize and len(body) < csize):
                pos += 4
                continue
            entries.append((name, comp, body))
            pos += hsize + csize
        except Exception:
            pos += 4
    if len(entries) < 4:
        return False
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zo:
        written = set()
        for name, comp, body in entries:
            if name in written or name.endswith("/"):
                continue
            written.add(name)
            try:
                if comp == 0:
                    zo.writestr(name, body)
                else:
                    zo.writestr(name, __import__("zlib").decompress(body, -15))
            except Exception:
                continue
    return epub_ok(out)


def target_dir_for(path: Path, title: str) -> tuple[Path, bool]:
    """→ (目标目录, 是否目录内子路径)。按恢复文件的原相对路径保留层级。"""
    hay = f"{path.relative_to(REC)}|{path.name}|{title}"
    for pat, dirname in MAP:
        if re.search(pat, hay, re.I):
            sub = ""
            if "translated_chapters" in str(path):
                sub = "translated_chapters"
            return SYN / dirname / sub, True
    return None, False


def is_padding(p: Path) -> bool:
    """Recoverit 未找回数据时的填充件：头部呈短周期重复模式。"""
    head = p.read_bytes()[:256]
    if len(head) < 64:
        return False
    for w in (2, 4, 8, 16):
        if head[:w] * (len(head) // w) == head[: len(head) // w * w]:
            return True
    return False


def main() -> int:
    dry = "--dry" in sys.argv
    epubs = sorted(REC.rglob("*.epub"))
    print(f"恢复区 epub 共 {len(epubs)}")
    STAGE.mkdir(parents=True, exist_ok=True)

    placed = {}
    ok = pad = broken = broken_unfixed = 0
    for p in epubs:
        if p.name.endswith("_fixed.epub"):
            continue
        healthy = epub_ok(p)
        padded = not healthy and is_padding(p)
        if healthy:
            ok += 1
        elif padded:
            pad += 1
        else:
            broken += 1
        title = epub_title(p)
        tgt, matched = target_dir_for(p, title)
        if not matched:
            tgt = SYN / "_恢复_未识别书目"
        good = p
        if not healthy and not padded:
            fixed = p.with_name(p.stem + "_fixed.epub")
            fixed.unlink(missing_ok=True)
            try:
                if rebuild_epub(p, fixed):
                    good = fixed
                    healthy = True
            except Exception:
                pass
            if not healthy:
                broken_unfixed += 1
                tgt = STAGE if matched else tgt  # 修不好的进待修区（保留原破坏件）
        if padded:  # 填充垃圾件：数据未找回，留档待更好工具
            tgt = STAGE / "填充件_数据未找回"
        rel_dir = p.relative_to(REC).parent
        dst = tgt / good.name
        if dst.exists() and dst.stat().st_size == good.stat().st_size:
            good.unlink(missing_ok=True) if good != p else None
            continue
        if dst.exists():
            stem, suf = dst.stem, dst.suffix
            dst = tgt / f"{stem}_恢复{p.stat().st_size // 1024}KB{suf}"
            if dst.exists():
                good.unlink(missing_ok=True) if good != p else None
                continue
        placed.setdefault(str(tgt), []).append(good.name)
        if not dry:
            tgt.mkdir(parents=True, exist_ok=True)
            shutil.copy2(good, dst)
            if good != p:
                good.unlink(missing_ok=True)
    print(f"完好 {ok}，填充垃圾（数据未找回）{pad}，结构损坏 {broken}（其中修复失败 {broken_unfixed} 进待修区）")
    print(f"\n归位 {sum(len(v) for v in placed.values())} 个，分布：")
    for d, names in sorted(placed.items()):
        print(f"  {d.replace(str(SYN), 'E:/syn')}: {len(names)} 个")
        for n in names[:4]:
            print(f"     {n[:70]}")
        if len(names) > 4:
            print(f"     ... 共 {len(names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
