#!/usr/bin/env python3
"""engine_col.py -- Twin-pass engine B (column-set implementation).

Implementation B of the twin-pass redundant pair. Same contract as
engine_row.py (one rules.json in; cleaned.csv / ledger.csv / summary.json
out), but deliberately written in a DIFFERENT style: csv.DictReader into a
dict-of-columns, list comprehensions, set membership tests and max() with
tuple sort keys instead of csv.reader row streaming and imperative scans.
The two engines share no code, so an implementation error or an ambiguous
rule surfaces as a reconciliation divergence rather than shipping silently.

Exit codes:
    0  success
    3  rules.json failed validation
    4  input table error (missing columns, ragged rows, unknown unit label)

Determinism: explicit sort keys, fixed float format (.10g), newline="\n",
no wall clock, no randomness, no network.

Documented default of THIS engine when rules omit dedup.tie:
last_occurrence (a column-style "highest (score, position) wins" reduction
naturally prefers the latest candidate, as if later re-entries supersede).
engine_row.py documents the opposite default. If the spec is silent about
ties, the twin pass disagrees and forces the ambiguity to be resolved in
rules.json -- that is the intended behaviour, not a bug.
"""

import argparse
import csv
import json
import math
import os
import sys
import unicodedata

EXIT_OK = 0
EXIT_RULES = 3
EXIT_INPUT = 4

FLOAT_FMT = ".10g"
DEFAULT_TIE = "last_occurrence"  # engine B documented default (see module docstring)

VALID_SENTINEL_CLASSES = ("not_detected", "below_detection_limit", "entry_missing")
ALL_CLASSES = ("valid", "true_zero", "not_detected", "below_detection_limit",
               "entry_missing", "unparseable")
ALL_FLAGS = ("out_of_bounds_high", "out_of_bounds_low", "unparseable_value")
ALLOWED_STEPS = ("trim", "collapse_ws", "lower", "nfc")


def fail(code, problems):
    for p in problems:
        sys.stderr.write("engine_col: error: %s\n" % p)
    sys.exit(code)


def normalize_key(text, steps):
    out = text
    for step in steps:
        if step == "trim":
            out = out.strip()
        elif step == "collapse_ws":
            out = " ".join(out.split())
        elif step == "lower":
            out = out.lower()
        elif step == "nfc":
            out = unicodedata.normalize("NFC", out)
    return out


def fmt_num(value):
    text = format(value, FLOAT_FMT)
    return "0" if text == "-0" else text


