#!/usr/bin/env python3
"""beat_cut.py -- 校验逐拍讲稿 beats.json 是否满足时长/证据/结构契约。

校验项（error 触发退出码 1，warning 不阻断）：
  * 每拍必填字段：claim / beat_text / evidence_refs / transition / est_sec；
  * evidence_refs 引用必须存在于 evidence.json（fig:/tab:/anchor:/page: 前缀）；
  * 过渡句 transition 非空；
  * 拍数 ≤ 页数上限（--max-slides）；
  * 时长合计 ≤ 预算 ±10%（预算 = --minutes × 60 秒）；
  * est_sec 与 beat_text 口播估算偏差 >30% 时给 warning（CPM 240 / WPM 150）。

用法：
    python3 beat_cut.py beats.json --evidence evidence.json \
        --minutes 10 --max-slides 8 --report beat_report.json
"""
import argparse
import json
import re
import sys

CJK_RE = re.compile(r"[一-鿿]")
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*")

REQUIRED_FIELDS = ["claim", "beat_text", "evidence_refs", "transition", "est_sec"]


def spoken_seconds(text, cpm=240, wpm=150):
    cjk = len(CJK_RE.findall(text))
    words = len(WORD_RE.findall(CJK_RE.sub(" ", text)))
    return cjk / cpm * 60.0 + words / wpm * 60.0


def load_evidence_index(evidence):
    figs = {f["ref"] for f in evidence.get("figures", [])}
    tabs = {t["ref"] for t in evidence.get("tables", [])}
    anchors = {a["id"] for a in evidence.get("anchors", [])}
    pages = set(range(1, evidence.get("page_count", 0) + 1))
    return figs, tabs, anchors, pages


def check_ref(ref, figs, tabs, anchors, pages):
    if ":" not in ref:
        return False, f"ref '{ref}' lacks kind prefix (fig:/tab:/anchor:/page:)"
    kind, _, key = ref.partition(":")
    if kind == "fig":
        return (key in figs), f"figure '{key}' not in evidence.json"
    if kind == "tab":
        return (key in tabs), f"table '{key}' not in evidence.json"
    if kind == "anchor":
        try:
            ok = int(key) in anchors
        except ValueError:
            ok = False
        return ok, f"anchor id '{key}' not in evidence.json"
    if kind == "page":
        try:
            ok = int(key) in pages
        except ValueError:
            ok = False
        return ok, f"page '{key}' out of range"
    return False, f"unknown ref kind '{kind}'"


def validate(beats_path, evidence, minutes, max_slides):
    errors, warnings = [], []
    with open(beats_path, encoding="utf-8") as f:
        data = json.load(f)
    beats = data.get("beats") if isinstance(data, dict) else data
    if not isinstance(beats, list) or not beats:
        return None, ["beats.json has no 'beats' list or it is empty"], warnings

    figs, tabs, anchors, pages = load_evidence_index(evidence)
    per_beat = []
    total_est = 0.0
    for i, beat in enumerate(beats):
        bid = beat.get("id", f"beat-{i}")
        for field in REQUIRED_FIELDS:
            if field not in beat or beat[field] in (None, "", []):
                errors.append(f"beat[{i}] ({bid}): missing/empty field '{field}'")
        if not isinstance(beat.get("est_sec"), (int, float)) or beat.get("est_sec", 0) <= 0:
            errors.append(f"beat[{i}] ({bid}): est_sec must be a positive number")
            est = 0.0
        else:
            est = float(beat["est_sec"])
        total_est += est
        if isinstance(beat.get("evidence_refs"), list):
            for ref in beat["evidence_refs"]:
                ok, why = check_ref(str(ref), figs, tabs, anchors, pages)
                if not ok:
                    errors.append(f"beat[{i}] ({bid}): bad evidence ref '{ref}': {why}")
        elif "evidence_refs" in beat:
            errors.append(f"beat[{i}] ({bid}): evidence_refs must be a list")
        if not str(beat.get("transition", "")).strip():
            errors.append(f"beat[{i}] ({bid}): transition must be non-empty")
        text = str(beat.get("beat_text", ""))
        est_from_text = spoken_seconds(text)
        row = {
            "index": i, "id": bid, "est_sec": est,
            "spoken_sec_from_text": round(est_from_text, 1),
            "n_evidence_refs": len(beat.get("evidence_refs") or []),
        }
        if est > 0 and abs(est_from_text - est) / est > 0.30:
            warnings.append(
                f"beat[{i}] ({bid}): est_sec={est:.0f} vs text-implied "
                f"{est_from_text:.0f}s differ >30%; re-time the beat"
            )
        per_beat.append(row)

    budget = minutes * 60.0
    if len(beats) > max_slides:
        errors.append(f"beat count {len(beats)} exceeds max-slides {max_slides}")
    if total_est > budget * 1.10 or total_est < budget * 0.90:
        errors.append(
            f"total est_sec {total_est:.0f}s outside budget±10% "
            f"[{budget*0.9:.0f}, {budget*1.1:.0f}] (minutes={minutes})"
        )
    report = {
        "beats_file": beats_path,
        "minutes": minutes,
        "max_slides": max_slides,
        "budget_sec": budget,
        "n_beats": len(beats),
        "total_est_sec": round(total_est, 1),
        "per_beat": per_beat,
        "errors": errors,
        "warnings": warnings,
        "pass": not errors,
    }
    return report, errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate a beats.json talk script contract.")
    ap.add_argument("beats", help="beats.json path")
    ap.add_argument("--evidence", required=True, help="evidence.json from evidence_scan.py")
    ap.add_argument("--minutes", type=float, default=10.0, help="talk budget in minutes")
    ap.add_argument("--max-slides", type=int, default=8, help="slide upper bound")
    ap.add_argument("--report", required=True, help="output beat_report.json path")
    args = ap.parse_args()
    try:
        with open(args.evidence, encoding="utf-8") as f:
            evidence = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot read evidence.json: {e}", file=sys.stderr)
        return 2
    try:
        report, errors, warnings = validate(args.beats, evidence, args.minutes, args.max_slides)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: cannot parse beats.json: {e}", file=sys.stderr)
        return 2
    if report is None:
        print(f"ERROR: {errors[0]}", file=sys.stderr)
        return 1
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    for w in warnings:
        print(f"WARN: {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        print(f"beat_cut: FAIL ({len(errors)} errors) -> {args.report}", file=sys.stderr)
        return 1
    print(
        f"beat_cut: PASS beats={report['n_beats']} "
        f"total={report['total_est_sec']:.0f}s/{report['budget_sec']:.0f}s -> {args.report}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
