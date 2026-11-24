#!/usr/bin/env python3
"""audit_translation.py — deterministic fact-preservation audit.

Given facts.jsonl (from build_fact_ledger.py) and a translation file, check
that every ledger fact survives translation. Writes audit_report.json and
exits NON-ZERO if any fact is `missing` or `altered`.

Verdicts per fact:
  preserved   fact found verbatim or in a digit-exact rewrite (e.g. thousand
              separators added/removed, flexible whitespace)
  normalized  acceptable cross-locale rewrite, always listed explicitly:
              万/亿 <-> ×10^4/×10^8 vs million/billion, scientific-notation
              swaps, label translation Figure 2 -> 图 2, unit rendered in the
              target language (USD -> 美元, years -> 年)
  missing     no trace of the fact value in the translation
  altered     heuristic: a translation number of the same digit length
              differs from the fact value in exactly one digit (likely a
              mistranscription); percentages written as decimal fractions
The audit also reports `added`: numeric values in the translation with no
counterpart in the source ledger (warnings; do not affect the exit code).

Normalization rules: thousand separators ignored; percents must stay
percents; ranges must keep both endpoints and a connector (– — - ~ 至 到 to);
万 = ×10^4, 亿 = ×10^8, million = ×10^6, billion = ×10^9.

Stdlib only. Deterministic.

Exit codes: 0 = no missing/altered facts; 1 = missing or altered facts;
2 = usage error.
"""
import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, timezone

CONNECTORS = ["–", "—", "-", "~", "～", "至", "到", "to"]
RANGE_WINDOW = 20  # max chars between range endpoints in the translation

UNIT_EQUIV = {
    "year": "年", "years": "年",
    "hour": "小时", "hours": "小时",
    "day": "天", "days": "天",
    "week": "周", "weeks": "周",
    "month": "个月", "months": "个月",
    "usd": "美元", "eur": "欧元", "cny": "人民币", "rmb": "人民币",
    "jpy": "日元", "°c": "°C", "°f": "°F",
}

TNUM = re.compile(
    r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
    r"(?:\s*[×xX]\s*10\^?-?\d+|[eE][+-]?\d+)?"
    r"(?:\s*(?:million|billion|千万|百万|亿|万))?")

MULTIPLIERS = {
    "million": 1e6, "billion": 1e9,
    "万": 1e4, "亿": 1e8, "百万": 1e6, "千万": 1e7,
}


# ---------------------------------------------------------------- helpers
def fmt(v):
    v = float(v)
    return str(int(v)) if v.is_integer() else f"{v:.10g}"


def key(v):
    return f"{float(v):.6g}"


def parse_num(s):
    s = s.strip().replace(",", "")
    m = re.match(r"^(.*?)\s*[×xX]\s*10\^?(-?\d+)$", s)
    if m:
        return float(m.group(1)) * 10 ** int(m.group(2))
    m = re.match(r"^(.*?)([eE][+-]?\d+)$", s)
    if m and re.fullmatch(r"[\d.]+", m.group(1)):
        return float(m.group(1)) * 10 ** int(m.group(2))
    m = re.match(r"^(.*?)\s*(million|billion|千万|百万|亿|万)$", s)
    if m:
        return parse_num(m.group(1)) * MULTIPLIERS[m.group(2)]
    return float(s)


def digits_only(s):
    return re.sub(r"\D", "", s)


def flex_regex(raw):
    """Whitespace-flexible regex for a raw surface string."""
    return r"\s*".join(re.escape(tok) for tok in raw.split())


def find_cand(text, cand):
    """Return start index of candidate in text, or -1.
    Pure-digit candidates are matched with numeric boundaries so '14'
    does not match inside '2014' or '1,400'."""
    if re.fullmatch(r"[\d.,]+", cand):
        rx = re.compile(r"(?<![\d.,])" + re.escape(cand) + r"(?![\d.,])")
    else:
        rx = re.compile(flex_regex(cand))
    m = rx.search(text)
    return m.start() if m else -1