def parse_finite(text):
    try:
        v = float(text)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def check_rules(rules):
    """Independent re-validation of the rules contract (engine B wording)."""
    bad = []
    if not isinstance(rules, dict):
        return ["top level of rules.json is not an object"]
    if rules.get("version") != 1:
        bad.append("version != 1")
    if not rules.get("case_id"):
        bad.append("case_id missing")
    if not isinstance(rules.get("key"), dict) or not rules["key"].get("column"):
        bad.append("key.column missing")
    if not isinstance(rules.get("meta_columns", []), list):
        bad.append("meta_columns is not a list")
    ms = rules.get("measures")
    if not ms or not isinstance(ms, list):
        bad.append("measures missing or empty")
    else:
        names = [m.get("column") for m in ms if isinstance(m, dict)]
        if len(names) != len(set(names)):
            bad.append("duplicate measure column names")
        for m in ms:
            col = m.get("column", "?")
            if not m.get("source"):
                bad.append("measure %s lacks source" % col)
            for s in m.get("sentinels", []):
                if not isinstance(s.get("pattern"), str):
                    bad.append("measure %s has a sentinel without string pattern" % col)
                if s.get("class") not in VALID_SENTINEL_CLASSES:
                    bad.append("measure %s sentinel %r: class not in %s"
                               % (col, s.get("pattern"), "/".join(VALID_SENTINEL_CLASSES)))
                if not s.get("source"):
                    bad.append("measure %s sentinel %r lacks source" % (col, s.get("pattern")))
            b = m.get("bounds")
            if b is not None:
                if not all(isinstance(b.get(k), (int, float)) and not isinstance(b.get(k), bool)
                           for k in ("min", "max")):
                    bad.append("measure %s bounds min/max must be numbers" % col)
                elif b["min"] > b["max"]:
                    bad.append("measure %s bounds min > max" % col)
                if b.get("action", "flag_keep") != "flag_keep":
                    bad.append("measure %s bounds.action must be flag_keep" % col)
                if not b.get("source"):
                    bad.append("measure %s bounds lacks source" % col)
            if "zero_is_true" in m and not isinstance(m["zero_is_true"], bool):
                bad.append("measure %s zero_is_true must be boolean" % col)
            if "convert_units" in m and not isinstance(m["convert_units"], bool):
                bad.append("measure %s convert_units must be boolean" % col)
        if any(m.get("convert_units") for m in ms if isinstance(m, dict)) \
                and rules.get("unit_column") is None:
            bad.append("convert_units=true on a measure but unit_column missing")
    uc = rules.get("unit_column")
    if uc is not None:
        if not uc.get("column") or not uc.get("target"):
            bad.append("unit_column needs column and target")
        if not isinstance(uc.get("factors"), dict) or not uc.get("factors"):
            bad.append("unit_column.factors missing/empty")
        else:
            if uc.get("target") not in uc["factors"]:
                bad.append("unit_column.factors lacks target %r" % uc.get("target"))
            if any(not isinstance(v, (int, float)) or isinstance(v, bool)
                   for v in uc["factors"].values()):
                bad.append("unit_column.factors values must be numbers")
        if not uc.get("source"):
            bad.append("unit_column lacks source")
    d = rules.get("dedup")
    if not isinstance(d, dict):
        bad.append("dedup missing")
    else:
        if not d.get("normalize") or any(s not in ALLOWED_STEPS for s in d.get("normalize", [])):
            bad.append("dedup.normalize has unknown steps (allowed: %s)" % "/".join(ALLOWED_STEPS))
        if d.get("keep") != "most_complete":
            bad.append("dedup.keep must be most_complete")
        if "tie" in d and d["tie"] not in ("first_occurrence", "last_occurrence"):
            bad.append("dedup.tie must be first_occurrence|last_occurrence")
        if not d.get("source"):
            bad.append("dedup lacks source")
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description="Twin-pass engine B (column-set).")
    ap.add_argument("--rules", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args(argv)

    try:
        with open(args.rules, "r", encoding="utf-8") as fh:
            rules = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        fail(EXIT_RULES, ["cannot parse rules.json: %s" % exc])
    problems = check_rules(rules)
    if problems:
        fail(EXIT_RULES, ["rules invalid: %s" % p for p in problems])

    key_col = rules["key"]["column"]
    meta_cols = list(rules.get("meta_columns", []))
    measures = rules["measures"]
    uc = rules.get("unit_column")
    dedup = rules["dedup"]
    steps = dedup["normalize"]
    measure_cols = [m["column"] for m in measures]
    required = {key_col, *meta_cols, *measure_cols}
    if uc:
        required.add(uc["column"])

    # ---- load whole table as a dict of columns -------------------------
    try:
        fh = open(args.csv, "r", encoding="utf-8", newline="")
    except OSError as exc:
        fail(EXIT_INPUT, ["cannot open csv: %s" % exc])
    with fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            fail(EXIT_INPUT, ["empty table: no header row"])
        header = [h.strip() for h in reader.fieldnames]
        absent = sorted(required - set(header))
        if absent:
            fail(EXIT_INPUT, ["missing required column(s): %s" % ", ".join(absent)])
        table = []
        for row in reader:  # DictReader skips fully blank physical lines
            if None in row or any(v is None for v in row.values()):
                fail(EXIT_INPUT, ["ragged row near physical line %d" % reader.line_num])
            table.append({k.strip(): v for k, v in row.items()})

    n = len(table)
    if n == 0:
        fail(EXIT_INPUT, ["table has a header but zero data rows"])

    cols = {name: [r[name] for r in table] for name in header}
    idx = list(range(n))  # 0-based; src_row = i + 1

    # ---- normalized keys, groups, completeness scores (column ops) -----
    norm_keys = [normalize_key(v, steps) for v in cols[key_col]]
    groups = {}
    for i, nk in enumerate(norm_keys):
        groups.setdefault(nk, []).append(i)
    sentinel_pats = {m["column"]: {s["pattern"] for s in m.get("sentinels", [])}
                     for m in measures}
    # completeness = measured cells only: no sentinel match AND finite numeric
    scores = [sum(1 for mc in measure_cols
                  if cols[mc][i].strip() not in sentinel_pats[mc]
                  and parse_finite(cols[mc][i].strip()) is not None)
              for i in idx]

    # ---- dedup selection via max() with tuple keys ----------------------
    tie_used = dedup["tie"] if "tie" in dedup else DEFAULT_TIE
    if tie_used == "last_occurrence":
        best_of = {nk: max(idxs, key=lambda i: (scores[i], i)) for nk, idxs in groups.items()}
    else:
        best_of = {nk: max(idxs, key=lambda i: (scores[i], -i)) for nk, idxs in groups.items()}
    keep_set = set(best_of.values())

    ledger = []
    for nk, idxs in groups.items():
        if len(idxs) <= 1:
            continue
        b = best_of[nk]
        ledger.append(["dedup_keep", b + 1, key_col, "duplicate_key",
                       "norm_key='%s'; candidates=%d; kept score=%d; tie=%s"
                       % (nk, len(idxs), scores[b], tie_used),
                       dedup["source"]])
        ledger += [["dedup_drop", i + 1, key_col, "duplicate_key",
                    "norm_key='%s'; kept src_row=%d score=%d; dropped score=%d; tie=%s"
                    % (nk, b + 1, scores[b], scores[i], tie_used),
                    dedup["source"]]
                   for i in idxs if i != b]

    # ---- unit factors, validated over the whole column at once ----------
    unit_labels = None
    if uc:
        unit_labels = [v.strip() for v in cols[uc["column"]]]
        unknown = sorted(set(unit_labels) - set(uc["factors"]))
        if unknown:
            fail(EXIT_INPUT,
                 ["unknown unit label(s) %s; add them to unit_column.factors in rules.json"
                  % ", ".join(repr(u) for u in unknown)])
    factor_of = ({i: float(uc["factors"][unit_labels[i]]) for i in idx} if uc else {})

    # ---- column-wise cell classification --------------------------------
    # cell[(i, col)] = (value_text, klass, flag); ledger only for kept rows.
    cell = {}
    for m in measures:
        col = m["column"]
        sentinel_by_pattern = {s["pattern"]: s for s in m.get("sentinels", [])}
        raws = [v.strip() for v in cols[col]]
        bounds = m.get("bounds")
        for i in idx:
            raw = raws[i]
            kept_row = i in keep_set
            if raw in sentinel_by_pattern:
                s = sentinel_by_pattern[raw]
                cell[(i, col)] = ("", s["class"], "")
                if kept_row:
                    ledger.append(["cell_flag", i + 1, col, s["class"],
                                   "raw='%s'; marked %s, not imputed" % (raw, s["class"]),
                                   s["source"]])
                continue
            val = parse_finite(raw)
            if val is None:
                cell[(i, col)] = (raw, "unparseable", "unparseable_value")
                if kept_row:
                    ledger.append(["cell_flag", i + 1, col, "unparseable",
                                   "raw='%s'; not numeric and no sentinel rule matched; original kept" % raw,
                                   m["source"]])
                continue
            if uc and m.get("convert_units", False):
                val = val * factor_of[i]
                if kept_row and unit_labels[i] != uc["target"]:
                    ledger.append(["unit_convert", i + 1, col, "unit_converted",
                                   "unit '%s' -> '%s' factor=%s"
                                   % (unit_labels[i], uc["target"], fmt_num(factor_of[i])),
                                   uc["source"]])
            value_text = fmt_num(val)
            klass = "valid"
            if val == 0 and m.get("zero_is_true"):
                klass = "true_zero"
                if kept_row:
                    ledger.append(["cell_flag", i + 1, col, "true_zero",
                                   "raw='%s'; numeric zero; marked true_zero, not imputed" % raw,
                                   m["source"]])
            flag = ""
            if bounds:
                if val > float(bounds["max"]):
                    flag = "out_of_bounds_high"
                elif val < float(bounds["min"]):
                    flag = "out_of_bounds_low"
                if flag and kept_row:
                    which = ">" if flag == "out_of_bounds_high" else "<"
                    limit = bounds["max"] if flag == "out_of_bounds_high" else bounds["min"]
                    ledger.append(["cell_flag", i + 1, col, flag,
                                   "value %s %s %s %s; original kept, flagged"
                                   % (value_text, which, "max" if flag == "out_of_bounds_high" else "min",
                                      fmt_num(float(limit))),
                                   bounds["source"]])
            cell[(i, col)] = (value_text, klass, flag)

    # ---- assemble cleaned rows in ascending src_row order ---------------
    cleaned_header = ["src_row", key_col + "_raw", key_col + "_norm"] + meta_cols
    if uc:
        cleaned_header.append(uc["column"] + "_raw")
    for col in measure_cols:
        cleaned_header += [col, col + "_class", col + "_flag"]

    def cleaned_row(i):
        base = {"src_row": str(i + 1),
                key_col + "_raw": cols[key_col][i],
                key_col + "_norm": norm_keys[i]}
        base.update({mc: cols[mc][i] for mc in meta_cols})
        if uc:
            base[uc["column"] + "_raw"] = cols[uc["column"]][i]
        for col in measure_cols:
            value_text, klass, flag = cell[(i, col)]
            base[col] = value_text
            base[col + "_class"] = klass
            base[col + "_flag"] = flag
        return [base[h] for h in cleaned_header]

    kept_idx = sorted(keep_set)
    cleaned_rows = [cleaned_row(i) for i in kept_idx]

    # ---- counts (set reductions over kept cells) ------------------------
    kept_cells = [(i, col) for i in kept_idx for col in measure_cols]
    counts = {c: sum(1 for k in kept_cells if cell[k][1] == c) for c in ALL_CLASSES}
    flag_counts = {f: sum(1 for k in kept_cells if cell[k][2] == f) for f in ALL_FLAGS}
    unit_conversions = sum(1 for e in ledger if e[0] == "unit_convert")

    ledger.sort(key=lambda e: (e[1], e[2], e[0], e[3]))

    # ---- write artifacts -------------------------------------------------
    os.makedirs(args.outdir, exist_ok=True)
    with open(os.path.join(args.outdir, "cleaned.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(cleaned_header)
        w.writerows(cleaned_rows)
    with open(os.path.join(args.outdir, "ledger.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["record", "src_row", "field", "record_class", "detail", "source"])
        w.writerows(ledger)
    summary = {
        "case_id": rules["case_id"],
        "rows_input": n,
        "rows_output": len(kept_idx),
        "duplicates_dropped": n - len(kept_idx),
        "cell_class_counts": counts,
        "flag_counts": flag_counts,
        "unit_conversions": unit_conversions,
        "aggregate_statistics": "none (population statistics are prohibited)",
    }
    with open(os.path.join(args.outdir, "summary.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    print("engine_col: OK rows_in=%d rows_out=%d ledger=%d -> %s"
          % (n, len(kept_idx), len(ledger), args.outdir))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
