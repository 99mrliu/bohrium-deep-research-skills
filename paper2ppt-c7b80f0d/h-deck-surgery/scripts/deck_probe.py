#!/usr/bin/env python3
"""deck_probe.py — 手术前先诊断：解析起始稿/模板 pptx，输出 probe_report.json。

用法:
    python3 deck_probe.py <deck.pptx> --report probe_report.json

报告内容：引擎、页数、每页版式/占位符/标题/正文预览/备注有无/文本哈希、主题字体与主题哈希。
逐页 text_hash 是后续 surgery_lint「未涉及页哈希不变」校验的基线。
"""
from __future__ import annotations

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import deck_common as dc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="诊断 pptx：版式、占位符、逐页文本哈希、主题字体，输出 probe_report.json"
    )
    ap.add_argument("deck", help="起始稿或模板 pptx 路径")
    ap.add_argument("--report", required=True, help="输出 probe_report.json 路径")
    args = ap.parse_args(argv)

    try:
        info = dc.load_deck(args.deck)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # 损坏文件等
        print(f"error: cannot parse deck {args.deck}: {e}", file=sys.stderr)
        return 2

    report = {
        "deck": info["path"],
        "engine": info["engine"],
        "slide_count": info["slide_count"],
        "theme": info["theme"],
        "slides": [
            {
                "index": s["index"],
                "layout": s["layout"],
                "title": s["title"],
                "title_preview": s["title"][:120],
                "body_preview": " | ".join(s["body_texts"])[:200],
                "n_body_shapes": len(s["body_texts"]),
                "n_pictures": s["n_pictures"],
                "notes_present": bool(s["notes"].strip()),
                "placeholders": s["placeholders"],
                "text_hash": s["text_hash"],
                "full_hash": s["full_hash"],
            }
            for s in info["slides"]
        ],
    }
    dc.dump_json(report, args.report)
    print(
        f"probe ok: {args.deck} -> {args.report} "
        f"(engine={info['engine']}, slides={info['slide_count']}, "
        f"theme_sha1={info['theme'].get('sha1')})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
