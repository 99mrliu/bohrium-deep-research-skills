#!/usr/bin/env python3
"""validate_ontology.py — closed-ontology validator with typed-error quarantine.

Validates a model-written extraction JSONL file against references/ontology.json
and the discovered corpus. Accepted ops are appended to the validation state;
violations are rejected into quarantine.json with typed error codes, and a
per-rule violation histogram is written to validation_report.json.

Repair policy (bounded, ONE pass):
    pass 1:  validate the draft      -> quarantine.json lists violations
    pass 2:  validate the repair file (--repair). Repaired items (same ids)
             replace quarantined ones; still-failing items stay quarantined
             forever (final=true). A third attempt is refused with
             REPAIR_BUDGET_EXHAUSTED.

Usage:
    python3 validate_ontology.py --work /app/work --extraction /app/work/extractions.jsonl
    python3 validate_ontology.py --work /app/work --extraction /app/work/repair.jsonl --repair

Options:
    --ontology PATH   override ontology (default: ../references/ontology.json
                      relative to this script)

Outputs under <work>:
    validation_state.json   accepted ops so far (nodes/edges/merges/...)
    validated.jsonl         accepted ops, one JSON object per line, id-sorted
    quarantine.json         rejected items with typed error codes
    validation_report.json  per-rule violation counts, per pass and cumulative

Python 3 standard library only. Deterministic output (sorted keys and lines).
"""
import argparse
import json
import os
import sys

OPS = ("node", "edge", "merge", "nonmerge", "unreported", "note")
NO_MERGE_TYPES = ("sample", "claim")


def load_json(path, default=None):
    if not os.path.isfile(path):
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


