#!/usr/bin/env python3
"""warden.py -- audit a retrieval run directory; make fabrication unshippable.

The warden does not trust the run. It re-hashes every evidence file, re-scans
their bytes for every identifier the run claims, independently recomputes the
pipeline counts, and validates result.json against the case contract. It NEVER
edits candidates or evidence (that would be laundering); the only repair it
offers is --fix-result, which rewrites result.json into an honest state.

Four gates:
  ANTI-FABRICATION  every DOI / normalized title claimed by candidates.json,
                    candidates.md and result.json must literally appear in the
                    evidence copies; evidence file hashes must match their
                    names and what candidates claim. Miss => FABRICATION_SUSPECT
                    (ERROR).
  FLOW              identified / after-dedup / included counts are recomputed
                    from the evidence copies and compared with run_log.jsonl;
                    every excluded record must carry a reason code.
                    Mismatch => COUNT_MISMATCH / EXCLUSION_* (ERROR).
  CONTRACT          result.json exists, case_id matches, every output_contract
                    field is present, non-empty, and points to an existing file
                    under --out; status in {success, partial, failed};
                    success <=> empty uncertainty, partial => non-empty
                    uncertainty (honest partial). Violation => ERROR.
  ANOMALY           WARN only: zero-hit query terms, snapshots with zero
                    records, dedup ratio > 50%, single-source pools.

Usage:
  warden.py --case /input/case.json [--run /app/work/run] [--out /app/output]
            [--fix-result]

Writes <out>/audit_report.md and <out>/audit_report.json.
Exit 0 when the overall GATE is PASS (zero ERRORs), 1 otherwise.
A FAIL report is a deliverable too: it is the honest answer.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'\]\)<>,;]+")

GATES = ("ANTI-FABRICATION", "FLOW", "CONTRACT", "ANOMALY")


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha256_12(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def norm_text(s):
    """Lowercase alnum-only squash used for presence checks."""
    return re.sub(r"[^a-z0-9一-鿿]", "", (s or "").lower())


def norm_doi(d):
    d = (d or "").strip().lower()
    for pre in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.startswith(pre):
            d = d[len(pre):]
    return d.rstrip(".")


def classify(payload):
    """Independent re-implementation of snapshot shape detection."""
    if isinstance(payload, dict):
        m = payload.get("message")
        if isinstance(m, dict) and isinstance(m.get("items"), list):
            return "crossref", m["items"]
        r = payload.get("resultList")
        if isinstance(r, dict) and isinstance(r.get("result"), list):
            return "europepmc", r["result"]
        if isinstance(payload.get("results"), list):
            return "openalex", payload["results"]
        if isinstance(payload.get("records"), list):
            return "generic-records", payload["records"]
    return None, []


def record_keys(raw_list):
    """Dedup keys for a raw record list (DOI first, else normalized title)."""
    keys = []
    for raw in raw_list:
        raw = raw if isinstance(raw, dict) else {}
        doi = norm_doi(raw.get("DOI") or raw.get("doi") or "")
        if doi:
            keys.append("doi:" + doi)
        else:
            title = raw.get("title") or raw.get("display_name") or ""
            if isinstance(title, list):
                title = title[0] if title else ""
            keys.append("title:" + norm_text(str(title)))
    return keys


class Audit:
    def __init__(self):
        self.findings = []

    def add(self, gate, severity, code, message, recheck):
        self.findings.append({"gate": gate, "severity": severity, "code": code,
                              "message": message, "how_to_recheck": recheck})

    def err(self, gate, code, msg, recheck):
        self.add(gate, "ERROR", code, msg, recheck)

    def warn(self, gate, code, msg, recheck):
        self.add(gate, "WARN", code, msg, recheck)


def load_log(run_dir):
    entries = []
    path = os.path.join(run_dir, "run_log.jsonl")
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", required=True)
    ap.add_argument("--run", default="/app/work/run")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--fix-result", action="store_true",
                    help="rewrite <out>/result.json into an honest state; "
                         "never touches the run directory")
    args = ap.parse_args()
    a = Audit()

    case = json.load(open(args.case, encoding="utf-8"))
    case_id = case.get("case_id") or case.get("id") or "UNKNOWN"
    oc = case.get("output_contract") or case.get("outputContract") or {}
    fields = list(oc.keys()) if isinstance(oc, dict) else [
        x["name"] if isinstance(x, dict) and "name" in x else str(x)
        for x in oc] if isinstance(oc, list) else []

    run_dir = args.run
    out_dir = args.out
    ev_dir = os.path.join(run_dir, "evidence")
    os.makedirs(out_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # collect evidence copies (the only ground truth the warden accepts)
    # ------------------------------------------------------------------
    evidence = {}  # copy_name -> {"sha256_12", "text", "norm"}
    if os.path.isdir(ev_dir):
        for fn in sorted(os.listdir(ev_dir)):
            p = os.path.join(ev_dir, fn)
            if not os.path.isfile(p):
                continue
            digest = sha256_12(p)
            raw = open(p, "rb").read()
            text = raw.decode("utf-8", errors="replace")
            evidence[fn] = {"sha256_12": digest, "text": text,
                            "norm": norm_text(text), "bytes": len(raw)}
            if not fn.startswith(digest):
                a.err("ANTI-FABRICATION", "EVIDENCE_HASH_MISMATCH",
                      "evidence file %r re-hashes to %s, not the %s prefix in "
                      "its name" % (fn, digest, fn.split("__")[0]),
                      "run `shasum -a 256 %s` and compare the first 12 hex "
                      "chars with the file name" % p)
    else:
        a.err("ANTI-FABRICATION", "EVIDENCE_DIR_MISSING",
              "no evidence directory at %s -- nothing can be verified" % ev_dir,
              "check that the run wrote byte-identical snapshot copies to "
              "<work>/run/evidence/")

    # claimed identifiers from candidates.json
    cand_path = os.path.join(run_dir, "candidates.json")
    candidates = []
    claimed = []  # (kind, value, origin)
    if os.path.isfile(cand_path):
        try:
            cj = json.load(open(cand_path, encoding="utf-8"))
            candidates = cj.get("candidates") or []
        except json.JSONDecodeError as exc:
            a.err("ANTI-FABRICATION", "CANDIDATES_UNPARSEABLE",
                  "candidates.json is not valid JSON: %s" % exc,
                  "open %s and check its syntax" % cand_path)
    else:
        a.err("ANTI-FABRICATION", "CANDIDATES_MISSING",
              "no candidates.json in the run directory",
              "check %s" % cand_path)

    for c in candidates:
        origin = "candidates.json rank=%s" % c.get("rank", "?")
        if c.get("doi"):
            claimed.append(("doi", c["doi"], origin))
        if c.get("title"):
            claimed.append(("title", c["title"], origin))

    # DOIs mentioned anywhere in candidates.md
    cmd_path = os.path.join(run_dir, "candidates.md")
    if os.path.isfile(cmd_path):
        md = open(cmd_path, encoding="utf-8").read()
        for m in DOI_RE.findall(md):
            claimed.append(("doi", m, "candidates.md"))
    else:
        a.warn("ANTI-FABRICATION", "CANDIDATES_MD_MISSING",
               "no candidates.md in the run directory",
               "check %s" % cmd_path)

    # DOIs mentioned anywhere in result.json
    result_path = os.path.join(out_dir, "result.json")
    result = None
    if os.path.isfile(result_path):
        try:
            result = json.load(open(result_path, encoding="utf-8"))
            rtext = open(result_path, encoding="utf-8").read()
            for m in DOI_RE.findall(rtext):
                claimed.append(("doi", m, "result.json"))
        except json.JSONDecodeError as exc:
            a.err("CONTRACT", "RESULT_UNPARSEABLE",
                  "result.json is not valid JSON: %s" % exc,
                  "open %s and check its syntax" % result_path)

    # ---- ANTI-FABRICATION: presence checks ------------------------------
    seen = set()
    for kind, value, origin in claimed:
        if kind == "doi":
            probe = norm_text(norm_doi(value))  # squash like the evidence text
            label = "DOI %s" % norm_doi(value)
        else:
            probe = norm_text(value)
            label = "title %r" % value[:80]
        if (kind, probe) in seen or not probe:
            continue
        seen.add((kind, probe))
        hits = [fn for fn, e in evidence.items() if probe in e["norm"]]
        if not hits:
            if kind == "doi":
                hint = "grep -riF %r %s  (expect zero matches)" % (
                    norm_doi(value), ev_dir)
            else:
                hint = ("grep -riF %r %s  (expect zero matches; the warden "
                        "checks the title with all punctuation/case removed)"
                        % (" ".join(str(value).split()[:4]), ev_dir))
            a.err("ANTI-FABRICATION", "FABRICATION_SUSPECT",
                  "%s claimed by %s appears in NO evidence copy -- "
                  "this identifier cannot be verified and must not ship"
                  % (label, origin), hint)

    # claimed evidence pointers must match reality
    for c in candidates:
        ev = c.get("evidence") or {}
        name = ev.get("copy_name") or ""
        claimed_hash = ev.get("sha256_12") or ""
        if not name:
            a.err("ANTI-FABRICATION", "PROVENANCE_MISSING",
                  "candidate rank=%s (%s) carries no evidence pointer"
                  % (c.get("rank", "?"), (c.get("title") or "")[:60]),
                  "inspect the candidate entry in %s" % cand_path)
            continue
        if name not in evidence:
            a.err("ANTI-FABRICATION", "EVIDENCE_COPY_MISSING",
                  "candidate rank=%s points to evidence copy %r which does "
                  "not exist" % (c.get("rank", "?"), name),
                  "ls %s" % ev_dir)
        elif claimed_hash and evidence[name]["sha256_12"] != claimed_hash:
            a.err("ANTI-FABRICATION", "HASH_CLAIM_MISMATCH",
                  "candidate rank=%s claims sha256_12=%s for %s but re-hash "
                  "gives %s" % (c.get("rank", "?"), claimed_hash, name,
                                evidence[name]["sha256_12"]),
                  "run `shasum -a 256 %s`" % os.path.join(ev_dir, name))

    # ---- FLOW: independent recomputation ---------------------------------
    log = load_log(run_dir)
    prisma = next((e for e in reversed(log) if e.get("step") == "prisma"), None)
    excl_entry = next((e for e in reversed(log)
                       if e.get("step") == "exclusions"), None)
    exclusions = ((excl_entry or {}).get("notes") or {}).get("items") or []

    all_keys = []           # identified keys, in evidence order
    per_snapshot = []       # (copy_name, source_type, n_records)
    parse_failures = []
    for fn, e in sorted(evidence.items()):
        try:
            payload = json.loads(e["text"])
        except json.JSONDecodeError:
            parse_failures.append(fn)
            per_snapshot.append((fn, "unparseable", 0))
            continue
        stype, raw_list = classify(payload)
        per_snapshot.append((fn, stype or "unrecognized", len(raw_list)))
        all_keys.extend(record_keys(raw_list))
    identified = len(all_keys)
    deduped = len(set(all_keys))
    included = len(candidates)
    recomputed = {"identified": identified, "after_dedup": deduped,
                  "included": included}

    if prisma is None:
        a.err("FLOW", "PRISMA_MISSING",
              "run_log.jsonl has no 'prisma' step -- the run did not account "
              "for its own flow",
              "inspect %s" % os.path.join(run_dir, "run_log.jsonl"))
    else:
        reported = prisma.get("counts") or {}
        for k, v in recomputed.items():
            if k in reported and reported[k] != v:
                a.err("FLOW", "COUNT_MISMATCH",
                      "run_log reports %s=%s but independent recomputation "
                      "from the evidence copies gives %s"
                      % (k, reported[k], v),
                      "re-parse every file in %s and count records / unique "
                      "dedup keys / candidates by hand" % ev_dir)

    included_keys = set()
    for c in candidates:
        if c.get("dedup_key"):
            included_keys.add(c["dedup_key"])
        elif c.get("doi"):
            included_keys.add("doi:" + norm_doi(c["doi"]))
        elif c.get("title"):
            included_keys.add("title:" + norm_text(c["title"]))
    excl_keys = {}
    for item in exclusions:
        k = item.get("key")
        if not item.get("reason"):
            a.err("FLOW", "EXCLUSION_WITHOUT_REASON",
                  "exclusion entry for key %r has no reason code" % k,
                  "inspect the 'exclusions' step in run_log.jsonl")
        if k:
            excl_keys[k] = item.get("reason")
    missing = set(all_keys) - included_keys - set(excl_keys)
    extra = set(excl_keys) - set(all_keys)
    if missing:
        a.err("FLOW", "EXCLUSION_LEDGER_GAP",
              "%d identified record(s) are neither included nor excluded "
              "with a reason: %s" % (len(missing), sorted(missing)[:5]),
              "recompute dedup keys from the evidence copies and diff "
              "against candidates + the exclusions ledger")
    if extra:
        a.err("FLOW", "EXCLUSION_LEDGER_PHANTOM",
              "%d exclusion ledger key(s) match no identified record: %s"
              % (len(extra), sorted(extra)[:5]),
              "same recomputation as above")

    # ---- CONTRACT ----------------------------------------------------------
    if result is None and not os.path.isfile(result_path):
        a.err("CONTRACT", "RESULT_MISSING",
              "no result.json at %s" % result_path,
              "run make_result.py or warden --fix-result")
    elif result is not None:
        if result.get("case_id") != case_id:
            a.err("CONTRACT", "CASE_ID_MISMATCH",
                  "result.json case_id=%r but case.json says %r"
                  % (result.get("case_id"), case_id),
                  "diff the two files")
        out_real = os.path.realpath(out_dir)
        for f in fields:
            v = result.get(f)
            if v in (None, "", [], {}):
                a.err("CONTRACT", "CONTRACT_FIELD_EMPTY",
                      "output_contract field %r is missing or empty" % f,
                      "check key %r in %s" % (f, result_path))
            elif isinstance(v, str) and v.startswith("/"):
                if not os.path.isfile(v):
                    a.err("CONTRACT", "CONTRACT_PATH_DANGLING",
                          "field %r points to missing file %s" % (f, v),
                          "check that the file exists")
                elif not os.path.realpath(v).startswith(out_real + os.sep) \
                        and os.path.realpath(v) != out_real:
                    a.err("CONTRACT", "CONTRACT_PATH_OUTSIDE_OUTPUT",
                          "field %r points outside the output dir: %s" % (f, v),
                          "deliverables must live under %s" % out_dir)
        status = result.get("status")
        if status not in ("success", "partial", "failed"):
            a.err("CONTRACT", "STATUS_INVALID",
                  "status must be success|partial|failed, got %r" % status,
                  "check key 'status' in %s" % result_path)
        unc = result.get("uncertainty") or []
        if status == "success" and unc:
            a.err("CONTRACT", "SUCCESS_WITH_UNCERTAINTY",
                  "status=success but uncertainty is non-empty (%d item(s)) "
                  "-- either resolve them or downgrade to partial" % len(unc),
                  "check key 'uncertainty' in %s" % result_path)
        if status == "partial" and not unc:
            a.err("CONTRACT", "PARTIAL_WITHOUT_UNCERTAINTY",
                  "status=partial but uncertainty is empty -- a partial "
                  "result must say what is missing",
                  "fill key 'uncertainty' in %s" % result_path)

    # ---- ANOMALY (WARN only) ------------------------------------------------
    score_entry = next((e for e in reversed(log) if e.get("step") == "score"),
                       None)
    zero_hits = ((score_entry or {}).get("notes") or {}).get("zero_hit_terms")
    if zero_hits:
        a.warn("ANOMALY", "ZERO_HIT_TERMS",
               "query term(s) matched no record: %s -- honest coverage gap, "
               "belongs in uncertainty" % ", ".join(zero_hits),
               "grep each term across %s" % ev_dir)
    for fn, stype, n in per_snapshot:
        if n == 0:
            a.warn("ANOMALY", "EMPTY_SNAPSHOT",
                   "snapshot %s parsed to zero records (%s)"
                   % (fn, stype),
                   "open the file and check whether it is a legitimate empty "
                   "page or a failed query")
    if identified and (identified - deduped) / float(identified) > 0.5:
        a.warn("ANOMALY", "HIGH_DEDUP_RATIO",
               "dedup removed %.0f%% of identified records (%d -> %d) -- "
               "pool may be near-duplicate snapshots"
               % (100.0 * (identified - deduped) / identified,
                  identified, deduped),
               "inspect the 'dedup' step notes in run_log.jsonl")
    source_types = {s for _f, s, n in per_snapshot if n > 0}
    if len(evidence) <= 1 or len(source_types) <= 1:
        a.warn("ANOMALY", "SINGLE_SOURCE_POOL",
               "evidence pool has %d file(s) / %d source type(s) -- results "
               "rest on a single source" % (len(evidence),
                                            max(len(source_types), 0)),
               "ls %s and note the source_type of each snapshot" % ev_dir)

    # ------------------------------------------------------------------
    # report
    # ------------------------------------------------------------------
    n_err = sum(1 for f in a.findings if f["severity"] == "ERROR")
    n_warn = sum(1 for f in a.findings if f["severity"] == "WARN")
    overall = "PASS" if n_err == 0 else "FAIL"

    gate_status = {}
    for g in GATES:
        gate_status[g] = "FAIL" if any(
            f["gate"] == g and f["severity"] == "ERROR"
            for f in a.findings) else "PASS"

    report = {
        "generated_by": "retrieval-run-warden warden.py (offline, stdlib)",
        "ts": utcnow(), "case_id": case_id, "run_dir": os.path.abspath(run_dir),
        "overall_gate": overall, "errors": n_err, "warnings": n_warn,
        "gate_status": gate_status, "recomputed_counts": recomputed,
        "evidence_files": {fn: {"sha256_12": e["sha256_12"],
                                "bytes": e["bytes"]}
                           for fn, e in sorted(evidence.items())},
        "findings": a.findings,
    }
    with open(os.path.join(out_dir, "audit_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    lines = ["# Warden audit report — case %s" % case_id, "",
             "- run audited: `%s`" % os.path.abspath(run_dir),
             "- timestamp: %s" % report["ts"],
             "- **overall GATE: %s** (ERRORs: %d, WARNs: %d)"
             % (overall, n_err, n_warn), "",
             "Every finding below names its evidence and how to re-check it "
             "by hand. The warden never modified the run directory; only "
             "result.json may have been rewritten (see --fix-result).", "",
             "## Gate summary", "",
             "| gate | status |", "|-|-|"]
    for g in GATES:
        lines.append("| %s | %s |" % (g, gate_status[g]))
    lines += ["", "## Recomputed counts (independent of run_log.jsonl)", "",
              "- identified (records parsed from evidence copies): %d"
              % identified,
              "- after_dedup (unique DOI/title keys): %d" % deduped,
              "- included (candidates shipped): %d" % included, "",
              "## Findings", ""]
    if not a.findings:
        lines.append("No findings. Every claim was found in the evidence, "
                     "every count recomputed, the contract validated.")
    for f in a.findings:
        lines.append("### [%s] %s — %s" % (f["severity"], f["gate"], f["code"]))
        lines.append("- %s" % f["message"])
        lines.append("- re-check by hand: %s" % f["how_to_recheck"])
        lines.append("")
    lines += ["## Evidence pool (re-hashed during this audit)", ""]
    for fn, e in sorted(evidence.items()):
        lines.append("- `%s` sha256_12=%s bytes=%d"
                     % (fn, e["sha256_12"], e["bytes"]))
    lines.append("")
    with open(os.path.join(out_dir, "audit_report.md"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(lines))

    # ------------------------------------------------------------------
    # optional: repair result.json into an honest state
    # ------------------------------------------------------------------
    if args.fix_result:
        result = result if isinstance(result, dict) else {}
        result["case_id"] = case_id
        hints = [
            (("candidate", "literature", "papers", "ranked", "results"),
             ["candidates.md", "run/candidates.md"]),
            (("run", "log", "trace", "pipeline", "flow", "screening"),
             ["run_log.jsonl", "run/run_log.jsonl"]),
            (("audit", "warden", "gate", "integrity", "status", "report",
              "uncertainty", "state"),
             ["audit_report.md"]),
        ]
        # stage run artifacts into the output dir (copies, never edits)
        import shutil
        for fn in ("candidates.md", "run_log.jsonl"):
            src = os.path.join(run_dir, fn)
            dst = os.path.join(out_dir, fn)
            if os.path.isfile(src) and not os.path.isfile(dst):
                shutil.copyfile(src, dst)
        for f in fields:
            low = f.lower()
            for keys, rels in hints:
                if any(k in low for k in keys):
                    for rel in rels:
                        p = os.path.join(out_dir, rel)
                        if os.path.isfile(p):
                            result[f] = p
                            break
                    if result.get(f):
                        break
        errors = [f2 for f2 in a.findings if f2["severity"] == "ERROR"]
        warns = [f2 for f2 in a.findings if f2["severity"] == "WARN"]
        if errors or result.get("status") == "failed":
            result["status"] = "partial" if errors else result.get("status")
        else:
            result["status"] = "success"
        unc = list(result.get("uncertainty") or [])
        for f2 in errors + warns:
            note = "[%s %s] %s" % (f2["gate"], f2["code"], f2["message"])
            if note not in unc:
                unc.append(note)
        if result["status"] == "partial" and not unc:
            unc.append("partial: not all audit findings resolved")
        if result["status"] == "success":
            unc = []
        result["uncertainty"] = unc
        srcs = []
        for fn, e in sorted(evidence.items()):
            srcs.append({"path": os.path.join(ev_dir, fn),
                         "sha256_12": e["sha256_12"], "bytes": e["bytes"]})
        result["sources"] = srcs
        result["repaired_by"] = ("retrieval-run-warden warden.py --fix-result "
                                 "(candidates/evidence never edited)")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)

    print(json.dumps({"GATE": overall, "errors": n_err, "warnings": n_warn,
                      "gate_status": gate_status,
                      "audit_report": os.path.join(out_dir,
                                                   "audit_report.md")},
                     ensure_ascii=False))
    sys.exit(0 if overall == "PASS" else 1)


if __name__ == "__main__":
    main()
