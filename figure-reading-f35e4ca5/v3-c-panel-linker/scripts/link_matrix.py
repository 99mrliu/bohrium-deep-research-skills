#!/usr/bin/env python3
"""link_matrix.py — build, fill and machine-check the question->evidence link matrix.

Modes (exactly one of init/fill/check per run):
  init  (default): parse task.md question lines -> link_matrix.json with unfilled rows.
  fill  (--fill FRAGMENT.json): merge an agent-written fragment assigning
        panels/tables/text_spans/evidence to rows.
  check (--check): verify wiring and coverage -> link_check.json + gap_ledger.json.

CLI: --panels PANEL_MAP.json --captions CAPTION_MAP.json --task TASK.md --work DIR
     [--fill FRAGMENT.json | --check]

Exit codes: 0 = clean, 2 = success with warnings/violations, 1 = fatal error.
"""
import argparse
import json
import os
import re
import sys

QUESTION_LINE_RE = re.compile(
    r"^\s*(?:[-*\u2022]\s+|\d+[.)]\s+|Q\d*[:.)\s]\s*|#{1,6}\s*)?(.*\S)\s*$")
QUESTION_TRIGGER_RE = re.compile(
    r"^\s*(?:[-*\u2022]\s+|\d+[.)]\s+|Q\d+[:.)\s])", re.IGNORECASE)
PANEL_LETTER_RE = re.compile(
    r"\(([a-zA-Z])\)|\bpanel\s+([A-Za-z])\b|\bFig(?:ure)?\.?\s*\d+\s*([a-z])\b")
FIGURE_RE = re.compile(r"\bFig(?:ure)?s?\.?\s*(\d+)")
COMPARATIVE_RE = re.compile(
    r"compar|versus|\bvs\.?\b|between|relative to|against|correlat|"
    r"differ(?:ence)?s?\s+(?:from|between)|"
    r"\u6bd4\u8f83|\u76f8\u6bd4|\u5bf9\u6bd4|\u5dee\u5f02", re.IGNORECASE)

# rough content-type keyword map used ONLY for the mismatch heuristic
CONTENT_TYPES = {
    "timeseries": ["kinetic", "trace", "time course", "vs time", "over time", "curve", "\u66f2\u7ebf", "\u52a8\u529b\u5b66"],
    "quantification": ["quantif", "bar", "significance", "statistic", "group", "\u7edf\u8ba1", "\u663e\u8457"],
    "correlation": ["correlat", "scatter", "\u76f8\u5173", "\u6563\u70b9"],
    "spectrum": ["spectrum", "spectra", "spectral", "\u5149\u8c31", "\u8c31"],
    "image": ["microscop", "image", "staining", "micrograph", "\u663e\u5fae", "\u6210\u50cf"],
}


def fatal(msg):
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(1)


