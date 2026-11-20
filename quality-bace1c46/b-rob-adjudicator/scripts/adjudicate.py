#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adjudicate.py -- merge channel-P and channel-N first-pass judgments.

Implements the plaintext rules in rules/adjudication.md:

  R1 agreement         identical judgments -> adopted, source=agreement
  R2 evidence priority a judgment backed by a verbatim quote beats one
                       without; methodological explicit description >
                       results/table implication > no report
  R3 no report         if neither side has any quote, the domain defaults
                       to 'insufficient' (abstention, not a safe default)
  R4 conservative      both sides evidence-backed but disagree -> adopt the
                       higher-risk judgment, tag adjudicated_conservative
  R5 single channel    only one channel reported -> adopt if quote-backed,
                       else 'insufficient'; flagged single_channel

Every disagreement (and every single-channel adoption) is appended to
adjudication_ledger.jsonl with the rule applied. Disagreements are never
silently smoothed over.

Inputs : channel_p/<doc_id>.jsonl, channel_n/<doc_id>.jsonl
         (rows: {doc_id, domain, judgment, quote, locator, rationale})
Outputs: adjudicated/<doc_id>.jsonl, adjudication_ledger.jsonl
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common_utils as cu

SCRIPT_VERSION = "adjudicate/1.0"


def has_quote(row):
    return bool(row and str(row.get("quote") or "").strip())


def sanitize(row, channel, doc_id):
    if not row or row.get("_parse_error"):
        return None
    j = row.get("judgment")
    if not cu.valid_judgment(j):
        return None
    return {
        "doc_id": row.get("doc_id") or doc_id,
        "domain": row.get("domain"),
        "judgment": j,
        "quote": str(row.get("quote") or "").strip(),
        "locator": str(row.get("locator") or "").strip(),
        "rationale": str(row.get("rationale") or "").strip(),
        "channel": channel,
    }


def adjudicate_domain(doc_id, domain, prow, nrow, ledger):
    """Return the adjudicated record for one domain."""
    base = {"doc_id": doc_id, "domain": domain,
            "channel_p": prow, "channel_n": nrow}

    if prow is None and nrow is None:
        rec = dict(base, judgment="insufficient", quote="", locator="",
                   rationale="no channel reported on this domain",
                   source="no_channel", adjudicated_conservative=False)
        ledger.append({"doc_id": doc_id, "domain": domain,
                       "type": "no_channel", "rule_applied": "R3",
                       "detail": "neither channel reported; abstained"})
        return rec

    if prow is None or nrow is None:
        only = prow or nrow
        which = "P" if prow else "N"
        if has_quote(only):
            rec = dict(base, judgment=only["judgment"], quote=only["quote"],
                       locator=only["locator"], rationale=only["rationale"],
                       source="single_channel_" + which,
                       adjudicated_conservative=False)
        else:
            rec = dict(base, judgment="insufficient", quote="", locator="",
                       rationale="single channel without verbatim quote",
                       source="single_channel_" + which,
                       adjudicated_conservative=False)
        ledger.append({"doc_id": doc_id, "domain": domain,
                       "type": "channel_missing",
                       "rule_applied": "R5",
                       "detail": "channel %s missing; adopted %s"
                                 % (("N" if prow else "P"), rec["judgment"])})
        return rec

    if prow["judgment"] == nrow["judgment"]:
        # agreement; keep whichever row carries the quote (prefer P's)
        chosen = prow if has_quote(prow) else nrow
        return dict(base, judgment=prow["judgment"], quote=chosen["quote"],
                    locator=chosen["locator"], rationale=chosen["rationale"],
                    source="agreement", adjudicated_conservative=False)

    pj, nj = prow["judgment"], nrow["judgment"]
    pq, nq = has_quote(prow), has_quote(nrow)

    entry = {"doc_id": doc_id, "domain": domain, "type": "disagreement",
             "channel_p_judgment": pj, "channel_n_judgment": nj}

    if pq and not nq:
        entry.update({"rule_applied": "R2",
                      "detail": "channel P quote-backed judgment beats "
                                "unbacked channel N (%s)" % nj})
        ledger.append(entry)
        return dict(base, judgment=pj, quote=prow["quote"],
                    locator=prow["locator"], rationale=prow["rationale"],
                    source="adjudicated_R2", adjudicated_conservative=False)
    if nq and not pq:
        entry.update({"rule_applied": "R2",
                      "detail": "channel N quote-backed judgment beats "
                                "unbacked channel P (%s)" % pj})
        ledger.append(entry)
        return dict(base, judgment=nj, quote=nrow["quote"],
                    locator=nrow["locator"], rationale=nrow["rationale"],
                    source="adjudicated_R2", adjudicated_conservative=False)

    if not pq and not nq:
        entry.update({"rule_applied": "R3",
                      "detail": "no verbatim quote on either side; "
                                "defaulted to insufficient"})
        ledger.append(entry)
        return dict(base, judgment="insufficient", quote="", locator="",
                    rationale="disagreement without evidence on either side",
                    source="adjudicated_R3", adjudicated_conservative=False)

    # both quote-backed but disagree -> conservative
    winner, loser = (prow, nrow) if cu.RISK_RANK[pj] >= cu.RISK_RANK[nj] \
        else (nrow, prow)
    entry.update({"rule_applied": "R4",
                  "detail": "both quote-backed; conservative rule adopted "
                            "higher-risk judgment %s over %s"
                            % (winner["judgment"], loser["judgment"])})
    ledger.append(entry)
    return dict(base, judgment=winner["judgment"], quote=winner["quote"],
                locator=winner["locator"], rationale=winner["rationale"],
                source="adjudicated_R4", adjudicated_conservative=True)


