#!/usr/bin/env python3
"""audit.py — independent mechanical audit of an extraction draft (stage 2 / 4).

Audits EVERY item of the draft against the normalized corpus:
  * quote must be an EXACT substring of the cited paragraph (QUOTE_NOT_SUBSTRING)
  * evidence address source_id + paragraph_id must exist (SOURCE_UNKNOWN / ADDRESS_UNKNOWN)
  * root bibliographic metadata (doi/title of case.json) must not be attributed
    to the secondary source (ROOT_META_MISATTRIBUTION)
  * merge/nonmerge discipline (missing key/reason, unknown members,
    INVALID_NUMERIC_MERGE for merging claims with different numeric values)
  * edge endpoints must exist (ENDPOINT_UNKNOWN)
  * structural required fields (MISSING_FIELD)

Verdicts: accept / repair (iteration < max) / reject (final iteration).
Emits per-item verdicts with reason codes into audit_report.json, and a
repair_queue.json containing ONLY failing items. On the final iteration,
rejected items go to quarantine.json. Bounded: --iteration must be 1..2.

Usage:
    python3 audit.py --work /app/work --draft /app/work/extraction.draft.json --iteration 1

Python 3.9+, standard library only. Deterministic output.
"""
import argparse
import json
import os
import re
import sys

MAX_ITERATIONS = 2
MIN_QUOTE_LEN = 8

REQUIRED_FIELDS = {
    "node": ["id", "op", "entity_type", "label", "evidence"],
    "edge": ["id", "op", "relation", "subject", "object", "evidence"],
    "merge": ["id", "op", "members", "normalized_key", "reason", "evidence"],
    "nonmerge": ["id", "op", "members", "reason", "evidence"],
    "unreported": ["id", "op", "topic", "reason"],
    "note": ["id", "op", "text"],
}
EVIDENCE_OPS = ("node", "edge", "merge", "nonmerge", "unreported")


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip()).casefold()


def evidence_list(item):
    ev = item.get("evidence")
    if ev is None:
        return []
    if isinstance(ev, dict):
        return [ev]
    if isinstance(ev, list):
        return [e for e in ev if isinstance(e, dict)]
    return []


def find_latest_draft(work):
    rep = os.path.join(work, "extraction.repaired.json")
    if os.path.isfile(rep):
        return rep
    return os.path.join(work, "extraction.draft.json")


