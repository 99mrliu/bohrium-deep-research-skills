#!/usr/bin/env python3
"""rehearse.py -- 彩排计时：按语速从备注估算逐页口播秒数。

产出：逐页口播秒数、累计时长、超速页清单（>1.5×均摊时长）、过薄页（<15 秒）警告。
仅警告不阻断（退出码恒 0，除非文件不可读 => 2）。

用法：
    python3 rehearse.py deck.pptx --cpm 240 --wpm 150 --report rehearsal.json
    python3 rehearse.py deck.pptx --minutes 10 --report rehearsal.json
"""
import argparse
import json
import re
import sys

try:
    from pptx import Presentation
except ImportError:
    print(
        "ERROR: python-pptx is required for rehearse.py (pip install python-pptx).",
        file=sys.stderr,
    )
    sys.exit(2)

CJK_RE = re.compile(r"[一-鿿]")
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*")

THIN_SEC = 15.0
OVERSPEED_FACTOR = 1.5


def spoken_seconds(text, cpm, wpm):
    cjk = len(CJK_RE.findall(text))
    words = len(WORD_RE.findall(CJK_RE.sub(" ", text)))
    return cjk / cpm * 60.0 + words / wpm * 60.0


def main() -> int:
    ap = argparse.ArgumentParser(description="Rehearse timing from speaker notes.")
    ap.add_argument("deck", help="deck.pptx path")
    ap.add_argument("--cpm", type=int, default=240, help="Chinese chars per minute")
    ap.add_argument("--wpm", type=int, default=150, help="English words per minute")
    ap.add_argument("--minutes", type=float, default=10.0, help="talk budget in minutes")
    ap.add_argument("--report", required=True, help="rehearsal.json path")
    args = ap.parse_args()
    try:
        prs = Presentation(args.deck)
    except Exception as e:
        print(f"ERROR: cannot open deck: {e}", file=sys.stderr)
        return 2

    n = len(prs.slides)
    allotment = args.minutes * 60.0 / n if n else 0.0
    rows, over_speed, thin = [], [], []
    cumulative = 0.0
    for i, slide in enumerate(prs.slides, start=1):
        notes = ""
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()
        sec = spoken_seconds(notes, args.cpm, args.wpm)
        cumulative += sec
        row = {
            "slide": i,
            "spoken_sec": round(sec, 1),
            "cumulative_sec": round(cumulative, 1),
            "allotment_sec": round(allotment, 1),
            "flags": [],
        }
        if sec > OVERSPEED_FACTOR * allotment:
            row["flags"].append("over_speed")
            over_speed.append(i)
        if sec < THIN_SEC:
            row["flags"].append("thin")
            thin.append(i)
        rows.append(row)

    report = {
        "deck": args.deck,
        "cpm": args.cpm,
        "wpm": args.wpm,
        "minutes": args.minutes,
        "n_slides": n,
        "total_spoken_sec": round(cumulative, 1),
        "within_budget": cumulative <= args.minutes * 60.0,
        "per_slide": rows,
        "over_speed_slides": over_speed,
        "thin_slides": thin,
        "warnings": (
            [f"slide {s}: over speed (>1.5x allotment)" for s in over_speed]
            + [f"slide {s}: thin (<{THIN_SEC:.0f}s of notes)" for s in thin]
        ),
    }
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    for w in report["warnings"]:
        print(f"WARN: {w}", file=sys.stderr)
    print(
        f"rehearse: slides={n} total={report['total_spoken_sec']:.0f}s/"
        f"{args.minutes*60:.0f}s over_speed={over_speed or '-'} thin={thin or '-'} "
        f"-> {args.report}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
