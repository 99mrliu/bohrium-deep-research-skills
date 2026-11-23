#!/usr/bin/env python3
"""Identity resolver for literature-extracted data cleaning.

Pipeline: ingest (nested JSON / CSV) -> cautious normalization ->
identity keys -> deterministic duplicate adjudication -> conservative
clustering -> traceable outputs.

Stdlib only, Python 3.10+. Deterministic: no timestamps, no randomness,
all ordering explicit. An honest partial result.json is written before
any heavy work and upgraded stage by stage; unreadable or malformed
input yields status=input_error instead of a crash.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lexicon as L          # noqa: E402
import identity as I         # noqa: E402

CONTAINER_KEYS = (
    "studies", "experiments", "samples", "measurements", "records", "rows",
    "data", "results", "entries", "extractions", "tables", "observations",
    "items", "measurements_table",
)
META_KEYS = {"case_id", "id", "case", "output_contract", "synthetic", "task",
             "description", "version"}


# --------------------------------------------------------------------------
# ingestion

def ingest_json(obj, field_map, anomalies):
    """Flatten nested JSON into a list of raw record dicts."""
    records: list[dict] = []

    def walk(node, inherited):
        if isinstance(node, list):
            for item in node:
                walk(item, inherited)
            return
        if not isinstance(node, dict):
            return
        # CSV-shaped table inside JSON
        cols = node.get("columns")
        rows = node.get("rows")
        if (isinstance(cols, list) and isinstance(rows, list) and rows
                and all(isinstance(r, (list, tuple)) for r in rows)
                and len(node.get("columns") or []) > 0
                and not any(k in node for k in CONTAINER_KEYS if k != "rows")):
            base = dict(inherited)
            for r_i, row in enumerate(rows, 1):
                rec = dict(base)
                for c, v in zip(cols, row):
                    rec[str(c)] = v
                records.append(rec)
            return
        child_inherited = dict(inherited)
        produced_before = len(records)
        # pass 1: inherit all scalars (order-independent) and flatten
        # nested source/study objects
        for key in sorted(node.keys()):
            val = node[key]
            if isinstance(val, (str, int, float, bool)) or val is None:
                child_inherited[key] = val
            elif isinstance(val, dict) and L.norm_token(key) in (
                    "source", "study", "paper", "citation"):
                for sk, sv in val.items():
                    if isinstance(sv, (str, int, float)):
                        child_inherited.setdefault(str(sk), sv)
        # pass 2: recurse into containers with the complete context
        for key in sorted(node.keys()):
            val = node[key]
            if key in CONTAINER_KEYS and isinstance(val, (list, dict)):
                walk(val, child_inherited)
        if len(records) > produced_before:
            return  # this node was a container
        # leaf: is it record-like?
        if any(L.norm_token(k) in field_map for k in node.keys()):
            rec = dict(child_inherited)
            for k, v in node.items():
                if isinstance(v, dict) and L.norm_token(k) in ("source", "study", "paper"):
                    for sk, sv in v.items():
                        if isinstance(sv, (str, int, float)) and sk not in rec:
                            rec[sk] = sv
                elif k not in CONTAINER_KEYS or not isinstance(v, (list, dict)):
                    if not isinstance(v, (list, dict)):
                        rec[k] = v
            records.append(rec)

    walk(obj, {})
    return records


def ingest_csv(path: Path):
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def extract_contract(obj) -> dict[str, str]:
    """Normalize any reasonable output_contract shape to {name: type}."""
    out: dict[str, str] = {}
    if not isinstance(obj, dict):
        return out
    oc = obj.get("output_contract")
    if isinstance(oc, dict):
        fields = oc.get("fields")
        if isinstance(fields, list):
            for f in fields:
                if isinstance(f, str):
                    out[f] = "unknown"
                elif isinstance(f, dict) and f.get("name"):
                    out[str(f["name"])] = str(f.get("type", "unknown"))
        elif isinstance(fields, dict):
            for k, v in fields.items():
                out[str(k)] = str(v.get("type", "unknown")) if isinstance(v, dict) else str(v)
        else:
            for k, v in oc.items():
                out[str(k)] = str(v.get("type", "unknown")) if isinstance(v, dict) else str(v)
    elif isinstance(oc, list):
        for f in oc:
            if isinstance(f, str):
                out[f] = "unknown"
            elif isinstance(f, dict) and f.get("name"):
                out[str(f["name"])] = str(f.get("type", "unknown"))
    return out


# --------------------------------------------------------------------------
# normalization

def normalize_record(raw: dict, record_id: str, lex: dict, field_map,
                     changes, anomalies):
    rec = {
        "record_id": record_id,
        "source_label": None, "source_key": None, "locator": None,
        "experiment_label": None,
        "material": None, "material_display": None, "phase": None,
        "dopant": None, "composition": None, "morphology": None,
        "metric": None, "metric_display": None,
        "value_raw": None, "value_kind": "missing", "value": None,
        "value_min": None, "value_max": None, "value_text": None,
        "value_token": None,
        "unit": None, "unit_status": "missing",
        "value_normalized": None, "unit_normalized": None,
        "conversion_formula": None,
        "context": {}, "extra": {}, "original": raw, "blockable": True,
    }

    # ---- F-001: field mapping
    mapped: dict[str, object] = {}
    for key in sorted(raw.keys()):
        canon = field_map.get(L.norm_token(key))
        if canon and canon not in mapped:
            mapped[canon] = raw[key]
        elif canon is None and isinstance(raw[key], (str, int, float)):
            rec["extra"][str(L.normalize_text(key))] = L.normalize_text(raw[key])
    unmapped_fields = sorted(rec["extra"].keys())

    changes_done = []

    def log(rule, field, before, after, detail=""):
        changes_done.append({
            "record_id": record_id, "rule_id": rule, "field": field,
            "before": before, "after": after, "detail": detail})

    # ---- source identity (kept strict: merges never cross sources)
    src = mapped.get("source")
    if src is None:
        for k in ("doi", "title", "reference", "citation"):
            if raw.get(k):
                src = raw[k]
                break
    if src is None or str(src).strip() == "":
        rec["source_label"] = None
        rec["source_key"] = "source:unspecified"
        anomalies.append({"rule_id": "C-002", "kind": "missing_source",
                          "severity": "review", "record_id": record_id,
                          "detail": "no source identifier; dedup with other "
                                    "unspecified-source rows is restricted to "
                                    "exact fingerprint matches"})
    else:
        rec["source_label"] = L.normalize_text(src)
        rec["source_key"] = "source:" + (L.norm_token(src) or "unspecified")

    rec["locator"] = L.normalize_text(mapped.get("locator"))
    rec["experiment_label"] = L.normalize_text(mapped.get("experiment"))

    # ---- N-001..N-005: material identity
    mat_raw = mapped.get("material")
    minfo = L.canonical_material(mat_raw, lex)
    rec["material"] = minfo["canonical"]
    rec["material_display"] = minfo["display"]
    if minfo["canonical"] is None:
        anomalies.append({"rule_id": "C-001", "kind": "missing_material",
                          "severity": "review", "record_id": record_id,
                          "detail": "no material name; record excluded from "
                                    "duplicate blocking"})
        rec["blockable"] = False
    else:
        if minfo["matched_alias"] and L.norm_token(mat_raw) != L.norm_token(minfo["canonical"]):
            log("N-003", "material", minfo["display"], minfo["canonical"],
                "exact full-string lexicon alias")
        if "phase_split" in minfo["notes"]:
            log("N-004", "material", minfo["display"], minfo["canonical"],
                f"phase '{minfo['phase']}' split out of material string")
        if "dopant_split" in minfo["notes"]:
            log("N-005", "material", minfo["display"], minfo["canonical"],
                f"dopant '{minfo['dopant']}' split out of material string; "
                "dopant remains part of sample identity")
        if "lexicon_miss" in minfo["notes"]:
            anomalies.append({"rule_id": "N-006", "kind": "lexicon_miss",
                              "severity": "info", "record_id": record_id,
                              "detail": f"material '{minfo['display']}' not in "
                                        "lexicon; normalized token used as its "
                                        "own identity (no merging by similarity)"})
    # phase: explicit field wins over extracted
    explicit_phase = L.canonical_phase(mapped.get("phase"), lex)
    rec["phase"] = explicit_phase or minfo["phase"]
    rec["dopant"] = L.norm_token(mapped.get("dopant")) or minfo["dopant"]
    rec["composition"] = L.norm_token(mapped.get("composition"))
    rec["morphology"] = L.norm_token(mapped.get("morphology"))

    # ---- metric
    metric_info = L.canonical_metric(mapped.get("metric"), lex)
    rec["metric"] = metric_info["canonical"]
    rec["metric_display"] = metric_info["display"]
    if rec["metric"] is None:
        anomalies.append({"rule_id": "C-001", "kind": "missing_metric",
                          "severity": "review", "record_id": record_id,
                          "detail": "no metric name; record excluded from "
                                    "duplicate blocking"})
        rec["blockable"] = False
    elif metric_info["matched_alias"] and \
            L.norm_token(mapped.get("metric")) != rec["metric"]:
        log("N-003", "metric", metric_info["display"], rec["metric"],
            "metric alias canonicalization")
    spec = lex.get("metric_specs", {}).get(rec["metric"] or "", {})

    # ---- value & unit (V-001..V-005, U-001..U-004)
    val_raw = mapped.get("value")
    unit_raw = mapped.get("unit")
    if unit_raw in (None, "") and val_raw is not None:
        split = L.split_value_unit(val_raw)
        if split:
            val_raw, unit_raw = split
            log("V-005", "value", mapped.get("value"), val_raw,
                f"unit '{unit_raw}' split out of value string")
    v = L.parse_value(val_raw)
    rec["value_raw"] = L.normalize_text(val_raw)
    rec["value_kind"] = v["kind"]
    if v["kind"] == "scalar":
        rec["value"] = v["value"]
        if str(v.get("raw")) != str(rec["value_raw"]) or (
                isinstance(val_raw, str) and "," in val_raw):
            log("V-001", "value", rec["value_raw"], v["value"],
                "numeric formatting normalized (value itself unchanged)")
    elif v["kind"] == "range":
        rec["value_min"], rec["value_max"] = v["min"], v["max"]
        log("V-002", "value", rec["value_raw"],
            f"[{v['min']}, {v['max']}]", "range parsed; kept as interval, "
            "no midpoint is fabricated")
        anomalies.append({"rule_id": "V-002", "kind": "range_value",
                          "severity": "info", "record_id": record_id,
                          "detail": "interval value kept as min/max; no "
                                    "midpoint fabricated"})
    elif v["kind"] == "missing" and v.get("explicit"):
        log("V-003", "value", v.get("raw"), None,
            "explicit missing token normalized to null (stays null)")
        anomalies.append({"rule_id": "V-003", "kind": "missing_value",
                          "severity": "review", "record_id": record_id,
                          "detail": f"missing value token '{v.get('raw')}' "
                                    "normalized to null"})
    elif v["kind"] == "text":
        rec["value_text"] = L.norm_token(v.get("raw"))
        anomalies.append({"rule_id": "V-006", "kind": "non_numeric_value",
                          "severity": "review", "record_id": record_id,
                          "detail": f"non-numeric value '{v.get('raw')}' kept "
                                    "as text; not merged by numeric comparison"})

    uinfo = L.normalize_unit(unit_raw, lex)
    rec["unit"] = uinfo.get("unit_raw")
    rec["unit_status"] = uinfo["status"]
    if uinfo["status"] == "unknown":
        anomalies.append({"rule_id": "U-003", "kind": "unknown_unit",
                          "severity": "review", "record_id": record_id,
                          "detail": f"unit '{uinfo['unit_raw']}' not in unit "
                                    "table; no conversion attempted, value "
                                    "compared raw only"})
    elif uinfo["status"] == "missing" and rec["value_kind"] in ("scalar", "range"):
        anomalies.append({"rule_id": "U-004", "kind": "missing_unit",
                          "severity": "review", "record_id": record_id,
                          "detail": "value present but unit missing; "
                                    "normalized value stays null"})
    elif uinfo["status"] == "known":
        if L.norm_token(unit_raw) != uinfo.get("unit_key"):
            log("U-001", "unit", uinfo["unit_raw"], uinfo["entry"]["canonical"],
                "unit alias/normalization")
        conv = L.convert_value(rec["value"] if rec["value_kind"] == "scalar" else None,
                               uinfo, spec.get("dimension"),
                               spec.get("canonical_unit"), lex)
        if conv:
            rec["value_normalized"] = conv["value"]
            rec["unit_normalized"] = conv["unit"]
            rec["conversion_formula"] = conv["formula"]
            if conv["formula"] != "identity (unit already canonical)" or \
                    rec["value"] != conv["value"]:
                log("U-002", "value", f"{rec['value']} {uinfo['unit_raw']}",
                    f"{conv['value']} {conv['unit']}",
                    f"converted with formula: value = raw {conv['formula']}; "
                    "original value retained in value_raw")
        elif rec["value_kind"] == "scalar" and rec["value"] is not None:
            if spec.get("dimension") and uinfo["entry"].get("dimension") != spec["dimension"]:
                anomalies.append({"rule_id": "U-005", "kind": "unit_dimension_mismatch",
                                  "severity": "review", "record_id": record_id,
                                  "detail": f"unit dimension "
                                            f"'{uinfo['entry'].get('dimension')}' "
                                            f"does not match metric expectation "
                                            f"'{spec.get('dimension')}'; left "
                                            "unconverted"})
            elif spec.get("canonical_unit"):
                rec["value_normalized"] = rec["value"]
                rec["unit_normalized"] = uinfo["entry"]["canonical"]
                rec["conversion_formula"] = "identity (metric accepts this unit)"

    # plausible range check (A-001) on normalized scalar
    pr = spec.get("plausible_range")
    if pr and rec["value_normalized"] is not None:
        if not (pr[0] <= rec["value_normalized"] <= pr[1]):
            anomalies.append({"rule_id": "A-001", "kind": "out_of_plausible_range",
                              "severity": "review", "record_id": record_id,
                              "detail": f"normalized value "
                                        f"{rec['value_normalized']} "
                                        f"{rec['unit_normalized']} outside "
                                        f"plausible range {pr}; value kept "
                                        "unchanged, flagged for review"})

    # value token for cross-source corroboration blocking
    if rec["value_kind"] == "scalar" and rec["value"] is not None:
        if rec["value_normalized"] is not None:
            rec["value_token"] = f"{rec['value_normalized']:g}|{rec['unit_normalized']}"
        else:
            rec["value_token"] = f"{rec['value']:g}|raw|{rec['unit'] or '?'}"
    elif rec["value_kind"] == "range":
        rec["value_token"] = f"range:{rec['value_min']:g}-{rec['value_max']:g}|{rec['unit'] or '?'}"
    elif rec["value_kind"] == "text":
        rec["value_token"] = "text:" + (rec["value_text"] or "")

    # ---- context (never merged across differing contexts)
    ctx = {}
    for field in lex.get("context_fields", []):
        raw_val = mapped.get(field)
        if raw_val is None or L.norm_token(raw_val) in (None, ""):
            ctx[field] = None
            continue
        if field in ("temperature", "pressure"):
            sval, sunit = L.split_value_unit(raw_val) or (raw_val, None)
            pv = L.parse_value(sval)
            if pv["kind"] == "scalar":
                u2 = L.normalize_unit(sunit, lex)
                dim = "temperature" if field == "temperature" else "pressure"
                target = "K" if field == "temperature" else "kPa"
                conv = L.convert_value(pv["value"], u2, dim, target, lex)
                if conv:
                    ctx[field] = f"{conv['value']:g} {conv['unit']}"
                    if conv["formula"] != "identity (unit already canonical)":
                        log("U-002", field, f"{pv['value']} {u2['unit_raw']}",
                            ctx[field],
                            f"context normalized: {conv['formula']}")
                else:
                    ctx[field] = (f"{pv['value']:g}"
                                  + (f" {u2['unit_raw']}" if u2.get("unit_raw") else "")
                                  + (" [unit-unresolved]" if u2["status"] != "known" else ""))
                    if u2["status"] in ("unknown",):
                        anomalies.append({"rule_id": "U-003", "kind": "unknown_unit",
                                          "severity": "review",
                                          "record_id": record_id,
                                          "detail": f"context {field} unit "
                                                    f"'{u2['unit_raw']}' unknown"})
            else:
                ctx[field] = L.norm_token(raw_val)
        else:
            ctx[field] = L.norm_token(raw_val)
    rec["context"] = ctx

    rec["_changes"] = changes_done
    rec["_unmapped_fields"] = unmapped_fields
    return rec


# --------------------------------------------------------------------------
# outputs

CLEANED_COLUMNS = [
    "cluster_id", "experiment_id", "experiment_label", "record_id",
    "member_count", "member_record_ids",
    "material", "material_display", "phase", "dopant", "composition",
    "morphology", "sample_key", "metric", "value_raw", "value_kind", "value",
    "value_min", "value_max", "unit", "value_normalized", "unit_normalized",
    "conversion_formula", "context_key", "source", "locator",
    "conflict_cluster_ids", "review_flags",
]


def write_outputs(out_dir: Path, case_id, records, clusters, candidates,
                  anomalies, review_queue, changes, sources, invariants,
                  contract, contract_values, unresolved, status, summary,
                  synthetic, task_info, counts, lex):
    out_dir.mkdir(parents=True, exist_ok=True)

    def dump(name, obj):
        with open(out_dir / name, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")

    # ---- cleaned records (cluster representatives; members retained in JSON)
    conflict_links = {}
    cl_of = {}
    for c in clusters:
        for m in c["members"]:
            cl_of[m["record_id"]] = c["cluster_id"]
    for c in candidates:
        if c["state"] == "conflict":
            a, b = c["pair"]
            conflict_links.setdefault(cl_of[a], set()).add(cl_of[b])
            conflict_links.setdefault(cl_of[b], set()).add(cl_of[a])

    rows_json = []
    for c in clusters:
        rep = c["representative"]
        flags = sorted({a["kind"] for a in anomalies
                        if a["record_id"] in [m["record_id"] for m in c["members"]]})
        row = {
            "cluster_id": c["cluster_id"],
            "experiment_id": c["experiment_id"],
            "experiment_label": rep["experiment_label"],
            "record_id": rep["record_id"],
            "member_count": c["size"],
            "member_record_ids": [m["record_id"] for m in c["members"]],
            "material": rep["material"],
            "material_display": rep["material_display"],
            "phase": rep["phase"], "dopant": rep["dopant"],
            "composition": rep["composition"], "morphology": rep["morphology"],
            "sample_key": I.sample_key(rep),
            "metric": rep["metric"],
            "value_raw": rep["value_raw"], "value_kind": rep["value_kind"],
            "value": rep["value"], "value_min": rep["value_min"],
            "value_max": rep["value_max"], "unit": rep["unit"],
            "value_normalized": rep["value_normalized"],
            "unit_normalized": rep["unit_normalized"],
            "conversion_formula": rep["conversion_formula"],
            "context_key": I.context_key(rep),
            "source": rep["source_label"], "locator": rep["locator"],
            "conflict_cluster_ids": sorted(conflict_links.get(c["cluster_id"], [])),
            "review_flags": flags,
            "members": [{
                "record_id": m["record_id"], "role": m["role"],
                "source": m["source_label"], "locator": m["locator"],
                "experiment_label": m["experiment_label"],
                "material_raw": m["original"],
                "value_raw": m["value_raw"], "unit": m["unit"],
                "value_normalized": m["value_normalized"],
            } for m in c["members"]],
        }
        rows_json.append(row)
    dump("cleaned_records.json", {"case_id": case_id, "synthetic_input": synthetic,
                                  "row_count": len(rows_json), "rows": rows_json})

    with open(out_dir / "cleaned_records.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CLEANED_COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows_json:
            flat = {k: r.get(k) for k in CLEANED_COLUMNS}
            flat["member_record_ids"] = ";".join(r["member_record_ids"])
            flat["conflict_cluster_ids"] = ";".join(r["conflict_cluster_ids"])
            flat["review_flags"] = ";".join(r["review_flags"])
            for k, v in flat.items():
                if v is None:
                    flat[k] = ""
                elif isinstance(v, (int, float)):
                    flat[k] = f"{v:g}" if isinstance(v, float) else str(v)
            w.writerow(flat)

    # ---- duplicate report
    state_counts = {}
    for c in candidates:
        state_counts[c["state"]] = state_counts.get(c["state"], 0) + 1
    dump("duplicate_report.json", {
        "case_id": case_id, "synthetic_input": synthetic,
        "method": "deterministic blocking + pairwise evidence adjudication; "
                  "only exact_duplicate and likely_duplicate pairs are merged; "
                  "conflict/review/not_duplicate rows are never merged and "
                  "conflicting values are never averaged",
        "candidate_state_counts": state_counts,
        "candidates": candidates,
        "clusters": [{
            "cluster_id": c["cluster_id"], "experiment_id": c["experiment_id"],
            "representative_record_id": c["representative"]["record_id"],
            "merge_rule": c["merge_rule"],
            "member_record_ids": [m["record_id"] for m in c["members"]],
            "sample_key": I.sample_key(c["representative"]),
            "metric": c["representative"]["metric"],
            "source": c["representative"]["source_label"],
        } for c in clusters],
    })

    # ---- review queue + anomalies
    dump("review_queue.json", {
        "case_id": case_id, "synthetic_input": synthetic,
        "note": "items the tool refuses to decide automatically; nothing here "
                "was merged or altered silently",
        "review_items": review_queue,
        "anomalies": anomalies,
    })

    # ---- change log
    dump("change_log.json", {
        "case_id": case_id, "synthetic_input": synthetic,
        "note": "every automated change carries a rule id (see "
                "references/identity-adjudication.md); before/after keep the "
                "original string so each change traces back to the input row "
                "and source locator",
        "change_count": len(changes), "changes": changes,
    })

    # ---- result.json
    artifacts = {
        "cleaned_records_csv": "cleaned_records.csv",
        "cleaned_records_json": "cleaned_records.json",
        "duplicate_report": "duplicate_report.json",
        "review_queue": "review_queue.json",
        "change_log": "change_log.json",
        "audit": "audit.md",
    }
    result = {
        "case_id": case_id,
        "synthetic_input": synthetic,
        "status": status,
        "summary": summary,
        "counts": counts,
        "sources": sources,
        "uncertainty": sorted({a["detail"] for a in anomalies
                               if a["severity"] == "review"} | {
                               f"{len(review_queue)} item(s) require human "
                               "adjudication (see review_queue.json)"}
                              ) if (anomalies or review_queue) else [],
        "unresolved": unresolved,
        "change_records": changes,
        "invariants": invariants,
        "artifacts": artifacts,
        "task_file": task_info,
        "lexicon": {"path": "references/synonyms.json",
                    "version": lex.get("_version", "unknown")},
    }
    for name, value in contract_values.items():
        result[name] = value
    result["output_contract"] = contract
    dump("result.json", result)

    # ---- audit.md
    lines = []
    lines.append(f"# Audit — identity resolver — case `{case_id}`")
    lines.append("")
    if synthetic:
        lines.append("> **SYNTHETIC EXAMPLE RUN** — input is marked synthetic "
                     "data for demonstration/self-check, not real literature.")
        lines.append("")
    lines.append(f"- status: `{status}`")
    lines.append(f"- lexicon: references/synonyms.json v{lex.get('_version')}")
    lines.append(f"- input records: {counts['input_records']}")
    lines.append(f"- output rows (clusters): {counts['output_rows']}")
    lines.append(f"- rows merged as duplicates: {counts['merged_rows']}")
    st = counts["candidate_states"]
    lines.append(f"- candidate pairs: exact_duplicate={st.get('exact_duplicate', 0)}, "
                 f"likely_duplicate={st.get('likely_duplicate', 0)}, "
                 f"conflict={st.get('conflict', 0)}, "
                 f"review={st.get('review', 0)}, "
                 f"not_duplicate={st.get('not_duplicate', 0)}")
    lines.append(f"- review queue items: {len(review_queue)}; anomalies: {len(anomalies)}")
    lines.append(f"- rule-coded changes: {len(changes)}")
    lines.append("")
    lines.append("## Sources")
    lines.append("")
    for s in sources:
        lines.append(f"- `{s['source_key']}` ({s['source_label']}): "
                     f"{s['record_count']} record(s); locators: "
                     + (", ".join(s["locators"]) if s["locators"] else "(none given)"))
    lines.append("")
    lines.append("## Invariants (self-check executed every run)")
    lines.append("")
    for chk in invariants:
        mark = "PASS" if chk["passed"] else "FAIL"
        lines.append(f"- [{mark}] {chk['name']}: {chk['detail']}")
    lines.append("")
    lines.append("## Rules applied (counts)")
    lines.append("")
    rule_counts = {}
    for ch in changes:
        rule_counts[ch["rule_id"]] = rule_counts.get(ch["rule_id"], 0) + 1
    for a in anomalies:
        rule_counts[a["rule_id"]] = rule_counts.get(a["rule_id"], 0) + 1
    if rule_counts:
        for r in sorted(rule_counts):
            lines.append(f"- {r}: {rule_counts[r]}")
    else:
        lines.append("- (no changes or anomalies)")
    lines.append("")
    lines.append("## Unresolved / human takeover points")
    lines.append("")
    if unresolved:
        for u in unresolved:
            lines.append(f"- {u['item']}: {u['reason']}"
                         + (f" ({u['location']})" if u.get("location") else ""))
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Output contract coverage")
    lines.append("")
    if contract:
        for name in sorted(contract):
            val = contract_values.get(name)
            state = "null (unresolved)" if val is None else "filled"
            lines.append(f"- `{name}` ({contract[name]}): {state}")
    else:
        lines.append("- input provided no output_contract")
    lines.append("")
    lines.append("## Traceability")
    lines.append("")
    lines.append("- `change_log.json`: every automated change with rule id, "
                 "before/after, input record id.")
    lines.append("- `duplicate_report.json`: every candidate pair with evidence "
                 "and decision rule; clusters keep all member rows and the "
                 "representative selection rule D-008.")
    lines.append("- `cleaned_records.json`: per-row `members[]` lineage back to "
                 "original raw rows, sources and locators.")
    lines.append("- Determinism: output contains no timestamps, absolute paths "
                 "or randomness; identical input yields byte-identical output.")
    lines.append("")
    with open(out_dir / "audit.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# --------------------------------------------------------------------------
# contract semantics

def map_contract_field(name: str, expected_type: str, payload: dict):
    """Fill a contract field only when its name has an unambiguous semantic
    match to a computed artifact. Otherwise return None (stays null and is
    listed in unresolved)."""
    n = L.norm_token(name) or ""
    value = None
    if any(t in n for t in ("cleaned", "table", "record", "data")):
        value = {"path": "cleaned_records.csv",
                 "json": "cleaned_records.json",
                 "row_count": payload["counts"]["output_rows"],
                 "columns": CLEANED_COLUMNS}
    elif any(t in n for t in ("cluster", "duplicate", "dedup")):
        value = payload["cluster_summaries"]
    elif any(t in n for t in ("review", "anomal", "uncertain", "unresolved")):
        value = [{"id": q["id"], "kind": q["kind"], "rule": q.get("rule_id"),
                  "detail": q["detail"]} for q in payload["review_queue"]]
    elif "audit" in n or "trace" in n or "lineage" in n:
        value = "audit.md"
    elif "source" in n or "evidence" in n:
        value = [s["source_key"] for s in payload["sources"]]
    elif any(t in n for t in ("summary", "answer", "response", "result", "report")):
        value = payload["summary"]
    if value is None:
        return None
    if expected_type == "string" and not isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if expected_type == "list" and not isinstance(value, list):
        return [value]
    if expected_type == "dict" and not isinstance(value, dict):
        return {"value": value}
    return value


# --------------------------------------------------------------------------

def write_partial(out_dir: Path, case_id, status, stage, error=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    partial = {
        "case_id": case_id, "status": status, "stage": stage,
        "summary": (f"partial result: pipeline stopped at stage '{stage}'"
                    + (f" ({error})" if error else "")),
        "sources": [], "uncertainty": ([f"pipeline incomplete: {error}"]
                                       if error else []),
        "unresolved": [{"item": "full_pipeline", "reason": error or stage,
                        "location": "identity_resolver.py"}],
        "change_records": [], "artifacts": {}, "output_contract": {},
    }
    with open(out_dir / "result.json", "w", encoding="utf-8") as fh:
        json.dump(partial, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    with open(out_dir / "audit.md", "w", encoding="utf-8") as fh:
        fh.write(f"# Audit (partial) — case `{case_id}`\n\n"
                 f"- status: `{status}`\n- stage: `{stage}`\n"
                 + (f"- error: {error}\n" if error else ""))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Identity resolver: cautious duplicate adjudication and "
                    "conservative merging for literature-extracted data.")
    ap.add_argument("--case", default="/input/case.json",
                    help="input case file: JSON (flat or nested) or CSV")
    ap.add_argument("--task", default="/input/task.md",
                    help="task description file (read for audit only)")
    ap.add_argument("--work", default="/app/work",
                    help="working directory (intermediate files)")
    ap.add_argument("--out", default="/app/output",
                    help="output directory for final artifacts")
    ap.add_argument("--lexicon", default=None,
                    help="path to a customized synonym lexicon JSON "
                         "(default: references/synonyms.json next to scripts/)")
    args = ap.parse_args(argv)

    out_dir = Path(args.out)
    work_dir = Path(args.work)
    case_path = Path(args.case)

    # --- honest partial first
    write_partial(out_dir, "unknown", "partial", "initializing")

    lex = L.load_lexicon(args.lexicon)
    field_map = L.build_field_map(lex)

    # --- read input
    case_id = "unknown"
    contract: dict[str, str] = {}
    raw_records: list[dict] = []
    anomalies: list[dict] = []
    synthetic = False

    if not case_path.exists():
        write_partial(out_dir, case_id, "input_error", "read_input",
                      f"input file not found: {args.case}")
        return 2
    try:
        if case_path.suffix.lower() == ".csv":
            raw_records = ingest_csv(case_path)
            case_id = case_path.stem
        else:
            with open(case_path, "r", encoding="utf-8-sig") as fh:
                obj = json.load(fh)
            if isinstance(obj, dict):
                case_id = str(obj.get("case_id") or obj.get("id")
                              or case_path.stem)
                contract = extract_contract(obj)
                synthetic = bool(obj.get("synthetic", False))
            else:
                case_id = case_path.stem
            raw_records = ingest_json(obj, field_map, anomalies)
            if isinstance(obj, list):
                raw_records = [r for r in obj if isinstance(r, dict)] \
                    if not raw_records else raw_records
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        write_partial(out_dir, case_id, "input_error", "parse_input", str(exc))
        return 2
    except OSError as exc:
        write_partial(out_dir, case_id, "input_error", "read_input", str(exc))
        return 2

    write_partial(out_dir, case_id, "partial", "ingested")

    # keep only dict rows
    valid_raw = []
    for idx, r in enumerate(raw_records, 1):
        if isinstance(r, dict):
            valid_raw.append(r)
        else:
            anomalies.append({"rule_id": "C-003", "kind": "row_skipped",
                              "severity": "review", "record_id": f"r{idx:04d}",
                              "detail": "input row is not an object; skipped"})

    # task file (audit only)
    task_info = {"path": Path(args.task).name, "found": False, "title": None}
    try:
        tp = Path(args.task)
        if tp.exists():
            text = tp.read_text(encoding="utf-8", errors="replace")
            task_info["found"] = True
            for line in text.splitlines():
                if line.strip():
                    task_info["title"] = line.strip().lstrip("# ").strip()[:120]
                    break
    except OSError:
        pass

    # --- normalize
    records, changes = [], []
    seen_ids: set[str] = set()
    for idx, raw in enumerate(valid_raw, 1):
        rid = str(raw.get("record_id") or raw.get("id") or f"r{idx:04d}")
        if rid in seen_ids:
            suffix = 2
            while f"{rid}-{suffix}" in seen_ids:
                suffix += 1
            changes.append({"record_id": rid, "rule_id": "C-004",
                            "field": "record_id", "before": rid,
                            "after": f"{rid}-{suffix}",
                            "detail": "duplicate input record id; suffixed to "
                                      "keep lineage unambiguous"})
            rid = f"{rid}-{suffix}"
        seen_ids.add(rid)
        rec = normalize_record(raw, rid, lex, field_map, changes, anomalies)
        rec["_seq"] = idx
        records.append(rec)
    for rec in records:
        changes.extend(rec.pop("_changes"))

    # unmapped fields inventory (global info anomaly)
    all_unmapped = sorted({f for rec in records for f in rec["_unmapped_fields"]})
    if all_unmapped:
        anomalies.append({"rule_id": "F-002", "kind": "unmapped_fields",
                          "severity": "info", "record_id": "*",
                          "detail": "input columns with no canonical mapping "
                                    "(kept verbatim in record extras): "
                                    + ", ".join(all_unmapped)})

    work_dir.mkdir(parents=True, exist_ok=True)
    with open(work_dir / "normalized_records.json", "w", encoding="utf-8") as fh:
        json.dump([{k: v for k, v in r.items() if k != "original"}
                   for r in records], fh, ensure_ascii=False, indent=2,
                  sort_keys=True)
        fh.write("\n")

    status, note = "success", ""
    if not records:
        status, note = "partial", "no usable records in input (empty table or "
        "all rows skipped)"

    # --- dedup
    candidates = I.generate_candidates(records)
    clusters = I.cluster_records(records, candidates)
    invariants = I.run_invariants(clusters, candidates)
    if not all(c["passed"] for c in invariants):
        status = "partial"
        note = (note + "; " if note else "") + \
            "one or more internal invariants failed; see audit.md"

    # dedup change entries (D-008/D-009/D-004 retention actions)
    for c in clusters:
        for m in c["members"]:
            if m["role"] == "representative" and c["size"] > 1:
                changes.append({"record_id": m["record_id"], "rule_id": "D-008",
                                "field": "cluster", "before": None,
                                "after": c["cluster_id"],
                                "detail": "chosen as cluster representative "
                                          "(most complete row, then smallest "
                                          "record id); values never mixed "
                                          "across members"})
            elif m["role"] == "member":
                changes.append({"record_id": m["record_id"], "rule_id": "D-001/D-002",
                                "field": "cluster", "before": None,
                                "after": c["cluster_id"],
                                "detail": "merged as duplicate of cluster "
                                          "representative; original row retained "
                                          "in members[] lineage"})
    for c in candidates:
        if c["state"] in ("conflict", "review"):
            for rid in c["pair"]:
                changes.append({"record_id": rid, "rule_id": "D-009" if c["state"] == "conflict" else "D-004",
                                "field": "cluster", "before": None, "after": "kept_separate",
                                "detail": f"{c['state']} with {c['pair'][1] if c['pair'][0]==rid else c['pair'][0]}: {c['reason']}"})
    changes.sort(key=lambda ch: (ch["record_id"], ch["rule_id"], ch["field"]))
    for i, ch in enumerate(changes, 1):
        ch["change_id"] = f"ch{i:04d}"

    # review queue
    review_queue = []
    for c in candidates:
        if c["state"] in ("conflict", "review"):
            review_queue.append({"kind": c["state"], "rule_id": c["rule"],
                                 "record_ids": c["pair"],
                                 "detail": c["reason"], "score": c["score"]})
    for a in anomalies:
        if a["severity"] == "review":
            review_queue.append({"kind": a["kind"], "rule_id": a["rule_id"],
                                 "record_ids": [a["record_id"]],
                                 "detail": a["detail"], "score": 0})
    review_queue.sort(key=lambda q: (-q["score"], q["record_ids"], q["kind"]))
    for i, q in enumerate(review_queue, 1):
        q["id"] = f"q{i:04d}"

    # sources summary
    src_map: dict[str, dict] = {}
    for r in records:
        s = src_map.setdefault(r["source_key"], {
            "source_key": r["source_key"], "source_label": r["source_label"],
            "record_count": 0, "locators": []})
        s["record_count"] += 1
        if r["locator"]:
            s["locators"].append(r["locator"])
    sources = [src_map[k] for k in sorted(src_map)]

    # counts / summary
    state_counts: dict[str, int] = {}
    for c in candidates:
        state_counts[c["state"]] = state_counts.get(c["state"], 0) + 1
    merged_rows = sum(c["size"] - 1 for c in clusters)
    counts = {
        "input_records": len(records),
        "output_rows": len(clusters),
        "merged_rows": merged_rows,
        "conflict_pairs": state_counts.get("conflict", 0),
        "review_items": len(review_queue),
        "anomalies": len(anomalies),
        "changes": len(changes),
        "candidate_states": state_counts,
    }
    summary = (
        f"cleaned {len(records)} record(s) into {len(clusters)} row(s); "
        f"merged {merged_rows} duplicate row(s) by explainable keys; kept "
        f"{state_counts.get('conflict', 0)} conflict pair(s) separate "
        f"(never averaged); {len(review_queue)} item(s) queued for human "
        f"review; missing values/units left null."
        + (f" NOTE: {note}" if note else ""))

    # contract values
    payload = {"counts": counts,
               "cluster_summaries": [{
                   "cluster_id": c["cluster_id"],
                   "size": c["size"],
                   "representative_record_id": c["representative"]["record_id"],
                   "member_record_ids": [m["record_id"] for m in c["members"]],
               } for c in clusters],
               "review_queue": review_queue,
               "sources": sources,
               "summary": summary}
    contract_values = {}
    unresolved = []
    for name, typ in sorted(contract.items()):
        val = map_contract_field(name, typ, payload)
        contract_values[name] = val
        if val is None:
            unresolved.append({"item": f"output_contract.{name}",
                               "reason": "no unambiguous semantic mapping from "
                                         "this field name to a computed "
                                         "artifact; left null rather than "
                                         "fabricated",
                               "location": "result.json"})
    for a in anomalies:
        if a["severity"] == "review" and a["record_id"] != "*":
            unresolved.append({"item": f"{a['kind']}:{a['record_id']}",
                               "reason": a["detail"], "location": "review_queue.json"})
    if note:
        unresolved.append({"item": "pipeline_status", "reason": note,
                           "location": "audit.md"})

    write_outputs(out_dir, case_id, records, clusters, candidates, anomalies,
                  review_queue, changes, sources, invariants, contract,
                  contract_values, unresolved, status, summary, synthetic,
                  task_info, counts, lex)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # honest partial even on unexpected failure
        out = Path("/app/output")
        try:
            args_out = [a for i, a in enumerate(sys.argv)
                        if sys.argv[i - 1] == "--out"]
            if args_out:
                out = Path(args_out[-1])
        except Exception:
            pass
        write_partial(out, "unknown", "partial", "unexpected_error",
                      f"{type(exc).__name__}: {exc}")
        raise
