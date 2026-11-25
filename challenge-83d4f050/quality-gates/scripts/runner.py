#!/usr/bin/env python3
"""Atomic observed→specified→rendered→exported→audited→delivered runner.

The runner audits files and supplied Agent judgments; it never infers biology.
Fresh execution stops at audited/partial pending native visual review. `attest`
finishes delivered/complete after an Agent actually inspects PNG and PDF.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

BUNDLE = "quality-gates"
DEFAULT_CASE = Path("/app/case/quality-gates")
DEFAULT_WORK = Path("/app/work/quality-gates")
DEFAULT_OUTPUT = Path("/app/output/quality-gates")
STAGES = ["observed", "specified", "rendered", "exported", "audited", "delivered"]
META_FIELDS = {"case_id", "result_file_pointer", "asset_paths"}


class ContractError(Exception):
    pass


class ScientificError(Exception):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
        tmp = Path(f.name)
    os.replace(tmp, path)


def atomic_json(path: Path, value: object) -> None:
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ContractError(f"Expected JSON object: {path}")
    return value


def resolve_case(case_root: Path) -> tuple[dict, Path, Path]:
    p = case_root.resolve()
    candidates = [p] if p.is_dir() else []
    if p.name == "case.json":
        candidates = [p.parent]
        if p.parent.name == "input":
            candidates.append(p.parent.parent)
    elif p.name == "task.md":
        candidates = [p.parent, p.parent / "input"]
    elif p.is_dir():
        candidates.append(p / "input")
    for d in candidates:
        if (d / "case.json").is_file() and (d / "task.md").is_file():
            return load_json(d / "case.json"), d / "case.json", d / "task.md"
        if d.name == "input" and (d / "case.json").is_file() and (d.parent / "task.md").is_file():
            return load_json(d / "case.json"), d / "case.json", d.parent / "task.md"
    raise ContractError(f"Cannot resolve case.json + task.md from {case_root}")


def case_layout(case_root: Path, cj: Path, task: Path) -> dict[str, Path]:
    p = case_root.resolve()
    roots = [p] if p.is_dir() else []
    if p.name in {"case.json", "task.md"}:
        roots += [p.parent, p.parent / "input", p.parent.parent]
    else:
        roots.append(p / "input")
    roots += [cj.parent, cj.parent.parent]
    names = {"spec": "specification.json", "source_data": "data.csv", "source_paper": "source_paper.md", "workorder": "workorder.json", "scientific_review": "scientific_review.json"}
    result = {"case_json": cj, "task": task}
    for key, name in names.items():
        for root in roots:
            if (root / name).is_file():
                result[key] = root / name
                break
        if key not in result:
            raise ContractError(f"Missing required {name}")
    return result


def case_identity(cfg: dict) -> str:
    comp, explicit = cfg.get("composite_id"), cfg.get("case_id")
    if not comp:
        asset = cfg.get("asset", {})
        comp = f"{BUNDLE}__{asset.get('source_file', 'specification.json')}__{asset.get('panel', 'figure03')}__{asset.get('mode', 'quality-demo')}"
    if explicit != comp or comp.count("__") != 3 or comp.split("__")[0] != BUNDLE:
        raise ContractError("case_id must equal bundle__source_file__panel__mode composite_id")
    return comp


def output_contract(cfg: dict, case_id: str) -> dict[str, object]:
    out = cfg.get("output_contract")
    if not isinstance(out, dict):
        raise ContractError("output_contract must be an object")
    required = {
        "result": "result/result.json", "record_key": f"record_key/{case_id}.json", "edited": f"edited/{case_id}.json",
        "svg": f"generated/{case_id}/figure03.svg", "png": f"generated/{case_id}/figure03.png", "pdf": f"generated/{case_id}/figure03.pdf",
        "run_manifest": "review/run_manifest.json",
    }
    for key, value in required.items():
        if out.get(key) != value:
            raise ContractError(f"output_contract.{key} must equal {value}")
    for key in ("sources", "uncertainty", "change_records", "source_map", "audit", "visual_review", "scientific_readback", "recovery", "result_file_pointer", "asset_paths", "case_id"):
        if key not in out:
            raise ContractError(f"output_contract missing {key}")
    if out["case_id"] != case_id or out["result_file_pointer"] != out["result"]:
        raise ContractError("Dynamic case_id/result_file_pointer mismatch")
    expected = {k: v for k, v in out.items() if k not in META_FIELDS}
    if out["asset_paths"] != expected:
        raise ContractError("asset_paths must exactly mirror every non-meta output_contract field")
    return out


def inputs_record(layout: dict[str, Path]) -> list[dict]:
    return [{"role": role, "path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size} for role, path in sorted(layout.items())]


def make_partial(cfg: dict, case_id: str, status: str = "partial") -> dict:
    result = {"case_id": case_id, "status": status, "sources": [], "uncertainty": ["Incomplete run; no complete scientific or visual claim."], "change_records": []}
    for key, value in cfg["output_contract"].items():
        result[key] = value if key in META_FIELDS else None
    result["case_id"] = case_id
    return result


def write_result_fields(result: dict, contract: dict, out: Path) -> dict:
    for key, rel in contract.items():
        if key not in META_FIELDS:
            result[key] = str(out / str(rel))
    result["result_file_pointer"] = str(out / str(contract["result"]))
    result["asset_paths"] = dict(contract["asset_paths"])
    return result


def load_manifest(path: Path) -> dict | None:
    return load_json(path) if path.is_file() else None


def checkpoint(work: Path, out: Path, contract: dict, manifest: dict, stage: str, evidence: dict) -> None:
    if stage not in STAGES:
        raise ContractError("Invalid stage " + stage)
    manifest["current_stage"] = stage
    if stage not in manifest["completed_stages"]:
        manifest["completed_stages"].append(stage)
    manifest["checkpoints"][stage] = {"state": stage, "evidence_sha256": hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(), "evidence": evidence}
    atomic_json(work / "run_manifest.json", manifest)
    atomic_json(out / str(contract["run_manifest"]), manifest)


def audit_svg(svg: Path, spec: dict) -> dict:
    raw = svg.read_bytes()
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ContractError("Unsafe SVG declaration")
    root = ET.fromstring(raw)
    ids = [el.get("id") for el in root.iter() if isinstance(el.tag, str)]
    if any(not x for x in ids) or len(ids) != len(set(ids)):
        raise ContractError("SVG IDs missing or duplicate")
    entities = {el.get("data-entity-id"): "".join(el.itertext()) for el in root.iter() if el.get("data-kind") == "entity"}
    expected_entities = {e["id"]: e["label"] for e in spec["entities"]}
    if entities != expected_entities:
        raise ContractError(f"Entity readback mismatch: {entities} != {expected_entities}")
    edges = [{"id": el.get("data-edge-id"), "source": el.get("data-source"), "target": el.get("data-target"), "relation": el.get("data-relation"), "uncertain": el.get("data-uncertainty")} for el in root.iter() if el.get("data-kind") == "edge"]
    expected_edges = [{"id": e["id"], "source": e["source"], "target": e["target"], "relation": e["relation"], "uncertain": str(e.get("uncertain", False)).lower()} for e in spec["edges"]]
    if sorted(edges, key=lambda x: x["id"]) != sorted(expected_edges, key=lambda x: x["id"]):
        raise ContractError("Edge/source/target/relation readback mismatch")
    legends = [{"relation": el.get("data-relation"), "text": "".join(el.itertext()), "uncertain": el.get("data-uncertainty")} for el in root.iter() if el.get("data-kind") == "legend-entry"]
    expected_legends = [{"relation": x["relation"], "text": x["label"], "uncertain": str(x.get("uncertain", False)).lower()} for x in spec["legend"]]
    if sorted(legends, key=lambda x: x["relation"]) != sorted(expected_legends, key=lambda x: x["relation"]):
        raise ContractError("Legend readback mismatch")
    all_text = "\n".join(t.strip() for t in root.itertext() if t.strip())
    return {"entity_count": len(entities), "edge_count": len(edges), "legend_count": len(legends), "entities": entities, "edges": edges, "legend": legends, "text": all_text}


def audit_png(png: Path) -> dict:
    import pymupdf
    if not png.is_file() or png.stat().st_size == 0:
        raise ContractError(f"PNG export missing/empty: {png}")
    with pymupdf.open(png) as d:
        if d.page_count != 1:
            raise ContractError("PNG must have one image")
        pix = d[0].get_pixmap(alpha=False)
        samples = pix.samples
        nonwhite = sum(1 for i in range(0, len(samples), max(3, (len(samples) // 30000) // 3 * 3 or 3)) if samples[i] < 245)
        if pix.width < 100 or pix.height < 100 or len(samples) == 0 or nonwhite == 0:
            raise ContractError("PNG pixel audit found blank/tiny image")
        return {"width": pix.width, "height": pix.height, "sampled_nonwhite_pixels": nonwhite, "nonempty": True}


def audit_pdf(pdf: Path, spec: dict) -> dict:
    import pymupdf
    with pymupdf.open(pdf) as d:
        if d.page_count != 1:
            raise ContractError("PDF page count must be one")
        text = "\n".join(p.get_text() for p in d)
    required = [spec["title"]] + [x["label"] for x in spec["entities"]] + [x["legend"] for x in spec["edges"]] + [x["label"] for x in spec["legend"]]
    missing = [x for x in required if x not in text]
    if missing:
        raise ContractError("PDF text readback missing: " + ", ".join(missing))
    return {"page_count": 1, "text": text, "required_text_present": True}


def render(work: Path, svg: Path) -> None:
    if svg.exists():
        svg.unlink()
    proc = subprocess.run([sys.executable, str(Path(__file__).with_name("simple_renderer.py")), "--spec", str(work / "specification.json"), "--output", str(svg)], text=True, capture_output=True)
    if proc.returncode:
        raise ContractError("Renderer failed: " + proc.stderr.strip())


def export(svg: Path, png: Path, pdf: Path, inject: str | None) -> dict:
    import pymupdf
    with pymupdf.open(svg) as d:
        pix = d[0].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
        pdf_bytes = d.convert_to_pdf()
    if inject == "missing-png":
        if png.exists():
            png.unlink()
    else:
        atomic_bytes(png, pix.tobytes("png"))
    atomic_bytes(pdf, pdf_bytes)
    return {"renderer": "PyMuPDF", "png_written": inject != "missing-png", "pdf_sha256": sha256(pdf)}


def validate_native_review(review: dict, spec: dict) -> None:
    if review.get("verdict") != "pass":
        raise ScientificError("Agent scientific review did not pass; rendering cannot substitute for source judgment")
    expected_ids = {x["id"] for x in spec["entities"]}
    reviewed = set(review.get("reviewed_entity_ids", []))
    if reviewed != expected_ids:
        raise ScientificError("Agent review must explicitly cover every specified entity")
    if not review.get("feedback_reviewed") or not review.get("uncertain_edges_reviewed"):
        raise ScientificError("Feedback and uncertain edges require explicit Agent source review")
    if not review.get("observations") or not review.get("limitations"):
        raise ScientificError("Scientific review observations and limitations are required")


def audit_result_fields(result: dict, contract: dict, out: Path) -> dict:
    required_result = set(contract) | {"case_id", "status", "sources", "uncertainty", "change_records"}
    missing = sorted(k for k in required_result if k not in result or result[k] in (None, "", [], {}))
    if missing:
        raise ContractError("result missing/empty fields: " + ", ".join(missing))
    if result.get("case_id") != contract["case_id"] or result.get("result_file_pointer") != str(out / str(contract["result"])):
        raise ContractError("Dynamic case_id/result pointer mismatch")
    files = {}
    for key, rel in contract["asset_paths"].items():
        p = out / rel
        if key == "result":
            # Final result is atomically rewritten after this gate.
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                raise ContractError("Result file is absent")
        if not p.is_file() or p.stat().st_size == 0:
            raise ContractError(f"Required output absent/empty: {key} -> {p}")
        files[key] = {"path": str(p), "bytes": p.stat().st_size, "sha256": sha256(p)}
        if result.get(key) != str(p):
            raise ContractError(f"Dynamic value mismatch for {key}")
    for key in ("sources", "uncertainty", "change_records"):
        if key not in result or result[key] in (None, "", [], {}):
            raise ContractError(f"Missing {key} content")
    return files


def fresh_manifest(case_id: str, layout: dict[str, Path]) -> dict:
    return {"schema_version": 1, "case_id": case_id, "status": "partial", "state_machine": STAGES, "current_stage": None, "completed_stages": [], "checkpoints": {}, "input_hashes": {x["role"]: x["sha256"] for x in inputs_record(layout)}, "recoveries": []}


def run_pipeline(args: argparse.Namespace) -> int:
    cfg, cj, task = resolve_case(args.case_root)
    case_id = case_identity(cfg)
    contract = output_contract(cfg, case_id)
    layout = case_layout(args.case_root, cj, task)
    out, work = args.output.resolve(), args.work.resolve()
    out.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    result_path = out / str(contract["result"])
    manifest_path = work / "run_manifest.json"
    if not args.resume:
        atomic_json(result_path, make_partial(cfg, case_id))
        manifest = fresh_manifest(case_id, layout)
        atomic_json(manifest_path, manifest)
        atomic_json(out / str(contract["run_manifest"]), manifest)
        start_index = 0
    else:
        if not manifest_path.is_file():
            raise ContractError("--resume requires an existing checkpoint manifest")
        manifest = load_manifest(manifest_path)
        if manifest.get("case_id") != case_id:
            raise ContractError("Checkpoint belongs to another case")
        atomic_json(result_path, make_partial(cfg, case_id))
        start_index = 0
        # Continue after the last checkpoint; backtrack if exported files were lost.
        for i, stage in enumerate(STAGES):
            if stage in manifest.get("completed_stages", []):
                start_index = i + 1
        if "exported" in manifest.get("completed_stages", []) and (not (out / str(contract["png"])).is_file() or not (out / str(contract["pdf"])).is_file()):
            start_index = STAGES.index("exported")
            manifest["completed_stages"] = [x for x in manifest["completed_stages"] if STAGES.index(x) < start_index]
            manifest["recoveries"].append({"reason": "missing exported artifact", "resume_from": "exported"})
        if start_index >= STAGES.index("delivered"):
            start_index = STAGES.index("audited")
            manifest["completed_stages"] = [x for x in manifest["completed_stages"] if STAGES.index(x) < start_index]
        if manifest.get("status") == "failed":
            manifest["recoveries"].append({"reason": manifest.get("failure", {}).get("message", "previous failed run"), "resume_from": STAGES[start_index] if start_index < len(STAGES) else "audited"})
        manifest["status"] = "partial"
        manifest.pop("failure", None)
        atomic_json(manifest_path, manifest)
    sources = inputs_record(layout)
    spec = load_json(layout["spec"])
    review = load_json(layout["scientific_review"])
    uncertainty = list(spec.get("uncertainty", [])) + list(review.get("limitations", [])) + ["Native visual review is required before delivered/complete."]
    try:
        if start_index <= 0:
            validate_native_review(review, spec)
            checkpoint(work, out, contract, manifest, "observed", {"inputs": sources, "native_scientific_review": review})
        if start_index <= 1:
            atomic_json(work / "specification.json", spec)
            checkpoint(work, out, contract, manifest, "specified", {"specification_sha256": sha256(work / "specification.json"), "source": str(layout["spec"])})
        svg, png, pdf = (out / str(contract[k]) for k in ("svg", "png", "pdf"))
        if start_index <= 2:
            render(work, svg)
            checkpoint(work, out, contract, manifest, "rendered", {"svg_sha256": sha256(svg), "renderer": "simple_renderer.py"})
        if start_index <= 3:
            export_evidence = export(svg, png, pdf, args.inject_failure)
            checkpoint(work, out, contract, manifest, "exported", export_evidence)
        if start_index <= 4:
            # Rebuild every supporting artifact so omitted result fields are repairable.
            svg_audit = audit_svg(svg, spec)
            png_audit = audit_png(png)
            pdf_audit = audit_pdf(pdf, spec)
            input_now = {x["role"]: x["sha256"] for x in inputs_record(layout)}
            if input_now != manifest["input_hashes"]:
                raise ContractError("Input hash changed since observed checkpoint")
            visual = {"status": "pending", "reviewer": None, "observations": [], "limitations": ["No delivered status until an Agent inspects actual PNG and PDF."]}
            mapping = {"case_id": case_id, "mappings": [{"entity_id": x["id"], "source": x["source"], "label": x["label"], "native_judgement": "Agent supplied; runner audited readback only"} for x in spec["entities"]], "edges": [{"source": x["source_record"], "source_id": x["source"], "target_id": x["target"], "relation": x["relation"], "uncertain": x.get("uncertain", False)} for x in spec["edges"]]}
            changes = [{"stage": "observed", "action": "Read case-local materials; hashes frozen"}, {"stage": "specified", "action": "Used Agent-authored specification; no inferred nodes/edges"}, {"stage": "rendered", "action": "Deterministic SVG generated", "sha256": sha256(svg)}, {"stage": "exported", "action": "PyMuPDF PNG/PDF generated", "png_sha256": sha256(png), "pdf_sha256": sha256(pdf)}]
            paths = {k: out / str(v) for k, v in contract.items() if k not in META_FIELDS}
            atomic_json(paths["sources"], {"case_id": case_id, "inputs": sources})
            atomic_json(paths["uncertainty"], uncertainty)
            atomic_json(paths["change_records"], changes)
            atomic_json(paths["source_map"], mapping)
            atomic_json(paths["visual_review"], visual)
            atomic_json(paths["scientific_readback"], {"role_boundary": "Native Agent judges source meaning. Script audits structure and files only.", "review": review, "specification_entity_count": len(spec["entities"]), "specification_edge_count": len(spec["edges"])})
            atomic_json(paths["recovery"], manifest.get("recoveries", []))
            partial_pointer = {"case_id": case_id, "status": "partial", "svg": str(svg), "png": str(png), "pdf": str(pdf), "result": str(result_path), "record_key": str(paths["record_key"])}
            atomic_json(paths["edited"], partial_pointer)
            atomic_json(paths["record_key"], {"schema_version": 1, "record_key": case_id, "composite_id": case_id, "source_file": cfg.get("source_file"), "source_file_sha256": sha256(layout["spec"]), "inputs": sources, "status": "partial", "edited": str(paths["edited"]), "result": str(result_path)})
            atomic_json(paths["audit"], {"passed": False, "status": "auditing", "note": "provisional until full audit is atomically committed"})
            result = write_result_fields(make_partial(cfg, case_id), contract, out)
            result.update({"sources_detail": sources, "uncertainty_detail": uncertainty, "change_record_details": changes, "content_mapping": mapping, "visual_review_detail": visual, "recovery_detail": manifest.get("recoveries", [])})
            if args.inject_failure == "missing-result-field":
                del result["sources"]
            # Write candidate result first, then enforce every declared field/path/value/hash.
            atomic_json(result_path, result)
            file_audit = audit_result_fields(result, contract, out)
            audit = {"passed": True, "svg": svg_audit, "png": png_audit, "pdf": pdf_audit, "files": file_audit, "native_visual_review": "pending", "scientific_decision_made_by_script": False}
            atomic_json(paths["audit"], audit)
            checkpoint(work, out, contract, manifest, "audited", {"audit_sha256": sha256(paths["audit"]), "machine_gates_passed": True, "visual_review": "pending"})
            result["run_manifest"] = str(out / str(contract["run_manifest"]))
            atomic_json(result_path, result)
            # refresh manifest in result paths without volatile timestamps
            atomic_json(out / str(contract["run_manifest"]), manifest)
        print(json.dumps({"case_id": case_id, "status": "partial", "stage": "audited", "result": str(result_path), "next": "Inspect actual PNG/PDF, write a visual-review JSON, then run attest."}, ensure_ascii=False))
        return 0
    except (ContractError, ScientificError) as e:
        is_science = isinstance(e, ScientificError)
        manifest["status"] = "failed"
        manifest["failure"] = {"kind": "scientific" if is_science else "contract", "message": str(e), "failed_stage": STAGES[start_index] if start_index < len(STAGES) else "audited"}
        atomic_json(manifest_path, manifest)
        atomic_json(out / str(contract["run_manifest"]), manifest)
        failure_result = write_result_fields(make_partial(cfg, case_id, "failed"), contract, out)
        failure_result["error"] = manifest["failure"]
        failure_result["recovery_command"] = f"python3 scripts/runner.py run --case-root {args.case_root} --work {work} --output {out} --resume"
        atomic_json(result_path, failure_result)
        if "audit" in contract:
            atomic_json(out / str(contract["audit"]), {"passed": False, "failure": manifest["failure"], "degraded_status": "failed", "repair": "Restore missing artifact/field, then use --resume; never claim complete."})
        print(f"{manifest['failure']['kind'].upper()} FAILURE: {e}", file=sys.stderr)
        return 4 if is_science else 3


def attest(args: argparse.Namespace) -> int:
    cfg, cj, task = resolve_case(args.case_root)
    case_id = case_identity(cfg)
    contract = output_contract(cfg, case_id)
    layout = case_layout(args.case_root, cj, task)
    out, work = args.output.resolve(), args.work.resolve()
    manifest = load_manifest(work / "run_manifest.json")
    if not manifest or manifest.get("current_stage") != "audited" or manifest.get("status") != "partial":
        raise ContractError("attest requires an audited, partial run with passing machine gates")
    review = load_json(args.visual_review)
    if review.get("status") != "passed" or not review.get("reviewer") or not review.get("observations") or not review.get("limitations"):
        raise ScientificError("Visual attestation needs status=passed, reviewer, observations, and limitations")
    result_path = out / str(contract["result"])
    result = load_json(result_path)
    machine = load_json(out / str(contract["audit"]))
    if not machine.get("passed"):
        raise ContractError("Machine audit did not pass")
    if {x["role"]: x["sha256"] for x in inputs_record(layout)} != manifest.get("input_hashes"):
        raise ContractError("Input hashes changed since audited checkpoint; rerun machine gates")
    spec = load_json(layout["spec"])
    svg, png, pdf = (out / str(contract[k]) for k in ("svg", "png", "pdf"))
    audit_svg(svg, spec)
    audit_png(png)
    audit_pdf(pdf, spec)
    # Verify exact reviewed artifact identity at delivery.
    for key, path in (("png_sha256", png), ("pdf_sha256", pdf)):
        if review.get(key) != sha256(path):
            raise ContractError(f"Visual review {key} does not match delivered artifact")
    result = write_result_fields(result, contract, out)
    result["visual_review_detail"] = review
    atomic_json(out / str(contract["visual_review"]), review)
    result["status"] = "complete"
    checkpoint(work, out, contract, manifest, "delivered", {"visual_review": "passed", "png_sha256": sha256(png), "pdf_sha256": sha256(pdf)})
    manifest["status"] = "complete"
    atomic_json(work / "run_manifest.json", manifest)
    atomic_json(out / str(contract["run_manifest"]), manifest)
    result["run_manifest"] = str(out / str(contract["run_manifest"]))
    atomic_json(result_path, result)
    edited = {"case_id": case_id, "status": "complete", "svg": str(out / str(contract["svg"])), "png": str(png), "pdf": str(pdf), "result": str(result_path), "record_key": str(out / str(contract["record_key"]))}
    atomic_json(out / str(contract["edited"]), edited)
    rec = {"schema_version": 1, "record_key": case_id, "composite_id": case_id, "directory": "book-figure-3->" + BUNDLE + "/" + case_id + "/", "source_file": cfg.get("source_file"), "source_file_sha256": sha256(layout["spec"]), "inputs": inputs_record(layout), "edited": str(out / str(contract["edited"])), "result": str(result_path)}
    atomic_json(out / str(contract["record_key"]), rec)
    audit_result_fields(result, contract, out)
    print(json.dumps({"case_id": case_id, "status": "complete", "stage": "delivered", "result": str(result_path)}, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("run", "attest"):
        p = sub.add_parser(name)
        p.add_argument("--case-root", type=Path, default=DEFAULT_CASE)
        p.add_argument("--work", type=Path, default=DEFAULT_WORK)
        p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    sub.choices["run"].add_argument("--resume", action="store_true")
    sub.choices["run"].add_argument("--inject-failure", choices=["missing-png", "missing-result-field"])
    sub.choices["attest"].add_argument("--visual-review", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        return run_pipeline(args) if args.command == "run" else attest(args)
    except ContractError as e:
        print(f"CONTRACT FAILURE: {e}", file=sys.stderr)
        return 3
    except ScientificError as e:
        print(f"SCIENTIFIC FAILURE: {e}", file=sys.stderr)
        return 4
    except Exception as e:
        print(f"INTERNAL ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
