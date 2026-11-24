#!/usr/bin/env python3
"""notes_lint.py -- 备注质量门禁（备注是讲稿，不是页面文字的复读）。

逐页检查（任一 error => 退出码 1）：
  1. 每页必须有非空备注；
  2. 备注 vs 页面可见文字的 token Jaccard 相似度必须 ≤ --max-jaccard（默认 0.5）；
  3. 备注必须含过渡或强调标记（next/remember/if asked/接下来/注意/… 见 MARKERS）；
  4. 口播总时长（中文 --cpm 字/分钟、英文 --wpm 词/分钟）≤ 预算（--minutes）。

输出逐页表格 + notes_report.json。

用法：
    python3 notes_lint.py deck.pptx --minutes 10 --report notes_report.json
"""
import argparse
import json
import re
import sys

try:
    from pptx import Presentation
except ImportError:
    print(
        "ERROR: python-pptx is required for notes_lint.py (pip install python-pptx).",
        file=sys.stderr,
    )
    sys.exit(2)

CJK_RE = re.compile(r"[一-鿿]")
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*")

MARKERS = [
    # English transition / emphasis cues
    "next", "moving on", "turning to", "now let", "remember", "note that",
    "key point", "if asked", "if-asked", "in summary", "to wrap up",
    "finally", "first", "second", "third", "however", "transition",
    # 中文过渡/强调
    "接下来", "现在", "注意", "关键", "请记住", "如果被问", "总结", "最后",
    "首先", "其次", "然而", "过渡",
]


def tokens(text):
    words = [w.lower() for w in WORD_RE.findall(text)]
    cjk = CJK_RE.findall(text)
    bigrams = ["".join(pair) for pair in zip(cjk, cjk[1:])]
    return set(words) | set(bigrams)


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def spoken_seconds(text, cpm, wpm):
    cjk = len(CJK_RE.findall(text))
    words = len(WORD_RE.findall(CJK_RE.sub(" ", text)))
    return cjk / cpm * 60.0 + words / wpm * 60.0


def slide_visible_text(slide):
    parts = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            parts.append(shape.text_frame.text)
    return "\n".join(parts)


def slide_notes(slide):
    if not slide.has_notes_slide:
        return ""
    return slide.notes_slide.notes_text_frame.text.strip()


def lint(deck_path, minutes, cpm, wpm, max_jaccard):
    prs = Presentation(deck_path)
    rows, errors = [], []
    total_spoken = 0.0
    for i, slide in enumerate(prs.slides, start=1):
        notes = slide_notes(slide)
        visible = slide_visible_text(slide)
        jac = jaccard(tokens(notes), tokens(visible))
        has_marker = any(m in notes.lower() for m in MARKERS) if notes else False
        sec = spoken_seconds(notes, cpm, wpm)
        total_spoken += sec
        problems = []
        if not notes:
            problems.append("notes_missing")
        if notes and jac > max_jaccard:
            problems.append(f"jaccard {jac:.2f} > {max_jaccard}")
        if notes and not has_marker:
            problems.append("no_transition_or_emphasis_marker")
        for p in problems:
            errors.append(f"slide {i}: {p}")
        rows.append({
            "slide": i,
            "notes_chars": len(notes),
            "jaccard_notes_vs_slide": round(jac, 3),
            "has_marker": has_marker,
            "spoken_sec": round(sec, 1),
            "status": "error" if problems else "ok",
            "problems": problems,
        })
    budget = minutes * 60.0
    if total_spoken > budget:
        errors.append(
            f"total spoken {total_spoken:.0f}s exceeds budget {budget:.0f}s (minutes={minutes})"
        )
    return {
        "deck": deck_path,
        "minutes": minutes,
        "cpm": cpm,
        "wpm": wpm,
        "max_jaccard": max_jaccard,
        "n_slides": len(rows),
        "total_spoken_sec": round(total_spoken, 1),
        "budget_sec": budget,
        "slides": rows,
        "errors": errors,
        "pass": not errors,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Gate speaker-notes quality of a deck.")
    ap.add_argument("deck", help="deck.pptx path")
    ap.add_argument("--minutes", type=float, default=10.0, help="talk budget in minutes")
    ap.add_argument("--cpm", type=int, default=240, help="Chinese chars per minute")
    ap.add_argument("--wpm", type=int, default=150, help="English words per minute")
    ap.add_argument("--max-jaccard", type=float, default=0.5,
                    help="max Jaccard(notes, slide text); above => verbatim-repeat error")
    ap.add_argument("--report", required=True, help="notes_report.json path")
    args = ap.parse_args()
    try:
        report = lint(args.deck, args.minutes, args.cpm, args.wpm, args.max_jaccard)
    except Exception as e:
        print(f"ERROR: cannot lint deck: {e}", file=sys.stderr)
        return 2
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"{'slide':>5} {'chars':>6} {'jaccard':>8} {'marker':>7} {'sec':>6}  status")
    for r in report["slides"]:
        print(f"{r['slide']:>5} {r['notes_chars']:>6} {r['jaccard_notes_vs_slide']:>8.2f} "
              f"{str(r['has_marker']):>7} {r['spoken_sec']:>6.1f}  {r['status']}")
    if report["errors"]:
        for e in report["errors"]:
            print(f"ERROR: {e}", file=sys.stderr)
        print(f"notes_lint: FAIL ({len(report['errors'])} errors) -> {args.report}",
              file=sys.stderr)
        return 1
    print(
        f"notes_lint: PASS slides={report['n_slides']} "
        f"spoken={report['total_spoken_sec']:.0f}s/{report['budget_sec']:.0f}s -> {args.report}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
