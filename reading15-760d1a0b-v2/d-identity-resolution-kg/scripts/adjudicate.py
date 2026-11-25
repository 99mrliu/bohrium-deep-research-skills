#!/usr/bin/env python3
"""adjudicate.py — apply the model's tiny adjudication JSON to the candidates.

Inputs (both in --work):
  candidates.json     from candidates.py (script-generated)
  adjudication.json   the ONLY identity artifact the model writes:
                      {"decisions": [{"pair_id": "P01",
                                      "decision": "merge" | "nonmerge",
                                      "reason": "<one line>",
                                      "evidence": ["s1-p01", "s2-p03"]}]}

Rules:
  * every decision is validated (pair exists, decision value legal, reason
    non-empty, evidence paragraph ids exist in the corpus);
  * invalid decisions are quarantined and the pair falls back to the
    conservative default: NONMERGE with decision_source
    "default-conservative" (never silently merged);
  * pairs the model did not adjudicate also default to nonmerge;
  * union-find over (norm_key, source_id) atoms yields canonical entities
    with stable deterministic IDs E0001... (components sorted by their
    smallest member key).

Outputs (work): entity_map.json, merge_ledger.json, nonmerge_registry.json,
adjudication_report.json.

Usage: python3 adjudicate.py --work /app/work
"""
import argparse
import os
import sys
from collections import Counter, defaultdict

import kgcommon as K