def find_all_cand(text, cand):
    if re.fullmatch(r"[\d.,]+", cand):
        rx = re.compile(r"(?<![\d.,])" + re.escape(cand) + r"(?![\d.,])")
    else:
        rx = re.compile(flex_regex(cand))
    return [(m.start(), m.end()) for m in rx.finditer(text)]


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def value_candidates(v, raw):
    """(exact_tier, locale_tier) candidate strings for a numeric value."""
    exact, locale = [], []

    def add(lst, s):
        if s and s not in lst:
            lst.append(s)

    add(exact, raw)
    add(exact, raw.replace(",", ""))
    add(exact, fmt(v))
    if float(v).is_integer() and abs(v) >= 1000:
        add(exact, f"{int(v):,}")
    if v != 0:
        # spaced variants are added because find_cand's whitespace-flexible
        # regex then covers both "250万" and "250 万"
        if v >= 1e8:
            add(locale, f"{v / 1e8:.10g}亿")
            add(locale, f"{v / 1e8:.10g} 亿")
        if v >= 1e4:
            add(locale, f"{v / 1e4:.10g}万")
            add(locale, f"{v / 1e4:.10g} 万")
        if v >= 1e6:
            add(locale, f"{v / 1e6:.10g} million")
        if v >= 1e9:
            add(locale, f"{v / 1e9:.10g} billion")
        exp = math.floor(math.log10(abs(v)))
        mant = f"{v / 10 ** exp:.6g}"
        add(locale, f"{mant} × 10^{exp}")
        add(locale, f"{mant}×10^{exp}")
        add(locale, f"{mant}e{exp}")
        add(locale, f"{mant}E{exp}")
    locale = [c for c in locale if c not in exact]
    return exact, locale


def unit_variants(unit):
    variants = {unit}
    eq = UNIT_EQUIV.get(unit.lower())
    if eq:
        variants.add(eq)
    return variants


def translation_numbers(text):
    """All numeric values mentioned in the translation: [(raw, value)]."""
    out = []
    for m in TNUM.finditer(text):
        try:
            out.append((m.group(0), parse_num(m.group(0))))
        except ValueError:
            continue
    return out


def ledger_value_keys(facts):
    keys = set()
    for f in facts:
        t = f["type"]
        try:
            if t in ("number", "percent", "year", "sample_size", "unit_value"):
                keys.add(key(float(f["normalized"])))
            elif t == "range":
                lo, hi = f["normalized"].split("-", 1)
                keys.add(key(float(lo)))
                keys.add(key(float(hi)))
            elif t == "citation_marker":
                for d in re.findall(r"\d+", f["normalized"]):
                    keys.add(key(float(d)))
            elif t in ("figure_ref", "table_ref"):
                m = re.match(r"\d+", f["normalized"])
                if m:
                    keys.add(key(float(m.group(0))))
        except ValueError:
            continue
    return keys


def altered_or_missing(fact, tnumbers):
    """Heuristic: same-length digit string differing in exactly one digit =>
    likely mistranscribed (altered); otherwise missing."""
    targets = {digits_only(fact["raw"])}
    try:
        targets.add(digits_only(fmt(float(fact["normalized"]))))
    except (ValueError, OverflowError):
        pass
    targets.discard("")
    for raw_t, _val in tnumbers:
        d2 = digits_only(raw_t)
        for d1 in targets:
            if (len(d1) == len(d2) and d1 != d2
                    and sum(a != b for a, b in zip(d1, d2)) == 1):
                return "altered"
    return "missing"


# ------------------------------------------------------- per-type checks
def check_numeric(fact, text, tnumbers, v):
    exact, locale = value_candidates(v, fact["raw"])
    for cand in exact:
        pos = find_cand(text, cand)
        if pos >= 0:
            return "preserved", f"exact/digit-exact form '{cand}'", pos
    for cand in locale:
        pos = find_cand(text, cand)
        if pos >= 0:
            return "normalized", f"cross-locale form '{cand}'", pos
    verdict = altered_or_missing(fact, tnumbers)
    return verdict, ("possible mistranscription: a same-length digit string "
                     "differs by one digit" if verdict == "altered"
                     else "value not found"), None


def check_percent(fact, text, tnumbers, v):
    raw = fact["raw"]
    cands = [raw, raw.replace("%", " %"), raw.replace("%", "％"),
             raw.replace("%", " ％")]
    for cand in cands:
        pos = find_cand(text, cand)
        if pos >= 0:
            return "preserved", f"percent kept as '{cand}'", pos
    alt = f"{fmt(v)}%"
    for cand in (alt, alt.replace("%", " %"), alt.replace("%", "％")):
        pos = find_cand(text, cand)
        if pos >= 0:
            return "normalized", f"percent rewritten as '{cand}'", pos
    frac = f"{v / 100:.10g}"
    pos = find_cand(text, frac)
    if pos >= 0:
        return "altered", f"percent written as fraction '{frac}'", pos
    verdict = altered_or_missing(fact, tnumbers)
    return verdict, ("possible mistranscription: a same-length digit string "
                     "differs by one digit" if verdict == "altered"
                     else "percent value not found"), None


