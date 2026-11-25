#!/usr/bin/env python3
"""contract_check.py — pre-submission QC of result.json against the Harbor
runtime contract and the cross-lingual task's honesty requirements.

Checks (each yields pass/warn/fail with evidence):
  C1 case_id present and equal to case.json's case_id
  C2 every output_contract field present (null allowed only if the null is
     acknowledged in uncertainty or change_records)
  C3 status in {ok, partial, failed} and consistent with content
     (ok requires non-empty hits or an explicit empty-result note;
      partial/failed require non-empty uncertainty)
  C4 every hit carries a locator (locator / source_file / evidence) and
     attribution fields (source, doi, language, version) — explicit null is
     accepted only together with an attribution note
  C5 language coverage honesty: every language claimed in coverage either
     lists hits or gives an explicit evidence-backed note; no claimed
     language is silently absent
  C6 dedupe honesty: if duplicate/translation views appear in hits, a
     dedupe note must exist in change_records or coverage notes
  C7 sources non-empty and each source resolvable (file paths exist when
     they look like paths)
  C8 no fabricated-looking placeholders: DOI/title fields must not contain
     template markers (TODO, XXX, lorem, example.com)

Writes qc.json + qc_report.md. Exit 0 always; overall verdict in JSON.
"""
import argparse
import json
import os
import re
import sys

LOCATOR_KEYS = ("locator", "source_file", "evidence", "file", "path", "offsets")
ATTRIB_KEYS = ("source", "doi", "language", "version")
ATTRIB_NOTE_KEYS = ("attribution_note", "attribution", "note")
PLACEHOLDER = re.compile(r"todo|xxx+|lorem|example\.com|placeholder|待定|占位", re.I)


def check(name, ok, detail, level_ok="pass"):
    return {"check": name, "verdict": ok if isinstance(ok, str) else
            ("pass" if ok else "fail"), "detail": detail}


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def contract_keys(output_contract):
    if isinstance(output_contract, dict):
        return list(output_contract.keys())
    if isinstance(output_contract, list):
        out = []
        for item in output_contract:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict) and item.get("name"):
                out.append(item["name"])
        return out
    return []


