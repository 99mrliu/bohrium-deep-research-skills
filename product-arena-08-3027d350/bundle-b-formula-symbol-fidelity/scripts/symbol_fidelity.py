#!/usr/bin/env python3
"""symbol_fidelity.py — linearize math lines and audit symbol fidelity.

Pipeline stage 2 of the formula-symbol-fidelity skill.

Inputs : math_lines.jsonl (from math_detect.py) + the original word TSV.
Outputs (in --out-dir):
  * math_linearized.jsonl — one record per math line with explicit
    sub/superscript markup:  base_{sub} / base^{sup}
  * symbol_inventory.json — reconciliation of mapped-symbol counts between
    raw extraction and linearized output, plus every unmappable non-ASCII
    character listed as `unknown` with page/line/codepoint. Nothing is
    guessed and nothing is silently dropped: unknown glyphs stay verbatim
    in the linearized text AND are reported.

Sub/superscript rule (y grows downward): within a line, a word whose
baseline (y1) deviates from the line's median baseline by more than
0.25 x its own font size is a script; negative deviation => superscript,
positive => subscript.

Exit codes: 0 = ok, 2 = input/usage error, 3 = degenerate input.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import InputError, group_lines, load_words

SCRIPT_FACTOR = 0.25       # baseline-deviation threshold, in units of font size
EQNUM_TOKEN_RE = re.compile(r"^\(\d+(?:\.\d+)?\)$")


def load_symbol_map(path):
    """glyph -> {name, latex}; skips comments/blank lines."""
    table = {}
    p = Path(path)
    if not p.is_file():
        raise InputError(f"symbol map not found: {path}")
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        table[parts[0]] = {"name": parts[1], "latex": parts[2]}
    if not table:
        raise InputError(f"symbol map is empty: {path}")
    return table


def map_text(text, table):
    """Replace known glyphs with their LaTeX form; keep everything else."""
    return "".join(table[ch]["latex"] if ch in table else ch for ch in text)


def count_latex(haystack, latex):
    """Count occurrences of a LaTeX token, not inside a longer command."""
    pat = r"(?<![\\A-Za-z])" + re.escape(latex) + r"(?![A-Za-z])"
    return len(re.findall(pat, haystack))


def attach_scripts(words, table):
    """Linearize one math line's words with ^/_ markup. Returns (text, notes)."""
    if not words:
        return "", []
    baseline = statistics.median(w.y1 for w in words)
    tokens, notes = [], []
    for w in sorted(words, key=lambda w: w.x0):
        mapped = map_text(w.text, table)
        dev = w.y1 - baseline
        kind = None
        if dev < -SCRIPT_FACTOR * w.size:
            kind = "superscript"
        elif dev > SCRIPT_FACTOR * w.size:
            kind = "subscript"
        if kind and tokens:
            brace = "^{" if kind == "superscript" else "_{"
            tokens[-1] += f"{brace}{mapped}}}"
            notes.append({"word": w.text, "kind": kind,
                          "baseline_dev": round(dev, 2), "size": w.size})
        elif kind:  # leading script with no base: keep it, mark honestly
            brace = "^{" if kind == "superscript" else "_{"
            tokens.append(f"{brace}{mapped}}}")
            notes.append({"word": w.text, "kind": kind + "_no_base",
                          "baseline_dev": round(dev, 2), "size": w.size})
        else:
            tokens.append(mapped)
    return " ".join(tokens), notes


def match_line(grouped, rec):
    """Find the grouped Line matching a math_lines.jsonl record by geometry."""
    for ln in grouped:
        if ln.page != rec["page"]:
            continue
        b = ln.bbox
        if abs(b[0] - rec["bbox"][0]) < 0.01 and abs(b[1] - rec["bbox"][1]) < 0.01:
            return ln
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--math-lines", required=True, help="math_lines.jsonl")
    ap.add_argument("--input", required=True, help="original word-level TSV")
    ap.add_argument("--map", default=str(Path(__file__).resolve().parent.parent
                                         / "references" / "symbol-map.tsv"),
                    help="references/symbol-map.tsv")
    ap.add_argument("--out-dir", required=True, help="output directory")
    args = ap.parse_args(argv)

    try:
        table = load_symbol_map(args.map)
        words = load_words(args.input)
        ml_path = Path(args.math_lines)
        if not ml_path.is_file():
            raise InputError(f"math lines file not found: {args.math_lines}")
        recs = [json.loads(l) for l in
                ml_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (InputError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not words:
        print("error: word TSV contains zero usable words", file=sys.stderr)
        return 3

    grouped = group_lines(words)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    lin_path = out_dir / "math_linearized.jsonl"
    unknown = {}   # char -> {codepoint, occurrences:[{page,line_id}]}
    unmatched = []
    with lin_path.open("w", encoding="utf-8") as fh:
        for rec in recs:
            ln = match_line(grouped, rec)
            if ln is None:
                unmatched.append(rec["line_id"])
                lin_text, notes, scripts = rec["raw_text"], [], 0
            else:
                body = list(ln.words)
                if rec.get("eq_number") and body and \
                        EQNUM_TOKEN_RE.match(body[-1].text):
                    body = body[:-1]  # number captured separately, not in text
                lin_text, notes = attach_scripts(body, table)
                scripts = sum(1 for n in notes if "no_base" not in n["kind"])
            for ch in rec["raw_text"]:
                if ord(ch) > 127 and ch not in table:
                    ent = unknown.setdefault(
                        ch, {"codepoint": f"U+{ord(ch):04X}", "occurrences": []})
                    ent["occurrences"].append(
                        {"page": rec["page"], "line_id": rec["line_id"]})
            out = dict(rec)
            out["linearized"] = lin_text
            out["script_notes"] = notes
            out["scripts_attached"] = scripts
            fh.write(json.dumps(out, ensure_ascii=False) + "\n")

    raw_all = "\n".join(r["raw_text"] for r in recs)
    lin_all = "\n".join(json.loads(l)["linearized"] for l in
                        lin_path.read_text(encoding="utf-8").splitlines()
                        if l.strip())
    glyphs = {}
    for glyph, meta in sorted(table.items()):
        rc = raw_all.count(glyph)
        oc = count_latex(lin_all, meta["latex"])
        if rc == 0 and oc == 0:
            continue  # only audit glyphs that actually occur
        glyphs[glyph] = {"name": meta["name"], "latex": meta["latex"],
                         "raw_count": rc, "output_count": oc, "ok": rc == oc}
    unknown_list = [{"char": ch, **meta} for ch, meta in sorted(unknown.items())]
    issues = [g for g, v in glyphs.items() if not v["ok"]] or unmatched or unknown_list
    inventory = {
        "schema": "symbol-inventory/1",
        "math_lines": len(recs),
        "glyphs": glyphs,
        "totals": {
            "raw_mapped": sum(v["raw_count"] for v in glyphs.values()),
            "output_mapped": sum(v["output_count"] for v in glyphs.values()),
            "unknown": len(unknown_list),
        },
        "unknown": unknown_list,
        "unmatched_lines": unmatched,
        "status": "issues" if issues else "ok",
    }
    inv_path = out_dir / "symbol_inventory.json"
    inv_path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(json.dumps({"status": inventory["status"],
                      "math_lines": len(recs),
                      "unknown": len(unknown_list),
                      "out_dir": str(out_dir)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