def main():
    ap = argparse.ArgumentParser(
        description="Adjudicate channel P vs channel N judgments")
    ap.add_argument("--workdir", default="/app/work")
    args = ap.parse_args()

    plan = cu.read_json(os.path.join(args.workdir, "domain_plan.json"),
                        default={"documents": []})
    out_dir = os.path.join(args.workdir, "adjudicated")
    os.makedirs(out_dir, exist_ok=True)
    ledger_path = os.path.join(args.workdir, "adjudication_ledger.jsonl")
    # reset ledger for idempotent reruns
    if os.path.exists(ledger_path):
        os.remove(ledger_path)

    stats = {"docs": 0, "domains": 0, "disagreements": 0}
    for entry in plan.get("documents", []):
        doc_id = entry.get("doc_id")
        if entry.get("grade") == "failed":
            continue
        prows = {r.get("domain"): sanitize(r, "P", doc_id)
                 for r in cu.read_jsonl(os.path.join(
                     args.workdir, "channel_p", doc_id + ".jsonl"))}
        nrows = {r.get("domain"): sanitize(r, "N", doc_id)
                 for r in cu.read_jsonl(os.path.join(
                     args.workdir, "channel_n", doc_id + ".jsonl"))}
        domains = [d["id"] for d in entry.get("domains", [])]
        # include any domain the channels reported but the plan missed
        for dd in list(prows) + list(nrows):
            if dd and dd not in domains:
                domains.append(dd)
        ledger = []
        out_rows = []
        for dom in domains:
            rec = adjudicate_domain(doc_id, dom, prows.get(dom),
                                    nrows.get(dom), ledger)
            out_rows.append(rec)
        cu.write_jsonl(os.path.join(out_dir, doc_id + ".jsonl"), out_rows)
        for item in ledger:
            cu.append_jsonl(ledger_path, item)
        stats["docs"] += 1
        stats["domains"] += len(out_rows)
        stats["disagreements"] += sum(
            1 for i in ledger if i["type"] == "disagreement")
    print(stats)


if __name__ == "__main__":
    main()