class Checker:
    """Collects typed errors for one extraction item."""

    def __init__(self, ontology, corpus, known_nodes, known_ids):
        self.ont = ontology
        self.corpus = corpus
        self.known_nodes = known_nodes      # id -> node op (accepted + this pass)
        self.known_ids = known_ids          # all ids ever accepted (nodes+edges)
        self.errors = []

    def err(self, code, message):
        self.errors.append({"code": code, "message": message})

    # -- evidence ------------------------------------------------------------
    def check_evidence(self, item, allow_empty_quote=False):
        ev = item.get("evidence")
        if ev is None:
            self.err("EVIDENCE_MISSING", "no evidence block")
            return
        evs = ev if isinstance(ev, list) else [ev]
        for e in evs:
            if not isinstance(e, dict) or not e.get("source_id") or not e.get("paragraph_id"):
                self.err("EVIDENCE_MISSING",
                         "evidence needs source_id and paragraph_id")
                continue
            key = "%s/%s" % (e["source_id"], e["paragraph_id"])
            if key not in self.corpus.get("address_index", {}):
                self.err("ADDRESS_NOT_FOUND", "address %s not in corpus" % key)
                continue
            quote = e.get("quote")
            if quote is None or (quote == "" and allow_empty_quote):
                if quote == "" and allow_empty_quote:
                    continue
                self.err("EVIDENCE_MISSING", "quote missing")
                continue
            text = self._paragraph_text(e["source_id"], e["paragraph_id"])
            if text is None:
                self.err("ADDRESS_NOT_FOUND", "address %s not in corpus" % key)
            elif quote not in text:
                self.err("QUOTE_NOT_SUBSTRING",
                         "quote is not an exact substring of %s" % key)

    _para_cache = None

    def _paragraph_text(self, source_id, paragraph_id):
        if self._para_cache is None:
            self._para_cache = {(p["source_id"], p["paragraph_id"]): p["text"]
                                for p in self.corpus.get("paragraphs", [])}
        return self._para_cache.get((source_id, paragraph_id))

    # -- qualifiers ------------------------------------------------------------
    def check_qualifiers(self, rel_id, rel_spec, quals, obj_type):
        if not isinstance(quals, dict):
            self.err("BAD_SHAPE", "qualifiers must be a JSON object")
            return
        qdefs = self.ont["qualifier_keys"]
        required = list(rel_spec.get("required_qualifiers", []))
        optional = list(rel_spec.get("optional_qualifiers", []))
        has_value = False
        for key, val in quals.items():
            if key not in qdefs:
                self.err("UNKNOWN_QUALIFIER", "qualifier '%s' not in ontology" % key)
                continue
            if key not in required and key not in optional:
                self.err("MISSING_QUALIFIER",
                         "qualifier '%s' not declared for relation '%s'" % (key, rel_id))
            want = qdefs[key]["value_type"]
            if want == "number":
                if isinstance(val, bool) or not isinstance(val, (int, float)):
                    self.err("QUALIFIER_TYPE_MISMATCH",
                             "qualifier '%s' must be a number" % key)
                else:
                    has_value = True
            elif want == "string" and not isinstance(val, str):
                self.err("QUALIFIER_TYPE_MISMATCH",
                         "qualifier '%s' must be a string" % key)
        for key in required:
            if key not in quals or quals.get(key) in (None, ""):
                self.err("MISSING_QUALIFIER",
                         "required qualifier '%s' missing for '%s'" % (key, rel_id))
        # Global rule NUMERIC_REQUIRES_METRIC_CONDITION
        if has_value:
            has_metric = bool(quals.get("metric")) or obj_type == "metric"
            has_condition = bool(quals.get("condition"))
            if not (has_metric and has_condition):
                self.err("NUMERIC_REQUIRES_METRIC_CONDITION",
                         "numeric value without metric/condition qualifiers")

    # -- ops ------------------------------------------------------------
    def check_node(self, item):
        nid = item.get("id")
        etype = item.get("type")
        if not isinstance(nid, str) or not nid:
            self.err("BAD_SHAPE", "node needs non-empty string id")
        elif nid in self.known_ids:
            self.err("DUPLICATE_ID", "id '%s' already used" % nid)
        if not isinstance(item.get("label"), str) or not item.get("label"):
            self.err("BAD_SHAPE", "node needs non-empty string label")
        if etype not in self.ont["entity_types"]:
            self.err("UNKNOWN_ENTITY_TYPE", "entity type '%s' not in ontology" % etype)
        self.check_evidence(item)

    def check_edge(self, item):
        eid = item.get("id")
        if not isinstance(eid, str) or not eid:
            self.err("BAD_SHAPE", "edge needs non-empty string id")
        elif eid in self.known_ids:
            self.err("DUPLICATE_ID", "id '%s' already used" % eid)
        rel = item.get("relation")
        rel_spec = self.ont["relation_types"].get(rel)
        if rel_spec is None:
            self.err("UNKNOWN_RELATION", "relation '%s' not in ontology" % rel)
            # still check the rest of the shape for useful extra codes
        subj, obj = item.get("subject"), item.get("object")
        stype = otype = None
        for role, nid in (("subject", subj), ("object", obj)):
            if not isinstance(nid, str) or nid not in self.known_nodes:
                self.err("UNKNOWN_NODE_REF", "%s node '%s' unknown" % (role, nid))
        if isinstance(subj, str) and subj in self.known_nodes:
            stype = self.known_nodes[subj].get("type")
        if isinstance(obj, str) and obj in self.known_nodes:
            otype = self.known_nodes[obj].get("type")
        if subj is not None and subj == obj:
            self.err("SELF_EDGE", "subject and object are the same node")
        if rel_spec is not None:
            if stype is not None and stype not in rel_spec["domain"]:
                self.err("DOMAIN_MISMATCH",
                         "subject type '%s' not in domain of '%s' %s"
                         % (stype, rel, rel_spec["domain"]))
            if otype is not None and otype not in rel_spec["range"]:
                self.err("RANGE_MISMATCH",
                         "object type '%s' not in range of '%s' %s"
                         % (otype, rel, rel_spec["range"]))
            if rel_spec.get("same_type_required") and stype and otype and stype != otype:
                self.err("SAME_TYPE_REQUIRED",
                         "aliases links '%s' to '%s'" % (stype, otype))
            declared_pol = rel_spec.get("polarity")
            if "polarity" in item and item["polarity"] != declared_pol:
                self.err("POLARITY_MISMATCH",
                         "edge polarity '%s' != declared '%s' for '%s'"
                         % (item["polarity"], declared_pol, rel))
            self.check_qualifiers(rel, rel_spec, item.get("qualifiers", {}), otype)
        self.check_evidence(item)

    def check_merge(self, item):
        keep, drop = item.get("keep"), item.get("drop")
        for role, nid in (("keep", keep), ("drop", drop)):
            if not isinstance(nid, str) or nid not in self.known_nodes:
                self.err("MERGE_TARGET_UNKNOWN", "%s node '%s' unknown" % (role, nid))
        kt = self.known_nodes.get(keep, {}).get("type") if isinstance(keep, str) else None
        dt = self.known_nodes.get(drop, {}).get("type") if isinstance(drop, str) else None
        if kt and dt:
            if kt != dt:
                self.err("SAME_TYPE_REQUIRED",
                         "cannot merge '%s' into '%s'" % (dt, kt))
            if kt in NO_MERGE_TYPES:
                self.err("DOMAIN_MISMATCH",
                         "entity type '%s' may never be merged (ontology merge_rule)" % kt)
        if not isinstance(item.get("reason"), str) or not item.get("reason"):
            self.err("BAD_SHAPE", "merge needs a non-empty reason")
        self.check_evidence(item)

    def check_nonmerge(self, item):
        for role in ("a", "b"):
            nid = item.get(role)
            if not isinstance(nid, str) or nid not in self.known_nodes:
                self.err("MERGE_TARGET_UNKNOWN", "%s node '%s' unknown" % (role, nid))
        if not isinstance(item.get("reason"), str) or not item.get("reason"):
            self.err("BAD_SHAPE", "nonmerge needs a non-empty reason")
        self.check_evidence(item)

    def check_unreported(self, item):
        if not isinstance(item.get("item"), str) or not item.get("item"):
            self.err("BAD_SHAPE", "unreported needs a non-empty item string")
        if not isinstance(item.get("reason"), str) or not item.get("reason"):
            self.err("BAD_SHAPE", "unreported needs a non-empty reason")
        # quote may be "" when the item is absent from the whole source
        self.check_evidence(item, allow_empty_quote=True)

    def check_note(self, item):
        if not isinstance(item.get("text"), str) or not item.get("text"):
            self.err("BAD_SHAPE", "note needs a non-empty text string")

    def check(self, item, lineno):
        if not isinstance(item, dict):
            self.err("BAD_JSON_LINE", "line %d is not a JSON object" % lineno)
            return
        op = item.get("op")
        if op not in OPS:
            self.err("UNKNOWN_OP", "line %d: op '%s' unknown" % (lineno, op))
            return
        {"node": self.check_node, "edge": self.check_edge,
         "merge": self.check_merge, "nonmerge": self.check_nonmerge,
         "unreported": self.check_unreported, "note": self.check_note}[op](item)