def check_year(fact, text, tnumbers):
    pos = find_cand(text, fact["normalized"])
    if pos >= 0:
        return "preserved", "year present", pos
    return "missing", "year not found", None


def check_unit_value(fact, text, tnumbers, v):
    unit = fact["unit"] or ""
    idx = fact["raw"].rfind(unit)
    num_raw = fact["raw"][:idx].strip() if idx > 0 else fact["raw"]
    exact, locale = value_candidates(v, num_raw)
    for tier, cands in (("preserved", exact), ("normalized", locale)):
        for cand in cands:
            pos = find_cand(text, cand)
            if pos < 0:
                continue
            line_start = text.rfind("\n", 0, pos) + 1
            line_end = text.find("\n", pos)
            line_end = len(text) if line_end < 0 else line_end
            line = text[line_start:line_end]
            if any(u in line for u in unit_variants(unit)):
                note = (f"value '{cand}' + unit '{unit}'"
                        if tier == "preserved"
                        else f"cross-locale value '{cand}' + unit '{unit}'")
                return tier, note, pos
            return "normalized", (f"value '{cand}' kept but unit '{unit}' "
                                  "not found on the same line"), pos
    verdict = altered_or_missing(fact, tnumbers)
    return verdict, ("possible mistranscription: a same-length digit string "
                     "differs by one digit" if verdict == "altered"
                     else "value not found"), None


def check_range(fact, text, tnumbers):
    lo_raw, hi_raw = fact.get("endpoints",
                              fact["normalized"].split("-", 1))
    lo_v, hi_v = float(fact["normalized"].split("-", 1)[0]), \
        float(fact["normalized"].split("-", 1)[1])
    tiers = []
    lo_ex, lo_loc = value_candidates(lo_v, lo_raw)
    hi_ex, hi_loc = value_candidates(hi_v, hi_raw)
    tiers.append(("preserved", lo_ex, hi_ex))
    tiers.append(("normalized", lo_ex + lo_loc, hi_ex + hi_loc))
    for tier, lo_cands, hi_cands in tiers:
        for lc in lo_cands:
            for lo_s, lo_e in find_all_cand(text, lc):
                for hc in hi_cands:
                    for hi_s, _hi_e in find_all_cand(text, hc):
                        if hi_s < lo_e or hi_s - lo_e > RANGE_WINDOW:
                            continue
                        gap = text[lo_e:hi_s]
                        if "。" in gap or ". " in gap:
                            continue
                        if any(c in gap for c in CONNECTORS):
                            note = (f"range '{lc}–{hc}' with connector"
                                    if tier == "preserved"
                                    else f"range in cross-locale form "
                                         f"'{lc}–{hc}'")
                            return tier, note, lo_s
    lo_found = any(find_cand(text, c) >= 0 for c in lo_ex + lo_loc)
    hi_found = any(find_cand(text, c) >= 0 for c in hi_ex + hi_loc)
    if lo_found and hi_found:
        pos = find_cand(text, (lo_ex + lo_loc)[0])
        return "normalized", "both endpoints present but range connector " \
                             "changed or lost", pos
    verdict = altered_or_missing(fact, tnumbers)
    return verdict, ("possible mistranscription: a same-length digit string "
                     "differs by one digit" if verdict == "altered"
                     else "range endpoint(s) not found"), None


def check_citation(fact, text):
    norm = fact["normalized"]
    if fact["raw"].startswith("["):  # bracket citation [12] / [3–5]
        inner = norm
        if "-" in inner:
            a, b = inner.split("-", 1)
            rx = re.compile(r"[\[【]\s*" + re.escape(a) + r"\s*[–\-—]\s*"
                            + re.escape(b) + r"\s*[\]】]")
        else:
            nums = [n.strip() for n in inner.split(",")]
            rx = re.compile(r"[\[【]\s*" +
                            r"\s*,\s*".join(re.escape(n) for n in nums) +
                            r"\s*[\]】]")
        m = rx.search(text)
        if m:
            return "preserved", "bracket citation intact", m.start()
        if all(find_cand(text, n) >= 0 for n in re.findall(r"\d+", inner)):
            return "normalized", "citation numbers present but bracket " \
                                 "style changed", None
        return "missing", "bracket citation not found", None
    if fact["raw"].startswith("^"):  # superscript-style ^12
        for cand in (fact["raw"], f"[{norm}]"):
            pos = find_cand(text, cand)
            if pos >= 0:
                return ("preserved" if cand == fact["raw"] else "normalized",
                        f"superscript citation rendered as '{cand}'", pos)
        return "missing", "superscript citation not found", None
    # author-year: (Smith, 2020) / Smith et al. (2021)
    surname = norm.split(",")[0].strip()
    year_m = re.search(r"(?:19|20)\d{2}", norm)
    year = year_m.group(0) if year_m else ""
    pos_s = text.find(surname)
    pos_y = find_cand(text, year) if year else -1
    if pos_s >= 0 and pos_y >= 0:
        return "preserved", f"author-year '{surname}, {year}' present", pos_s
    if pos_y >= 0:
        return "normalized", "year present but author name missing/rewritten", \
            pos_y
    return "missing", "author-year citation not found", None