def _representative_surface(mentions):
    counts = Counter(m["surface"] for m in mentions)
    return sorted(counts.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[0][0]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", required=True, help="work directory")
    args = ap.parse_args(argv)
    work = args.work

    try:
        corpus = K.load_json(os.path.join(work, "corpus.json"))
        candidates = K.load_json(os.path.join(work, "candidates.json"))
    except Exception as exc:
        print("ERROR: %s; run discover.py and candidates.py first" % exc,
              file=sys.stderr)
        return 2

    valid_pids = {(s["source_id"], p["paragraph_id"])
                  for s in corpus["sources"] for p in s["paragraphs"]}
    pid_to_sid = {p["paragraph_id"]: s["source_id"]
                  for s in corpus["sources"] for p in s["paragraphs"]}
    pairs = {p["pair_id"]: p for p in candidates["pairs"]}

    # --- load and validate the model's adjudication ------------------------
    decisions = {}
    quarantine = []
    adj_path = os.path.join(work, "adjudication.json")
    raw = {"decisions": []}
    if os.path.isfile(adj_path):
        try:
            raw = K.load_json(adj_path)
        except Exception as exc:
            quarantine.append({"pair_id": None, "error": "ADJUDICATION_UNPARSABLE",
                               "detail": str(exc)})
    else:
        quarantine.append({"pair_id": None, "error": "ADJUDICATION_MISSING",
                           "detail": "no adjudication.json; all pairs default to nonmerge"})
    if not isinstance(raw, dict) or not isinstance(raw.get("decisions"), list):
        quarantine.append({"pair_id": None, "error": "ADJUDICATION_SHAPE",
                           "detail": "expected {\"decisions\": [...]}"})
        raw = {"decisions": []}

    for idx, dec in enumerate(raw["decisions"]):
        if not isinstance(dec, dict):
            quarantine.append({"pair_id": None, "error": "DECISION_NOT_OBJECT",
                               "detail": "decision #%d" % idx})
            continue
        pid = dec.get("pair_id")
        if pid not in pairs:
            quarantine.append({"pair_id": pid, "error": "UNKNOWN_PAIR_ID",
                               "detail": "no such candidate pair"})
            continue
        if pid in decisions:
            quarantine.append({"pair_id": pid, "error": "DUPLICATE_DECISION",
                               "detail": "later decision ignored"})
            continue
        if dec.get("decision") not in ("merge", "nonmerge"):
            quarantine.append({"pair_id": pid, "error": "BAD_DECISION_VALUE",
                               "detail": repr(dec.get("decision"))})
            continue
        if not str(dec.get("reason") or "").strip():
            quarantine.append({"pair_id": pid, "error": "MISSING_REASON",
                               "detail": "a one-line reason is mandatory"})
            continue
        evidence = dec.get("evidence") or []
        bad = [e for e in evidence
               if (pid_to_sid.get(e), e) not in valid_pids or e not in pid_to_sid]
        if bad:
            quarantine.append({"pair_id": pid, "error": "BAD_EVIDENCE_PARAGRAPH",
                               "detail": "unknown paragraph ids: %s" % sorted(bad)})
            continue
        decisions[pid] = {
            "decision": dec["decision"],
            "reason": str(dec["reason"]).strip(),
            "evidence": sorted(set(evidence)),
            "decision_source": "model-adjudication",
        }

    # --- conservative default for unadjudicated / quarantined pairs --------
    for pid in sorted(pairs):
        if pid not in decisions:
            decisions[pid] = {
                "decision": "nonmerge",
                "reason": "unadjudicated or invalid decision; conservative default",
                "evidence": [],
                "decision_source": "default-conservative",
            }

    # --- union-find over (norm_key, source_id) atoms ------------------------
    uf = K.UnionFind()
    mentions_by_atom = defaultdict(list)
    for pair in candidates["pairs"]:
        for side in ("a", "b"):
            m = pair[side]
            atom = (m["norm_key"], m["source_id"])
            if not any(x["paragraph_id"] == m["paragraph_id"] and
                       x["surface"] == m["surface"] for x in mentions_by_atom[atom]):
                mentions_by_atom[atom].append(m)
    for atom in sorted(mentions_by_atom):
        uf.find(atom)
    for pid, pair in sorted(pairs.items()):
        if decisions[pid]["decision"] == "merge":
            uf.union((pair["a"]["norm_key"], pair["a"]["source_id"]),
                     (pair["b"]["norm_key"], pair["b"]["source_id"]))

    components = uf.components()
    components.sort(key=lambda comp: comp[0])  # smallest member key; stable

    # --- canonical entities with deterministic IDs --------------------------
    block_votes = defaultdict(Counter)
    for pair in candidates["pairs"]:
        for side in ("a", "b"):
            m = pair[side]
            block_votes[(m["norm_key"], m["source_id"])][m["block"]] += 1

    entities = []
    atom_to_entity = {}
    for idx, comp in enumerate(components, 1):
        eid = "E%04d" % idx
        members = []
        for atom in comp:
            members.extend(mentions_by_atom.get(atom, []))
        members.sort(key=lambda m: (m["source_id"], m["paragraph_id"], m["surface"]))
        votes = Counter()
        for atom in comp:
            votes.update(block_votes.get(atom, {}))
        etype = (votes.most_common(1)[0][0] if votes else "unknown")
        aliases = sorted({m["surface"] for m in members})
        entities.append({
            "entity_id": eid,
            "type": etype,
            "canonical_surface": _representative_surface(members),
            "aliases": aliases,
            "member_keys": sorted({m["norm_key"] for m in members}),
            "source_ids": sorted({m["source_id"] for m in members}),
            "cross_paper": len({m["source_id"] for m in members}) > 1,
            "mentions": [{
                "surface": m["surface"],
                "source_id": m["source_id"],
                "paragraph_id": m["paragraph_id"],
                "quote": m["context"],
            } for m in members],
        })
        for atom in comp:
            atom_to_entity[atom] = eid

    # --- ledgers -------------------------------------------------------------
    merge_ledger, nonmerge_registry = [], []
    for pid in sorted(pairs):
        pair, dec = pairs[pid], decisions[pid]
        evidence = [{"paragraph_id": e, "source_id": pid_to_sid[e]}
                    for e in dec["evidence"]]
        base = {
            "pair_id": pid,
            "kind": pair["kind"],
            "trap_flagged": pair["trap"],
            "form_a": pair["a"]["surface"], "key_a": pair["a"]["norm_key"],
            "source_a": pair["a"]["source_id"],
            "paragraph_a": pair["a"]["paragraph_id"],
            "form_b": pair["b"]["surface"], "key_b": pair["b"]["norm_key"],
            "source_b": pair["b"]["source_id"],
            "paragraph_b": pair["b"]["paragraph_id"],
            "reason": dec["reason"],
            "decision_source": dec["decision_source"],
            "evidence": evidence,
        }
        if dec["decision"] == "merge":
            base["entity_id"] = atom_to_entity.get(
                (pair["a"]["norm_key"], pair["a"]["source_id"]))
            merge_ledger.append(base)
        else:
            base["trap_reason"] = pair["trap_reason"]
            nonmerge_registry.append(base)

    K.dump_json({"notice": K.NOTICE, "entities": entities,
                 "atom_index": {"%s|%s" % atom: eid
                                for atom, eid in sorted(atom_to_entity.items())}},
                os.path.join(work, "entity_map.json"))
    K.dump_json({"notice": K.NOTICE, "merge_count": len(merge_ledger),
                 "merges": merge_ledger},
                os.path.join(work, "merge_ledger.json"))
    K.dump_json({"notice": K.NOTICE, "nonmerge_count": len(nonmerge_registry),
                 "nonmerges": nonmerge_registry},
                os.path.join(work, "nonmerge_registry.json"))
    K.dump_json({"notice": K.NOTICE,
                 "adjudicated": sum(1 for d in decisions.values()
                                    if d["decision_source"] == "model-adjudication"),
                 "defaulted": sum(1 for d in decisions.values()
                                  if d["decision_source"] == "default-conservative"),
                 "quarantine": quarantine},
                os.path.join(work, "adjudication_report.json"))
    print("adjudicate: %d merge(s), %d nonmerge(s), %d entit(ies), %d quarantined decision(s)"
          % (len(merge_ledger), len(nonmerge_registry), len(entities), len(quarantine)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