def empty_state():
    return {"passes_completed": 0, "repair_used": 0,
            "nodes": {}, "edges": {}, "merges": [], "nonmerges": [],
            "unreported": [], "notes": [],
            "quarantine": {},          # id-or-linekey -> entry
            "report": {"passes": [], "cumulative_violations": {}}}


def item_key(item, lineno):
    if isinstance(item, dict) and isinstance(item.get("id"), str):
        return item["id"]
    return "line-%04d" % lineno


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(
        description="Validate extraction JSONL against the closed ontology.")
    parser.add_argument("--work", required=True, help="work dir with corpus.json")
    parser.add_argument("--extraction", required=True, help="extraction JSONL file")
    parser.add_argument("--repair", action="store_true",
                        help="this extraction is the single allowed repair pass")
    parser.add_argument("--ontology",
                        default=os.path.join(here, "..", "references", "ontology.json"),
                        help="path to ontology.json")
    args = parser.parse_args(argv)

    ontology = load_json(args.ontology)
    if ontology is None:
        print("FATAL: ontology not found at %s" % args.ontology, file=sys.stderr)
        return 2
    corpus = load_json(os.path.join(args.work, "corpus.json"))
    if corpus is None:
        print("FATAL: corpus.json missing; run discover.py first", file=sys.stderr)
        return 2
    state = load_json(os.path.join(args.work, "validation_state.json"), empty_state())

    pass_no = state["passes_completed"] + 1
    if args.repair:
        if state["repair_used"] >= ontology.get("repair_policy", {}).get("max_repair_passes", 1):
            print("REPAIR_BUDGET_EXHAUSTED: only %d repair pass(es) allowed"
                  % ontology["repair_policy"]["max_repair_passes"], file=sys.stderr)
            return 3
        state["repair_used"] += 1

    if not os.path.isfile(args.extraction):
        print("FATAL: extraction file not found: %s" % args.extraction, file=sys.stderr)
        return 2

    with open(args.extraction, "r", encoding="utf-8") as fh:
        raw_lines = fh.read().splitlines()

    accepted_this, rejected_this = [], []
    violations = {}
    known_ids = set(state["nodes"]) | set(state["edges"])
    # phase 1: nodes (so later edges in the same file can reference them)
    parsed = []
    for lineno, line in enumerate(raw_lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            parsed.append((lineno, json.loads(line)))
        except ValueError as exc:
            parsed.append((lineno, {"__parse_error__": str(exc), "__raw__": line[:200]}))
    ordered = [p for p in parsed if isinstance(p[1], dict) and p[1].get("op") == "node"]
    ordered += [p for p in parsed if not (isinstance(p[1], dict) and p[1].get("op") == "node")]

    if args.repair and not state["quarantine"]:
        print("note: --repair given but quarantine is empty; nothing to repair")
    for lineno, item in ordered:
        checker = Checker(ontology, corpus, state["nodes"], known_ids)
        key = item_key(item, lineno)
        if "__parse_error__" in item:
            checker.err("BAD_JSON_LINE", "line %d: %s" % (lineno, item["__parse_error__"]))
            item = {"op": None, "__raw__": item["__raw__"]}
        checker.check(item, lineno)
        if checker.errors:
            for e in checker.errors:
                violations[e["code"]] = violations.get(e["code"], 0) + 1
            rejected_this.append({"key": key, "pass": pass_no,
                                  "repair_pass": bool(args.repair),
                                  "final": bool(args.repair),
                                  "error_codes": sorted({e["code"] for e in checker.errors}),
                                  "errors": sorted(checker.errors,
                                                   key=lambda x: (x["code"], x["message"])),
                                  "item": item})
        else:
            op = item.get("op")
            if args.repair and isinstance(item.get("id"), str):
                # repaired: drop any old quarantine entry for this id
                state["quarantine"].pop(item["id"], None)
            if op == "node":
                state["nodes"][item["id"]] = item
                known_ids.add(item["id"])
            elif op == "edge":
                state["edges"][item["id"]] = item
                known_ids.add(item["id"])
            elif op == "merge":
                state["merges"].append(item)
            elif op == "nonmerge":
                state["nonmerges"].append(item)
            elif op == "unreported":
                state["unreported"].append(item)
            elif op == "note":
                state["notes"].append(item)
            accepted_this.append(key)

    # fold rejects into persistent quarantine (replace same-key entry)
    for rej in rejected_this:
        state["quarantine"][rej["key"]] = rej

    state["passes_completed"] = pass_no
    if args.repair:
        # the repair budget is now spent: everything still quarantined is final
        for entry in state["quarantine"].values():
            entry["final"] = True
    pass_report = {
        "pass": pass_no,
        "kind": "repair" if args.repair else "draft",
        "extraction_file": os.path.basename(args.extraction),
        "lines_total": len(raw_lines),
        "items_parsed": len(parsed),
        "accepted": len(accepted_this),
        "quarantined": len(rejected_this),
        "violations_by_code": {k: violations[k] for k in sorted(violations)},
    }
    state["report"]["passes"].append(pass_report)
    cum = state["report"]["cumulative_violations"]
    for code, n in violations.items():
        cum[code] = cum.get(code, 0) + n

    # deterministic validated.jsonl
    ops = list(state["nodes"].values()) + list(state["edges"].values())
    ops += state["merges"] + state["nonmerges"] + state["unreported"] + state["notes"]
    def sort_key(o):
        return (o.get("op") or "", o.get("id") or o.get("item") or o.get("keep") or "")
    with open(os.path.join(args.work, "validated.jsonl"), "w", encoding="utf-8") as fh:
        for op in sorted(ops, key=sort_key):
            fh.write(json.dumps(op, ensure_ascii=False, sort_keys=True) + "\n")

    quarantine = {
        "description": "Items rejected by the closed-ontology validator, with typed error codes.",
        "repair_budget": {"max_repair_passes":
                          ontology.get("repair_policy", {}).get("max_repair_passes", 1),
                          "repair_passes_used": state["repair_used"]},
        "count": len(state["quarantine"]),
        "items": [state["quarantine"][k] for k in sorted(state["quarantine"])],
    }
    report = {
        "ontology_id": ontology.get("ontology_id"),
        "ontology_version": ontology.get("version"),
        "passes": state["report"]["passes"],
        "cumulative_violations": {k: cum[k] for k in sorted(cum)},
        "current_quarantine_count": len(state["quarantine"]),
        "validated_counts": {
            "nodes": len(state["nodes"]),
            "edges": len(state["edges"]),
            "merges": len(state["merges"]),
            "nonmerges": len(state["nonmerges"]),
            "unreported": len(state["unreported"]),
            "notes": len(state["notes"]),
        },
        "repair_budget": quarantine["repair_budget"],
    }
    dump_json(os.path.join(args.work, "validation_state.json"), state)
    dump_json(os.path.join(args.work, "quarantine.json"), quarantine)
    dump_json(os.path.join(args.work, "validation_report.json"), report)

    print("validate pass %d (%s): %d accepted, %d quarantined; violations=%s"
          % (pass_no, pass_report["kind"], len(accepted_this), len(rejected_this),
             json.dumps(pass_report["violations_by_code"], sort_keys=True)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