def audit(work, draft_path, iteration):
    corpus = load_json(os.path.join(work, "corpus.json"))
    draft = load_json(draft_path)
    items = draft.get("items") if isinstance(draft, dict) else None
    if not isinstance(items, list):
        print("ERROR: draft has no 'items' list: %s" % draft_path, file=sys.stderr)
        return 2

    sources = corpus.get("sources") or {}
    para_text = {}   # (source_id, paragraph_id) -> text
    all_addresses = set()
    for sid, src in sources.items():
        for p in src.get("paragraphs") or []:
            para_text[(sid, p["paragraph_id"])] = p["text"]
            all_addresses.add((sid, p["paragraph_id"]))

    root = corpus.get("root_metadata") or {}
    root_title_n = norm(root.get("title"))
    root_doi_n = norm(root.get("doi"))
    secondary_ids = {sid for sid, s in sources.items() if s.get("role") == "secondary"}

    items_by_id = {}
    for it in items:
        if isinstance(it, dict) and it.get("id"):
            items_by_id[str(it["id"])] = it

    quotes_total = quotes_valid = 0
    addr_total = addr_valid = 0
    per_item = []
    cited_paragraphs_accepted = set()

    for it in items:
        if not isinstance(it, dict):
            per_item.append({"id": None, "op": None, "verdict": None,
                             "codes": ["ITEM_NOT_OBJECT"], "messages": ["item is not a JSON object"]})
            continue
        iid = str(it.get("id") or "")
        op = str(it.get("op") or "")
        codes = []
        messages = []

        # --- structure ---
        if op not in REQUIRED_FIELDS:
            codes.append("UNKNOWN_OP")
            messages.append("unknown op '%s'; expected one of %s" % (op, sorted(REQUIRED_FIELDS)))
        else:
            for field in REQUIRED_FIELDS[op]:
                if it.get(field) in (None, "", []):
                    codes.append("MISSING_FIELD")
                    messages.append("missing required field '%s' for op '%s'" % (field, op))
                    break  # one structural code is enough per item

        # --- evidence checks (quote / address / attribution) ---
        misattributed = False
        if op in EVIDENCE_OPS:
            evs = evidence_list(it)
            if op in ("node", "edge", "merge", "nonmerge") and not evs:
                if "MISSING_FIELD" not in codes:
                    codes.append("EVIDENCE_MISSING")
                    messages.append("op '%s' requires at least one evidence entry" % op)
            for ev in evs:
                sid = str(ev.get("source_id") or "")
                pid = str(ev.get("paragraph_id") or "")
                quote = str(ev.get("quote") or "")
                addr_total += 1
                addr_ok = True
                if sid not in sources:
                    addr_ok = False
                    codes.append("SOURCE_UNKNOWN")
                    messages.append("evidence source_id '%s' not in corpus" % sid)
                elif (sid, pid) not in all_addresses:
                    addr_ok = False
                    codes.append("ADDRESS_UNKNOWN")
                    messages.append("paragraph_id '%s' not found in source '%s'" % (pid, sid))
                if addr_ok:
                    addr_valid += 1
                quotes_total += 1
                text = para_text.get((sid, pid))
                if text is None:
                    # address already flagged; quote cannot be checked
                    messages.append("quote not checkable (bad address)")
                elif quote and quote in text:
                    quotes_valid += 1
                elif not quote or len(quote) < MIN_QUOTE_LEN:
                    codes.append("QUOTE_TOO_SHORT")
                    messages.append("quote missing or shorter than %d chars" % MIN_QUOTE_LEN)
                else:
                    codes.append("QUOTE_NOT_SUBSTRING")
                    messages.append("quote is not an exact substring of %s/%s" % (sid, pid))
                # root-metadata attribution: root title/doi must only appear on primary
                if sid in secondary_ids and not misattributed:
                    label_n = norm(it.get("label"))
                    quote_n = norm(quote)
                    if (op == "node" and it.get("entity_type") in ("paper", "source")
                            and root_title_n and label_n == root_title_n):
                        misattributed = True
                    elif root_doi_n and root_doi_n in quote_n:
                        misattributed = True
                    if misattributed:
                        codes.append("ROOT_META_MISATTRIBUTION")
                        messages.append(
                            "root bibliographic metadata (case.json title/doi) attributed to "
                            "secondary source '%s'; root metadata belongs ONLY to the primary paper" % sid)

        # --- edge endpoints ---
        if op == "edge":
            for endpoint in ("subject", "object"):
                ref = str(it.get(endpoint) or "")
                if ref and ref not in items_by_id:
                    codes.append("ENDPOINT_UNKNOWN")
                    messages.append("edge %s '%s' is not a known item id" % (endpoint, ref))
                    break

        # --- merge discipline ---
        if op == "merge":
            members = it.get("members") or []
            for m in members:
                if str(m) not in items_by_id:
                    codes.append("MERGE_MEMBER_UNKNOWN")
                    messages.append("merge member '%s' is not a known item id" % m)
                    break
            if not it.get("normalized_key") and "MISSING_FIELD" not in codes:
                codes.append("MERGE_MISSING_KEY")
                messages.append("merge requires a normalized_key")
            if not it.get("reason") and "MISSING_FIELD" not in codes:
                codes.append("MERGE_MISSING_REASON")
                messages.append("merge requires an explicit reason")
            # never merge claims with the same metric but different numeric values
            member_nodes = [items_by_id.get(str(m)) for m in members]
            member_nodes = [n for n in member_nodes if isinstance(n, dict)]
            if member_nodes and all(n.get("entity_type") == "claim" for n in member_nodes):
                metrics = {norm((n.get("attributes") or {}).get("metric")) for n in member_nodes}
                values = {norm((n.get("attributes") or {}).get("value")) for n in member_nodes}
                if len(metrics) == 1 and len(values) > 1:
                    codes.append("INVALID_NUMERIC_MERGE")
                    messages.append(
                        "refusing to merge claims with metric %s but different values %s; "
                        "keep them as separate claims (conflict preserved)" %
                        (sorted(metrics), sorted(values)))

        # --- nonmerge discipline ---
        if op == "nonmerge":
            members = it.get("members") or []
            if len(members) < 2 and "MISSING_FIELD" not in codes:
                codes.append("NONMERGE_TOO_FEW_MEMBERS")
                messages.append("nonmerge requires at least two member ids")
            for m in members:
                if str(m) not in items_by_id:
                    codes.append("MERGE_MEMBER_UNKNOWN")
                    messages.append("nonmerge member '%s' is not a known item id" % m)
                    break

        codes = sorted(set(codes))
        verdict = "accept" if not codes else ("repair" if iteration < MAX_ITERATIONS else "reject")
        per_item.append({
            "id": iid, "op": op, "verdict": verdict,
            "codes": codes, "messages": messages,
            "misattributed": misattributed,
        })
        if verdict == "accept":
            for ev in evidence_list(it):
                key = (str(ev.get("source_id") or ""), str(ev.get("paragraph_id") or ""))
                if key in all_addresses:
                    cited_paragraphs_accepted.add(key)

    per_item.sort(key=lambda r: (str(r.get("id") or "")))
    n_items = len(per_item)
    accepted = [r["id"] for r in per_item if r["verdict"] == "accept"]
    repair = [r["id"] for r in per_item if r["verdict"] == "repair"]
    rejected = [r["id"] for r in per_item if r["verdict"] == "reject"]
    n_misattributed = sum(1 for r in per_item if r.get("misattributed"))

    def pct(num, den):
        return round(100.0 * num / den, 1) if den else None

    metrics = {
        "items_total": n_items,
        "accepted": len(accepted),
        "repair": len(repair),
        "rejected": len(rejected),
        "quotes_total": quotes_total,
        "quotes_valid": quotes_valid,
        "quote_precision_pct": pct(quotes_valid, quotes_total),
        "addresses_total": addr_total,
        "addresses_valid": addr_valid,
        "address_validity_pct": pct(addr_valid, addr_total),
        "attribution_checked_items": n_items,
        "attribution_violations": n_misattributed,
        "attribution_accuracy_pct": pct(n_items - n_misattributed, n_items),
        "corpus_paragraphs_total": len(all_addresses),
        "corpus_paragraphs_cited": len(cited_paragraphs_accepted),
        "paragraph_coverage_pct": pct(len(cited_paragraphs_accepted), len(all_addresses)),
    }
    uncited = sorted("%s/%s" % a for a in (all_addresses - cited_paragraphs_accepted))

    report = {
        "audit": "evidence-audit-loop",
        "iteration": iteration,
        "max_iterations": MAX_ITERATIONS,
        "case_id": corpus.get("case_id"),
        "draft_file": os.path.basename(draft_path),
        "verdicts": {"accept": accepted, "repair": repair, "reject": rejected},
        "per_item": [{k: v for k, v in r.items() if k != "misattributed"} for r in per_item],
        "metrics": metrics,
        "uncited_paragraphs": uncited,
    }
    dump_json(report, os.path.join(work, "audit_report.iter%d.json" % iteration))
    dump_json(report, os.path.join(work, "audit_report.json"))  # latest

    failing = [r for r in per_item if r["verdict"] != "accept"]
    queue_items = []
    for r in failing:
        orig = items_by_id.get(r["id"], {})
        queue_items.append({
            "id": r["id"], "op": r["op"],
            "codes": r["codes"], "messages": r["messages"],
            "item": orig,
        })
    queue = {
        "iteration": iteration,
        "instruction": ("Repair ONLY the items in this queue: fix the flagged fields "
                        "(quote / paragraph_id / source attribution / merge discipline) and "
                        "return patches keyed by item id. Do not touch accepted items."),
        "items": queue_items,
    }
    dump_json(queue, os.path.join(work, "repair_queue.json"))
    dump_json(queue, os.path.join(work, "repair_queue.iter%d.json" % iteration))

    if iteration >= MAX_ITERATIONS:
        quarantine = {
            "note": "Items still failing after the final audit iteration. Excluded from the graph.",
            "items": queue_items,
        }
        dump_json(quarantine, os.path.join(work, "quarantine.json"))

    print("audit iter=%d: items=%d accept=%d repair=%d reject=%d | quote=%.1f%% addr=%.1f%% attr=%.1f%% coverage=%.1f%%" % (
        iteration, n_items, len(accepted), len(repair), len(rejected),
        metrics["quote_precision_pct"] or 0.0, metrics["address_validity_pct"] or 0.0,
        metrics["attribution_accuracy_pct"] or 0.0, metrics["paragraph_coverage_pct"] or 0.0))
    return 0


def main():
    ap = argparse.ArgumentParser(description="Mechanically audit an extraction draft")
    ap.add_argument("--work", required=True)
    ap.add_argument("--draft", default=None,
                    help="draft JSON (default: extraction.repaired.json if present else extraction.draft.json)")
    ap.add_argument("--iteration", type=int, required=True, help="audit iteration (1..%d)" % MAX_ITERATIONS)
    args = ap.parse_args()
    if not (1 <= args.iteration <= MAX_ITERATIONS):
        print("ERROR: --iteration must be between 1 and %d (bounded loop)" % MAX_ITERATIONS, file=sys.stderr)
        return 2
    draft = args.draft or find_latest_draft(args.work)
    if not os.path.isfile(draft):
        print("ERROR: draft not found: %s" % draft, file=sys.stderr)
        return 2
    return audit(args.work, draft, args.iteration)


if __name__ == "__main__":
    sys.exit(main())
