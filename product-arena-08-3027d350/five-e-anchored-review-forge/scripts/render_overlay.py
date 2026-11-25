#!/usr/bin/env python3
"""render_overlay.py — blocks.jsonl + page_meta.json -> overlays/page-N.svg。

每页一张纯文本 SVG：页面矩形 + 每块着色矩形（kind -> 颜色表）+
锚点 id 小字标签；<title> 元素放块文本前 80 字符（XML 转义）。
尺寸按页点 1:1，viewBox 正确；坐标左上原点 y 向下，与 bbox 同系，不做变换。
SVG 构建逻辑在 svg_common.py，与 review.html 内嵌 SVG 同源。

退出码：0=成功，2=部分（有块被跳过或块越界），3=失败。
"""

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import svg_common  # noqa: E402

EXIT_OK, EXIT_PARTIAL, EXIT_FAIL = 0, 2, 3


def load_blocks(path):
    blocks = []
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            for key in ("id", "page", "kind", "bbox"):
                if key not in rec:
                    raise ValueError(f"blocks.jsonl 第 {ln} 行缺字段 {key}")
            if len(rec["bbox"]) != 4:
                raise ValueError(f"blocks.jsonl 第 {ln} 行 bbox 长度 != 4")
            blocks.append(rec)
    return blocks


def main():
    ap = argparse.ArgumentParser(description="渲染逐页锚点叠加 SVG")
    ap.add_argument("--blocks", required=True)
    ap.add_argument("--page-meta", required=True)
    ap.add_argument("--out-dir", required=True, help="产物根目录，SVG 写入其 overlays/ 子目录")
    args = ap.parse_args()

    report = {"script": "render_overlay.py", "warnings": [], "status": "failed",
              "pages_rendered": 0, "blocks_placed": 0, "blocks_skipped": 0,
              "outputs": []}
    overlays_dir = os.path.join(args.out_dir, "overlays")
    os.makedirs(overlays_dir, exist_ok=True)

    try:
        blocks = load_blocks(args.blocks)
        with open(args.page_meta, encoding="utf-8") as f:
            meta = json.load(f)
        pages = meta["pages"]
    except Exception as e:  # noqa: BLE001
        report["warnings"].append(f"输入读取失败: {type(e).__name__}: {e}"[:300])
        return finish(report, args.out_dir, EXIT_FAIL)

    page_map = {int(p["page"]): p for p in pages}
    by_page = {}
    skipped = 0
    for b in blocks:
        pno = int(b["page"])
        if pno not in page_map:
            report["warnings"].append(f"块 {b['id']} 指向不存在的页 {pno}，跳过")
            skipped += 1
            continue
        by_page.setdefault(pno, []).append(b)

    out_of_range = 0
    for p in pages:
        pno = int(p["page"])
        w, h = float(p["width"]), float(p["height"])
        placed = []
        for b in by_page.get(pno, []):
            x0, y0, x1, y1 = (float(v) for v in b["bbox"])
            if x0 < 0 or y0 < 0 or x1 > w + 0.5 or y1 > h + 0.5 or x1 <= x0 or y1 <= y0:
                report["warnings"].append(
                    f"块 {b['id']} bbox {b['bbox']} 越出页 {pno} ({w}x{h}) 或退化，仍渲染")
                out_of_range += 1
            placed.append(b)
        svg = svg_common.build_page_svg(w, h, placed)
        try:
            ET.fromstring(svg)  # 良构自检，失败即 3
        except ET.ParseError as e:
            report["warnings"].append(f"page-{pno}.svg 良构自检失败: {e}")
            return finish(report, args.out_dir, EXIT_FAIL)
        out = os.path.join(overlays_dir, f"page-{pno}.svg")
        with open(out, "w", encoding="utf-8") as f:
            f.write(svg)
        report["outputs"].append(out)
        report["pages_rendered"] += 1
        report["blocks_placed"] += len(placed)

    report["blocks_skipped"] = skipped
    if report["warnings"]:
        report["status"] = "partial"
        return finish(report, args.out_dir, EXIT_PARTIAL)
    report["status"] = "success"
    return finish(report, args.out_dir, EXIT_OK)


def finish(report, out_dir, code):
    report["exit_code"] = code
    path = os.path.join(out_dir, "overlay.report.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps(report, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