def run_checks(case, result, base_dir=""):
    checks = []
    cid = case.get("case_id") or case.get("id")
    checks.append(check("C1 case_id match",
                        bool(cid) and result.get("case_id") == cid,
                        f"case.json={cid!r} result={result.get('case_id')!r}"))

    keys = contract_keys(case.get("output_contract"))
    missing = [k for k in keys if k not in result]
    text_blob = json.dumps(result, ensure_ascii=False)
    unack_nulls = [k for k in keys
                   if k in result and result[k] is None
                   and k not in json.dumps(result.get("uncertainty", []),
                                           ensure_ascii=False)
                   and k not in json.dumps(result.get("change_records", []),
                                           ensure_ascii=False)]
    if missing:
        checks.append(check("C2 output_contract fields", False,
                            f"missing fields: {missing}"))
    elif unack_nulls:
        checks.append(check("C2 output_contract fields", "warn",
                            f"null fields without acknowledgement: {unack_nulls}"))
    else:
        checks.append(check("C2 output_contract fields", True,
                            f"{len(keys)} contract fields present and acknowledged"))

    status = result.get("status")
    hits = result.get("hits") or []
    uncertainty = result.get("uncertainty") or []
    if status not in ("ok", "partial", "failed"):
        checks.append(check("C3 status consistency", False,
                            f"invalid status {status!r}"))
    elif status == "ok" and isinstance(hits, list) and not hits:
        note = any("empty" in str(u).lower() or "no result" in str(u).lower()
                   or "空" in str(u) for u in uncertainty)
        checks.append(check("C3 status consistency",
                            "warn" if note else False,
                            "status=ok with empty hits" +
                            (" (empty-result note present)" if note
                             else " and no justification")))
    elif status in ("partial", "failed") and not uncertainty:
        checks.append(check("C3 status consistency", False,
                            f"status={status} but uncertainty is empty"))
    else:
        checks.append(check("C3 status consistency", True, f"status={status}"))

    bad_hits = []
    if isinstance(hits, list):
        for i, h in enumerate(hits):
            if not isinstance(h, dict):
                bad_hits.append((i, "hit is not an object"))
                continue
            if not any(h.get(k) for k in LOCATOR_KEYS):
                bad_hits.append((i, "no locator/source_file/evidence"))
            for k in ATTRIB_KEYS:
                if k not in h:
                    bad_hits.append((i, f"attribution field '{k}' absent"))
                elif h[k] is None and not any(h.get(n) for n in ATTRIB_NOTE_KEYS):
                    bad_hits.append((i, f"'{k}' is null without attribution note"))
        checks.append(check("C4 hit locator & attribution",
                            not bad_hits,
                            f"{len(hits)} hits checked; problems: {bad_hits[:5]}"))
    else:
        checks.append(check("C4 hit locator & attribution", "warn",
                            "no hits list to check"))

    coverage = result.get("coverage") or {}
    cov_problems = []
    if isinstance(coverage, dict):
        for lang, info in coverage.items():
            if isinstance(info, dict):
                n = info.get("hits", info.get("count"))
                note = info.get("note") or info.get("status")
                if not n and not note:
                    cov_problems.append(f"{lang}: no hits and no note")
            elif not info:
                cov_problems.append(f"{lang}: empty coverage entry")
        checks.append(check("C5 language coverage honesty",
                            not cov_problems,
                            "; ".join(cov_problems) or
                            f"{len(coverage)} languages accounted"))
    else:
        checks.append(check("C5 language coverage honesty", "warn",
                            "no coverage object"))

    blob_low = text_blob.lower()
    mentions_versions = ("duplicate" in blob_low or "translation" in blob_low
                         or "view_type" in blob_low)
    if mentions_versions:
        has_dedupe_note = ("dedup" in blob_low or "去重" in text_blob
                           or "count once" in blob_low
                           or "countable" in blob_low)
        checks.append(check("C6 dedupe honesty",
                            "pass" if has_dedupe_note else "warn",
                            "version/duplicate views present; " +
                            ("dedupe rule documented" if has_dedupe_note
                             else "no dedupe note found")))
    else:
        checks.append(check("C6 dedupe honesty", True, "no version views claimed"))

    sources = result.get("sources") or []
    src_problems = []
    for s in sources:
        path = s.get("path") if isinstance(s, dict) else s
        if isinstance(path, str) and (path.startswith("/") or "/" in path) \
                and base_dir and not os.path.exists(path):
            src_problems.append(path)
    if not sources:
        checks.append(check("C7 sources", "warn", "sources list is empty"))
    else:
        checks.append(check("C7 sources", not src_problems,
                            f"{len(sources)} sources; unresolvable: {src_problems[:5]}"))

    placeholders = []
    def scan(obj, trail=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                scan(v, f"{trail}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                scan(v, f"{trail}[{i}]")
        elif isinstance(obj, str) and PLACEHOLDER.search(obj):
            placeholders.append(trail)
    scan(result)
    checks.append(check("C8 no placeholders", not placeholders,
                        f"placeholder-like strings at: {placeholders[:5]}"))
    return checks


def verdict(checks):
    vs = [c["verdict"] for c in checks]
    if "fail" in vs:
        return "fail"
    if "warn" in vs:
        return "pass_with_warnings"
    return "pass"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--result", default="/app/output/result.json")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    case = load_json(args.case)
    result = load_json(args.result)
    checks = run_checks(case, result, base_dir=os.getcwd())
    overall = verdict(checks)
    payload = {"overall": overall,
               "case_id": result.get("case_id"), "checks": checks}
    with open(os.path.join(args.out, "qc.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    lines = ["# result.json contract QC report", "",
             f"overall: **{overall}**", "",
             "| check | verdict | detail |", "|-|-|-|"]
    for c in checks:
        lines.append("| {n} | {v} | {d} |".format(
            n=c["check"], v=c["verdict"],
            d=str(c["detail"]).replace("|", "/")[:200]))
    with open(os.path.join(args.out, "qc_report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(json.dumps({"overall": overall,
                      "fails": [c["check"] for c in checks
                                if c["verdict"] == "fail"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
