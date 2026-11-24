#!/usr/bin/env python3
"""engine_row.py -- Twin-pass engine A (row-streaming implementation).

Implementation A of the twin-pass redundant pair. It reads one rules.json
specification and one normalized CSV, processes the table ONE ROW AT A TIME
with csv.reader and imperative loops, and writes three deterministic
artifacts into --outdir:

    cleaned.csv   cleaned table (sentinels classified, never imputed)
    ledger.csv    per-cell / per-row change records with provenance
    summary.json  process counts only (no population statistics)

This script deliberately shares NO code with engine_col.py. The two engines
are independent implementations of the same rules.json contract; any
divergence between their outputs is a finding, not noise.

Exit codes:
    0  success
    3  rules.json failed validation
    4  input table error (missing columns, ragged rows, unknown unit label)

Determinism: explicit sort keys, fixed float format (.10g), newline="\n",
no wall clock, no randomness, no network.

Documented default of THIS engine when rules omit dedup.tie:
first_occurrence (an imperative "replace only when strictly better" scan
naturally keeps the earliest candidate). engine_col.py documents the
opposite default. An underspecified spec therefore surfaces as a
reconciliation divergence -- which is the point of the twin pass.
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
DEFAULT_TIE = "first_occurrence"  # engine A documented default (see module docstring)

VALID_SENTINEL_CLASSES = ("not_detected", "below_detection_limit", "entry_missing")
ALL_CLASSES = ("valid", "true_zero", "not_detected", "below_detection_limit",
               "entry_missing", "unparseable")
ALL_FLAGS = ("out_of_bounds_high", "out_of_bounds_low", "unparseable_value")
ALLOWED_STEPS = ("trim", "collapse_ws", "lower", "nfc")


def die(code, msg):
    sys.stderr.write("engine_row: error: %s\n" % msg)
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


def is_finite_number(text):
    try:
        return math.isfinite(float(text))
    except ValueError:
        return False


def validate_rules(rules):
    problems = []
    if not isinstance(rules, dict):
        return ["rules root must be a JSON object"]
    if rules.get("version") != 1:
        problems.append("rules.version must be 1")
    if not isinstance(rules.get("case_id"), str) or not rules.get("case_id"):
        problems.append("rules.case_id must be a non-empty string")
    key = rules.get("key")
    if not isinstance(key, dict) or not isinstance(key.get("column"), str) or not key.get("column"):
        problems.append("rules.key.column is required (non-empty string)")
    meta = rules.get("meta_columns", [])
    if not isinstance(meta, list) or any(not isinstance(c, str) for c in meta):
        problems.append("rules.meta_columns must be an array of strings")
    measures = rules.get("measures")
    if not isinstance(measures, list) or not measures:
        problems.append("rules.measures must be a non-empty array")
    else:
        seen = set()
        for idx, m in enumerate(measures):
            where = "measures[%d]" % idx
            if not isinstance(m, dict) or not isinstance(m.get("column"), str) or not m.get("column"):
                problems.append(where + ".column is required (non-empty string)")
                continue
            if m["column"] in seen:
                problems.append(where + ".column duplicated: %s" % m["column"])
            seen.add(m["column"])
            if not isinstance(m.get("source"), str) or not m["source"]:
                problems.append(where + ".source is required (provenance)")
            sentinels = m.get("sentinels", [])
            if not isinstance(sentinels, list):
                problems.append(where + ".sentinels must be an array")
                sentinels = []
            for sidx, s in enumerate(sentinels):
                sw = "%s.sentinels[%d]" % (where, sidx)
                if not isinstance(s, dict) or not isinstance(s.get("pattern"), str):
                    problems.append(sw + ".pattern must be a string")
                    continue
                if s.get("class") not in VALID_SENTINEL_CLASSES:
                    problems.append(sw + ".class must be one of " + "|".join(VALID_SENTINEL_CLASSES))
                if not isinstance(s.get("source"), str) or not s["source"]:
                    problems.append(sw + ".source is required (provenance)")
            if "zero_is_true" in m and not isinstance(m["zero_is_true"], bool):
                problems.append(where + ".zero_is_true must be a boolean")
            if "convert_units" in m and not isinstance(m["convert_units"], bool):
                problems.append(where + ".convert_units must be a boolean")
            bounds = m.get("bounds")
            if bounds is not None:
                if not isinstance(bounds, dict):
                    problems.append(where + ".bounds must be an object")
                else:
                    if not isinstance(bounds.get("min"), (int, float)) or not isinstance(bounds.get("max"), (int, float)):
                        problems.append(where + ".bounds.min and .max must be numbers")
                    elif bounds["min"] > bounds["max"]:
                        problems.append(where + ".bounds.min must be <= bounds.max")
                    if bounds.get("action", "flag_keep") != "flag_keep":
                        problems.append(where + ".bounds.action must be 'flag_keep' (no deletion, no imputation)")
                    if not isinstance(bounds.get("source"), str) or not bounds.get("source"):
                        problems.append(where + ".bounds.source is required (provenance)")
    if any(isinstance(m, dict) and m.get("convert_units") for m in rules.get("measures", [])) \
            and rules.get("unit_column") is None:
        problems.append("a measure has convert_units=true but rules.unit_column is missing")
    uc = rules.get("unit_column")
    if uc is not None:
        if not isinstance(uc, dict):
            problems.append("rules.unit_column must be an object")
        else:
            if not isinstance(uc.get("column"), str) or not uc.get("column"):
                problems.append("unit_column.column is required")
            if not isinstance(uc.get("target"), str) or not uc.get("target"):
                problems.append("unit_column.target is required")
            factors = uc.get("factors")
            if not isinstance(factors, dict) or not factors:
                problems.append("unit_column.factors must be a non-empty object {label: factor}")
            else:
                for label, f in factors.items():
                    if not isinstance(f, (int, float)) or isinstance(f, bool):
                        problems.append("unit_column.factors[%r] must be a number" % label)
                if isinstance(uc.get("target"), str) and uc["target"] not in factors:
                    problems.append("unit_column.factors must contain the target unit %r (usually 1.0)" % uc.get("target"))
            if not isinstance(uc.get("source"), str) or not uc.get("source"):
                problems.append("unit_column.source is required (provenance)")
    dedup = rules.get("dedup")
    if not isinstance(dedup, dict):
        problems.append("rules.dedup is required (object)")
    else:
        steps = dedup.get("normalize")
        if not isinstance(steps, list) or not steps:
            problems.append("dedup.normalize must be a non-empty array of steps")
        else:
            for st in steps:
                if st not in ALLOWED_STEPS:
                    problems.append("dedup.normalize step %r not in %s" % (st, "/".join(ALLOWED_STEPS)))
        if dedup.get("keep") != "most_complete":
            problems.append("dedup.keep must be 'most_complete'")
        if "tie" in dedup and dedup["tie"] not in ("first_occurrence", "last_occurrence"):
            problems.append("dedup.tie must be 'first_occurrence' or 'last_occurrence'")
        if not isinstance(dedup.get("source"), str) or not dedup.get("source"):
            problems.append("dedup.source is required (provenance)")
    return problems


def load_rules(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            rules = json.load(fh)
    except OSError as exc:
        die(EXIT_RULES, "cannot open rules file: %s" % exc)
    except json.JSONDecodeError as exc:
        die(EXIT_RULES, "rules file is not valid JSON: %s" % exc)
    problems = validate_rules(rules)
    if problems:
        for p in problems:
            sys.stderr.write("engine_row: rules invalid: %s\n" % p)
        sys.exit(EXIT_RULES)
    return rules


def completeness(row, measures):
    """Number of measure cells holding a real measurement: the cell must
    NOT match any sentinel pattern and must parse as a finite number
    (0 and out-of-bounds values count; sentinels and unparsable text
    do not)."""
    score = 0
    for m in measures:
        raw = row[m["column"]].strip()
        sentinel = False
        for s in m.get("sentinels", []):
            if raw == s["pattern"]:
                sentinel = True
                break
        if not sentinel and is_finite_number(raw):
            score += 1
    return score


def main(argv=None):
    parser = argparse.ArgumentParser(description="Twin-pass engine A (row-streaming).")
    parser.add_argument("--rules", required=True, help="path to rules.json")
    parser.add_argument("--csv", required=True, help="path to normalized input CSV")
    parser.add_argument("--outdir", required=True, help="output directory")
    args = parser.parse_args(argv)

    rules = load_rules(args.rules)
    key_col = rules["key"]["column"]
    meta_cols = list(rules.get("meta_columns", []))
    measures = rules["measures"]
    uc = rules.get("unit_column")
    dedup = rules["dedup"]
    steps = dedup["normalize"]

    required = [key_col] + meta_cols + [m["column"] for m in measures]
    if uc:
        required.append(uc["column"])

    # ---- read table, row streaming -------------------------------------
    try:
        fh = open(args.csv, "r", encoding="utf-8", newline="")
    except OSError as exc:
        die(EXIT_INPUT, "cannot open csv: %s" % exc)
    with fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if header is None:
            die(EXIT_INPUT, "empty table: no header row")
        header = [h.strip() for h in header]
        missing = [c for c in required if c not in header]
        if missing:
            die(EXIT_INPUT, "missing required column(s): %s" % ", ".join(missing))
        raw_rows = []
        physical = 1  # header was line 1
        for fields in reader:
            physical += 1
            if not fields:
                continue  # tolerate fully blank physical lines
            if len(fields) != len(header):
                die(EXIT_INPUT, "physical line %d has %d fields, expected %d"
                    % (physical, len(fields), len(header)))
            raw_rows.append(fields)

    if not raw_rows:
        die(EXIT_INPUT, "table has a header but zero data rows")

    # ---- group by normalized key ---------------------------------------
    groups = {}
    order = []
    for src, fields in enumerate(raw_rows, start=1):
        row = dict(zip(header, fields))
        nk = normalize_key(row[key_col], steps)
        if nk not in groups:
            groups[nk] = []
            order.append(nk)
        groups[nk].append((src, row))

    # ---- dedup selection: most_complete, then documented tie rule ------
    tie_used = dedup["tie"] if "tie" in dedup else DEFAULT_TIE
    ledger = []
    kept = {}
    for nk in order:
        cands = groups[nk]
        best = None
        best_score = -1
        for cand in cands:
            sc = completeness(cand[1], measures)
            if best is None or sc > best_score or (sc == best_score and tie_used == "last_occurrence"):
                best, best_score = cand, sc
        kept[best[0]] = best[1]
        if len(cands) > 1:
            ledger.append(["dedup_keep", best[0], key_col, "duplicate_key",
                           "norm_key='%s'; candidates=%d; kept score=%d; tie=%s"
                           % (nk, len(cands), best_score, tie_used),
                           dedup["source"]])
            for cand in cands:
                if cand[0] == best[0]:
                    continue
                sc = completeness(cand[1], measures)
                ledger.append(["dedup_drop", cand[0], key_col, "duplicate_key",
                               "norm_key='%s'; kept src_row=%d score=%d; dropped score=%d; tie=%s"
                               % (nk, best[0], best_score, sc, tie_used),
                               dedup["source"]])

    # ---- per-row cell processing ---------------------------------------
    counts = {c: 0 for c in ALL_CLASSES}
    flag_counts = {f: 0 for f in ALL_FLAGS}
    unit_conversions = 0
    cleaned_rows = []
    for src in sorted(kept):
        row = kept[src]
        unit_raw = None
        factor = None
        if uc:
            unit_raw = row[uc["column"]].strip()
            if unit_raw not in uc["factors"]:
                die(EXIT_INPUT,
                    "unknown unit label '%s' at src_row %d; add it to unit_column.factors in rules.json"
                    % (unit_raw, src))
            factor = float(uc["factors"][unit_raw])
        out = {}
        out["src_row"] = str(src)
        out[key_col + "_raw"] = row[key_col]
        out[key_col + "_norm"] = normalize_key(row[key_col], steps)
        for mc in meta_cols:
            out[mc] = row[mc]
        if uc:
            out[uc["column"] + "_raw"] = row[uc["column"]]
        for m in measures:
            col = m["column"]
            raw = row[col].strip()
            value_text = ""
            klass = ""
            flag = ""
            sentinel_hit = None
            for s in m.get("sentinels", []):
                if raw == s["pattern"]:
                    sentinel_hit = s
                    break
            if sentinel_hit is not None:
                klass = sentinel_hit["class"]
                ledger.append(["cell_flag", src, col, klass,
                               "raw='%s'; marked %s, not imputed" % (raw, klass),
                               sentinel_hit["source"]])
            elif not is_finite_number(raw):
                klass = "unparseable"
                flag = "unparseable_value"
                value_text = raw
                ledger.append(["cell_flag", src, col, klass,
                               "raw='%s'; not numeric and no sentinel rule matched; original kept" % raw,
                               m["source"]])
            else:
                val = float(raw)
                if factor is not None and m.get("convert_units", False):
                    val = val * factor
                    if unit_raw != uc["target"]:
                        unit_conversions += 1
                        ledger.append(["unit_convert", src, col, "unit_converted",
                                       "unit '%s' -> '%s' factor=%s"
                                       % (unit_raw, uc["target"], fmt_num(factor)),
                                       uc["source"]])
                value_text = fmt_num(val)
                if val == 0 and m.get("zero_is_true"):
                    klass = "true_zero"
                    ledger.append(["cell_flag", src, col, "true_zero",
                                   "raw='%s'; numeric zero; marked true_zero, not imputed" % raw,
                                   m["source"]])
                else:
                    klass = "valid"
                bounds = m.get("bounds")
                if bounds:
                    if val > float(bounds["max"]):
                        flag = "out_of_bounds_high"
                        ledger.append(["cell_flag", src, col, flag,
                                       "value %s > max %s; original kept, flagged"
                                       % (value_text, fmt_num(float(bounds["max"]))),
                                       bounds["source"]])
                    elif val < float(bounds["min"]):
                        flag = "out_of_bounds_low"
                        ledger.append(["cell_flag", src, col, flag,
                                       "value %s < min %s; original kept, flagged"
                                       % (value_text, fmt_num(float(bounds["min"]))),
                                       bounds["source"]])
            counts[klass] += 1
            if flag:
                flag_counts[flag] += 1
            out[col] = value_text
            out[col + "_class"] = klass
            out[col + "_flag"] = flag
        cleaned_rows.append(out)

    # ---- deterministic ledger order ------------------------------------
    ledger.sort(key=lambda e: (e[1], e[2], e[0], e[3]))

    # ---- write artifacts -----------------------------------------------
    os.makedirs(args.outdir, exist_ok=True)

    cleaned_header = ["src_row", key_col + "_raw", key_col + "_norm"] + meta_cols
    if uc:
        cleaned_header.append(uc["column"] + "_raw")
    for m in measures:
        cleaned_header += [m["column"], m["column"] + "_class", m["column"] + "_flag"]
    with open(os.path.join(args.outdir, "cleaned.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(cleaned_header)
        for out in cleaned_rows:
            w.writerow([out[h] for h in cleaned_header])

    with open(os.path.join(args.outdir, "ledger.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["record", "src_row", "field", "record_class", "detail", "source"])
        for e in ledger:
            w.writerow(e)

    summary = {
        "case_id": rules["case_id"],
        "rows_input": len(raw_rows),
        "rows_output": len(cleaned_rows),
        "duplicates_dropped": len(raw_rows) - len(cleaned_rows),
        "cell_class_counts": counts,
        "flag_counts": flag_counts,
        "unit_conversions": unit_conversions,
        "aggregate_statistics": "none (population statistics are prohibited)",
    }
    with open(os.path.join(args.outdir, "summary.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    print("engine_row: OK rows_in=%d rows_out=%d ledger=%d -> %s"
          % (len(raw_rows), len(cleaned_rows), len(ledger), args.outdir))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