def load_json(path, what):
    if not path or not os.path.isfile(path):
        fatal(f"{what} not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:  # noqa: BLE001
        fatal(f"cannot parse {what} {path}: {exc}")


def load_task(path):
    if not os.path.isfile(path):
        fatal(f"task file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def extract_questions(task_text):
    """Question/claim items: bulleted/numbered/Q-prefixed lines (wrapped continuation
    lines are joined), or standalone lines ending in '?'."""
    questions = []
    current = None
    for raw in task_text.splitlines():
        line = raw.strip()
        if not line:
            if current:
                questions.append(current)
                current = None
            continue
        if line.startswith("#"):
            if current:
                questions.append(current)
                current = None
            continue
        if QUESTION_TRIGGER_RE.match(line):
            if current:
                questions.append(current)
            m = QUESTION_LINE_RE.match(line)
            current = m.group(1).strip()
        elif current is not None:
            current += " " + line
        elif line.rstrip().endswith(("?", "\uff1f")):
            questions.append(line)
    if current:
        questions.append(current)
    if not questions:  # fallback: every non-empty line is a claim to be wired
        questions = [l.strip() for l in task_text.splitlines() if l.strip() and not l.startswith("#")]
    return questions


def suggested_panels(question, panel_map):
    letter2id = {}
    for p in panel_map.get("panels", []):
        if p.get("label_guess"):
            letter2id[p["label_guess"].lower()] = p["id"]
    out = []
    for match in PANEL_LETTER_RE.finditer(question):
        letter = next(g for g in match.groups() if g).lower()
        if letter in letter2id and letter2id[letter] not in out:
            out.append(letter2id[letter])
    return out


def classify(text):
    low = text.lower()
    hits = set()
    for ctype, keywords in CONTENT_TYPES.items():
        if any(k in low for k in keywords):
            hits.add(ctype)
    return hits


def init_mode(args, panel_map, task_text):
    questions = extract_questions(task_text)
    rows = []
    for i, q in enumerate(questions):
        rows.append({
            "id": f"q{i + 1}",
            "question": q,
            "panels": [],
            "tables": [],
            "text_spans": [],
            "evidence": [],
            "suggested_panels": suggested_panels(q, panel_map),
            "comparative": bool(COMPARATIVE_RE.search(q)),
            "status": "unfilled",
            "reason": None,
        })
    matrix = {
        "schema": "link_matrix/1",
        "rows": rows,
        "not_needed_panels": [],
        "not_needed_clauses": [],
    }
    path = os.path.join(args.work, "link_matrix.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(matrix, fh, ensure_ascii=False, indent=2)
    print(f"wrote {path} with {len(rows)} unfilled row(s)")
    if not rows:
        print("WARNING: no question lines found in task.md", file=sys.stderr)
        return 2
    return 0


def fill_mode(args, matrix_path):
    matrix = load_json(matrix_path, "existing link_matrix.json (run init first)")
    fragment = load_json(args.fill, "fill fragment")
    frag_rows = fragment.get("rows", fragment if isinstance(fragment, list) else [])
    if isinstance(frag_rows, dict):
        frag_rows = [dict(v, id=k) for k, v in frag_rows.items()]
    by_id = {r["id"]: r for r in matrix.get("rows", [])}
    warnings = []
    merged = 0
    for frag in frag_rows:
        rid = frag.get("id")
        if rid not in by_id:
            warnings.append(f"unknown row id in fragment: {rid}")
            continue
        row = by_id[rid]
        for field in ("panels", "tables", "text_spans", "evidence"):
            if field in frag:
                row[field] = frag[field]
        if "status" in frag:
            row["status"] = frag["status"]
        elif row["panels"] or row["tables"] or row["text_spans"]:
            row["status"] = "filled"
        if "reason" in frag:
            row["reason"] = frag["reason"]
        merged += 1
    for field in ("not_needed_panels", "not_needed_clauses"):
        if field in fragment:
            matrix[field] = fragment[field]
    with open(matrix_path, "w", encoding="utf-8") as fh:
        json.dump(matrix, fh, ensure_ascii=False, indent=2)
    print(f"merged {merged} fragment row(s) into {matrix_path}")
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)
    return 2 if warnings else 0


def check_mode(args, panel_map, caption_map, task_text):
    matrix_path = os.path.join(args.work, "link_matrix.json")
    matrix = load_json(matrix_path, "link_matrix.json (run init first)")
    panels = {p["id"]: p for p in panel_map.get("panels", [])}
    letter2id = {p.get("label_guess", "").lower(): p["id"]
                 for p in panel_map.get("panels", []) if p.get("label_guess")}
    violations = []
    warnings = []

    def v(type_, detail, row_id=None):
        entry = {"type": type_, "detail": detail}
        if row_id:
            entry["row_id"] = row_id
        violations.append(entry)

    nn_panels = {e.get("panel") for e in matrix.get("not_needed_panels", [])}
    nn_clauses = {e.get("clause") for e in matrix.get("not_needed_clauses", [])
                  if e.get("clause")}
    nn_letters = {e.get("letter", "").lower() for e in matrix.get("not_needed_clauses", [])}

    referenced_panels = set()
    for row in matrix.get("rows", []):
        rid = row.get("id")
        status = row.get("status", "unfilled")
        if status == "not_needed":
            if not row.get("reason"):
                v("not_needed_without_reason", "row marked not_needed without reason", rid)
            continue
        if status == "unfilled":
            v("unfilled_row", f"row has no evidence yet: {row.get('question', '')[:80]}", rid)
            continue
        cited = list(row.get("panels", []))
        for pid in cited:
            if pid not in panels:
                v("unknown_panel", f"cited panel '{pid}' not in panel_map.json", rid)
        referenced_panels.update(pid for pid in cited if pid in panels)
        if not cited and not row.get("tables") and not row.get("text_spans"):
            v("row_without_support",
              "filled row cites no panel, table or text span", rid)
        if row.get("comparative"):
            distinct = {pid for pid in cited if pid in panels}
            if len(distinct) < 2:
                v("comparative_claim_single_panel",
                  f"cross-panel comparative claim cites {len(distinct)} panel(s), need >= 2", rid)
        # content-type mismatch heuristic: question names a panel letter explicitly
        # but the row cites different panels, or content classes are disjoint.
        qletters = {next(g for g in m.groups() if g).lower()
                    for m in PANEL_LETTER_RE.finditer(row.get("question", ""))}
        q_named = {letter2id[l] for l in qletters if l in letter2id}
        if q_named and cited and not (q_named & set(cited)):
            v("content_type_mismatch",
              f"question names panel(s) {sorted(q_named)} but row cites {sorted(cited)}", rid)
        q_types = classify(row.get("question", ""))
        for pid in cited:
            if pid not in panels:
                continue
            letter = panels[pid].get("label_guess") or ""
            clause_text = " ".join(caption_map.get("clauses", {}).get(letter.lower(), []))
            c_types = classify(clause_text)
            if q_types and c_types and q_types.isdisjoint(c_types):
                v("content_type_mismatch",
                  f"question type {sorted(q_types)} vs panel {pid} caption type "
                  f"{sorted(c_types)}", rid)

    # coverage: every caption panel-clause referenced or marked not_needed
    for letter in caption_map.get("clauses", {}):
        pid = letter2id.get(letter.lower())
        clause_hit = any(c in " ".join(caption_map["clauses"][letter]) for c in nn_clauses)
        if pid is None:
            v("caption_pixel_mismatch",
              f"caption describes panel ({letter}) but no pixel panel carries that label; "
              f"record an uncertainty entry, do not guess-merge")
        elif pid not in referenced_panels and pid not in nn_panels \
                and letter.lower() not in nn_letters and not clause_hit:
            v("unused_caption_clause",
              f"caption clause for panel ({letter}) not referenced by any row "
              f"and not marked not_needed")
    # coverage: every pixel panel referenced or marked
    for pid in panels:
        if pid not in referenced_panels and pid not in nn_panels:
            v("unreferenced_panel", f"pixel panel {pid} not referenced by any row "
                                    f"and not marked not_needed")

    # gap ledger: figures without pixels (caption_map seeds + task.md mentions)
    gaps = []
    have_pixels = set(caption_map.get("figures_with_pixels", []))
    for g in caption_map.get("figures_without_pixels", []):
        gaps.append({
            "reference": g["reference"],
            "evidence": f"{g.get('mentioned_in', 'caption')}: {g.get('reason', '')}",
            "status": "no_pixels_provided",
        })
    seen = {g["reference"] for g in gaps}
    for raw in task_text.splitlines():
        for m in FIGURE_RE.finditer(raw):
            ref = f"Figure {int(m.group(1))}"
            if ref not in seen and ref not in have_pixels:
                gaps.append({
                    "reference": ref,
                    "evidence": f"task.md line: {raw.strip()[:120]}",
                    "status": "no_pixels_provided",
                })
                seen.add(ref)
    if gaps:
        warnings.append(f"gap_ledger: {len(gaps)} figure(s) without pixels: "
                        + ", ".join(g["reference"] for g in gaps))

    check = {
        "schema": "link_check/1",
        "ok": not violations,
        "violations": violations,
        "warnings": warnings,
        "summary": {
            "rows": len(matrix.get("rows", [])),
            "panels": len(panels),
            "caption_clauses": sum(len(vv) for vv in caption_map.get("clauses", {}).values()),
            "gaps": len(gaps),
        },
    }
    check_path = os.path.join(args.work, "link_check.json")
    with open(check_path, "w", encoding="utf-8") as fh:
        json.dump(check, fh, ensure_ascii=False, indent=2)
    ledger = {"schema": "gap_ledger/1", "gaps": gaps}
    ledger_path = os.path.join(args.work, "gap_ledger.json")
    with open(ledger_path, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh, ensure_ascii=False, indent=2)
    print(f"wrote {check_path} ({len(violations)} violation(s)) and {ledger_path} "
          f"({len(gaps)} gap(s))")
    for entry in violations:
        print(f"VIOLATION [{entry['type']}] {entry.get('row_id', '')}: {entry['detail']}",
              file=sys.stderr)
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)
    return 2 if (violations or warnings) else 0


def main():
    ap = argparse.ArgumentParser(description="Init/fill/check the question-evidence link matrix.")
    ap.add_argument("--panels", required=True)
    ap.add_argument("--captions", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--fill", default=None, help="agent-written fill fragment JSON")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.work, exist_ok=True)
    panel_map = load_json(args.panels, "panel_map.json")
    caption_map = load_json(args.captions, "caption_map.json")
    task_text = load_task(args.task)

    if args.check:
        code = check_mode(args, panel_map, caption_map, task_text)
    elif args.fill:
        code = fill_mode(args, os.path.join(args.work, "link_matrix.json"))
    else:
        code = init_mode(args, panel_map, task_text)
    sys.exit(code)


if __name__ == "__main__":
    main()