def check_ref(fact, text):
    num = re.escape(fact["normalized"])
    if fact["type"] == "figure_ref":
        rx = re.compile(r"(?:Figure|Fig\.?|图|圖)\s*" + num + r"(?!\d)")
    else:
        rx = re.compile(r"(?:Table|表)\s*" + num + r"(?!\d)")
    m = rx.search(text)
    if m:
        return "preserved", f"reference intact as '{m.group(0)}'", m.start()
    pos = find_cand(text, fact["normalized"])
    if pos >= 0:
        return "normalized", "number present but Figure/Table label dropped", \
            pos
    return "missing", "reference not found", None


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(
        description="Audit a translation against facts.jsonl")
    ap.add_argument("facts", help="facts.jsonl from build_fact_ledger.py")
    ap.add_argument("translation", help="translation file (text/markdown)")
    ap.add_argument("-o", "--output", default=None,
                    help="report path (default <facts-dir>/audit_report.json)")
    args = ap.parse_args()

    if not os.path.isfile(args.facts) or not os.path.isfile(args.translation):
        print("audit_translation: ERROR: input file not found",
              file=sys.stderr)
        sys.exit(2)
    out = args.output or os.path.join(os.path.dirname(args.facts),
                                      "audit_report.json")

    facts = []
    with open(args.facts, "r", encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if ln:
                facts.append(json.loads(ln))
    with open(args.translation, "r", encoding="utf-8") as fh:
        text = fh.read()

    tnumbers = translation_numbers(text)
    verdicts = []
    for f in facts:
        t = f["type"]
        if t == "percent":
            verdict, note, pos = check_percent(
                f, text, tnumbers, float(f["normalized"]))
        elif t == "year":
            verdict, note, pos = check_year(f, text, tnumbers)
        elif t == "unit_value":
            verdict, note, pos = check_unit_value(
                f, text, tnumbers, float(f["normalized"]))
        elif t == "range":
            verdict, note, pos = check_range(f, text, tnumbers)
        elif t == "citation_marker":
            verdict, note, pos = check_citation(f, text)
        elif t in ("figure_ref", "table_ref"):
            verdict, note, pos = check_ref(f, text)
        else:  # number, sample_size
            verdict, note, pos = check_numeric(
                f, text, tnumbers, float(f["normalized"]))
        verdicts.append({
            "id": f["id"], "type": t, "raw": f["raw"],
            "source_page": f["page"], "source_line": f["line"],
            "verdict": verdict, "detail": note,
            "translation_line": line_of(text, pos) if pos is not None else None,
        })

    ledger_keys = ledger_value_keys(facts)
    added, seen_added = [], set()
    for raw_t, val in tnumbers:
        k = key(val)
        if k in ledger_keys:
            continue
        where = line_of(text, text.find(raw_t))
        if (k, where) in seen_added:
            continue
        seen_added.add((k, where))
        added.append({"raw": raw_t, "value": fmt(val),
                      "translation_line": where,
                      "note": "numeric value with no source counterpart"})

    counts = {"preserved": 0, "normalized": 0, "missing": 0, "altered": 0}
    for v in verdicts:
        counts[v["verdict"]] += 1
    report = {
        "summary": {
            "total_facts": len(verdicts),
            "preserved": counts["preserved"],
            "normalized": counts["normalized"],
            "missing": counts["missing"],
            "altered": counts["altered"],
            "added": len(added),
        },
        "verdicts": verdicts,
        "added": added,
        "exit_meaning": "exit 1 if missing>0 or altered>0; "
                        "'normalized' and 'added' are listed but non-fatal",
        "generated_utc": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    s = report["summary"]
    print(f"audit_translation: total={s['total_facts']} "
          f"preserved={s['preserved']} normalized={s['normalized']} "
          f"missing={s['missing']} altered={s['altered']} "
          f"added={s['added']} -> {out}")
    if s["missing"] or s["altered"]:
        print("audit_translation: FAIL (missing or altered facts)",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
