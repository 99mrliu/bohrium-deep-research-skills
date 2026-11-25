#!/usr/bin/env python3
"""Transactional, ID-addressed SVG DOM surgery and trusted PyMuPDF export.

Deterministic; never mutates a source path. No biological claims are inferred.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET

BUNDLE = "source-surgery"
DEFAULT_CASE = Path("/app/case/source-surgery")
DEFAULT_WORK = Path("/app/work/source-surgery")
DEFAULT_OUTPUT = Path("/app/output/source-surgery")
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ALLOWED_EDGE_KINDS = {
    "solid": (None, None, None),
    "direct": (None, "url(#arrow-direct)", "#2563eb"),
    "dashed": ("8 5", None, None),
    "dotted": ("2 5", None, None),
    "feedback": ("10 5", "url(#arrow-feedback)", "#7c3aed"),
    "uncertain": ("4 5", "url(#arrow-uncertain)", "#b45309"),
}
UNSAFE_STYLE = re.compile(r"url\s*\(|expression\s*\(|@import|javascript\s*:|behavior\s*:|-moz-binding", re.I)


class SurgeryError(Exception):
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
        tmp = Path(f.name)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def atomic_json(path: Path, value: object) -> None:
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise SurgeryError(f"Expected JSON object: {path}")
    return value


def resolve_case(case_root: Path) -> tuple[dict, Path, Path]:
    """Accept a case directory, input directory, case.json, or task.md."""
    p = case_root.resolve()
    candidates = [p] if p.is_dir() else []
    if p.name == "case.json":
        candidates = [p.parent]
        if p.parent.name == "input":
            candidates.append(p.parent.parent)
    elif p.name == "task.md":
        candidates = [p.parent, p.parent / "input"]
    elif p.is_dir():
        candidates += [p / "input"]
    for d in candidates:
        cj, tm = d / "case.json", d / "task.md"
        if cj.is_file() and tm.is_file():
            return load_json(cj), cj, tm
    # A case directory may have task.md at root and case.json/task.md in input.
    if p.is_dir():
        d = p / "input"
        if (d / "case.json").is_file() and (p / "task.md").is_file():
            cfg = load_json(d / "case.json")
            cfg["_task_path"] = str(p / "task.md")
            return cfg, d / "case.json", p / "task.md"
    raise SurgeryError(f"Cannot resolve case.json + task.md from {case_root}")


def case_paths(case_root: Path, case_json: Path) -> dict[str, Path]:
    """Resolve canonical paths and one-case-only input fallback, never a peer case."""
    root = case_root.resolve()
    base = case_json.parent
    candidates = [root] if root.is_dir() else []
    if root.name == "case.json":
        candidates = [root.parent]
        if root.parent.name == "input":
            candidates.append(root.parent.parent)
    elif root.name == "task.md":
        candidates = [root.parent, root.parent / "input"]
    else:
        candidates.append(root / "input")
    roots = []
    for d in candidates + [base, base.parent]:
        if d not in roots:
            roots.append(d)
    mapped = {
        "case_json": case_json,
        "task": case_paths_task(case_json, roots),
        "workorder": None, "source_svg": None, "original_png": None,
        "source_data": None, "source_paper": None,
    }
    names = {
        "source_svg": "source.svg", "original_png": "figure03.png",
        "source_data": "data.csv", "source_paper": "source_paper.md",
    }
    for key, name in names.items():
        for d in roots:
            p = d / name
            if p.is_file():
                mapped[key] = p
                break
    for d in roots:
        for p in (d / "source_surgery" / "workorder.json", d / "workorder.json"):
            if p.is_file():
                mapped["workorder"] = p
                break
        if mapped["workorder"]:
            break
    missing = [k for k, v in mapped.items() if v is None]
    if missing:
        raise SurgeryError("Missing required case inputs: " + ", ".join(missing))
    return mapped


def case_paths_task(case_json: Path, roots: list[Path]) -> Path:
    task_hint = None
    try:
        task_hint = load_json(case_json).get("_task_path")
    except Exception:
        pass
    if task_hint and Path(task_hint).is_file():
        return Path(task_hint)
    for d in roots:
        p = d / "task.md"
        if p.is_file():
            return p
    raise SurgeryError("Missing task.md")


def derive_case_id(cfg: dict) -> tuple[str, str, str, str, str]:
    explicit = cfg.get("case_id")
    comp = cfg.get("composite_id")
    if comp and explicit and explicit != comp:
        raise SurgeryError("case_id must exactly equal composite_id")
    if not comp:
        asset = cfg.get("asset", {})
        source_file = asset.get("source_file", "source")
        source_stem = Path(source_file).stem if Path(source_file).suffix == ".svg" else source_file
        panel = str(asset.get("panel", "book-figure-3"))
        mode = str(asset.get("mode", "source-preserving"))
        comp = f"{BUNDLE}__{source_stem}__{panel}__{mode}"
    if comp.count("__") != 3 or comp.split("__")[0] != BUNDLE:
        raise SurgeryError("composite_id must be bundle__source_file__panel__mode")
    if explicit != comp:
        raise SurgeryError("case_id must exactly equal composite_id")
    return comp, *comp.split("__")[1:]


def recorder(layout: dict[str, Path], prefix: str, case_id: str) -> dict:
    value = {}
    for key in ("task", "case_json", "workorder", "source_svg", "original_png", "source_data", "source_paper"):
        p = layout[key]
        value[key] = {"path": str(p), "sha256": sha256(p), "bytes": p.stat().st_size}
    return {
        "schema_version": 1, "record_key": case_id, "bundle": BUNDLE,
        "root": str(layout["case_json"].parent.parent if layout["case_json"].parent.name == "input" else layout["case_json"].parent),
        "directory": prefix + case_id + "/", "files": value,
    }


def write_manifest(layout: dict[str, Path], root: Path, case_id: str) -> dict:
    bundle = root.parent
    nested, records = [], []
    for d in sorted(bundle.iterdir()):
        if not d.is_dir() or d.name == root.name:
            continue
        if (d / "task.md").is_file() and not ((d / "files").is_dir() ^ (d / "assets").is_dir()):
            nested.append(d.name + "/")
        elif (d / "input" / "case.json").is_file():
            cj = d / "input" / "case.json"
            try:
                lyt = case_paths(d, cj)
                records.append(recorder(lyt, "cases/", str(load_json(cj).get("case_id"))))
            except Exception as e:
                raise SurgeryError(f"Invalid peer input case {d}: {e}") from e
    source = layout["source_svg"]
    data = {
        "schema_version": 1, "root": str(root), "directory": root.name + "/",
        "files": {"case.json": {"path": str(layout["case_json"]), "sha256": sha256(layout["case_json"])}},
        "task": {"path": str(layout["task"]), "sha256": sha256(layout["task"])},
        "case_id": case_id, "source_or_directory_cache": [], "nested_directories": nested,
        "layout_contract": {"record_key": f"record_key/{case_id}.json", "edited": f"edited/{case_id}.json", "result": f"result/{case_id}.json"},
    }
    if root.name == "input":
        data["layout_contract"].update({"record_key": "record_key.json", "edited": "edited.json", "result": "result.json"})
    for p in sorted(source.iterdir()):
        if p.name == "cache":
            continue
        if p.is_file():
            data["source_or_directory_cache"].append({"path": str(p), "sha256": sha256(p)})
    value = {"version": 1, "files": records, "settled": [data]}
    atomic_json(root / "case_manifest.json", value)
    return data


def expected_record_contract(cfg: dict, case_id: str) -> dict:
    out = dict(cfg["output_contract"])
    required = {
        "result": f"result/{case_id}.json",
        "record_key": f"record_key/{case_id}.json",
        "edited": f"edited/{case_id}.json",
        "edited_svg": f"edited/{case_id}/source.svg",
        "edited_png": f"edited/{case_id}/figure03.png",
        "edited_pdf": f"edited/{case_id}/figure03.pdf",
    }
    for k, v in required.items():
        if k not in out:
            raise SurgeryError(f"output_contract missing required field {k}")
        if out[k] != v:
            raise SurgeryError(f"output_contract.{k} must be {v}; got {out[k]}")
    for field in ("result_file_pointer", "asset_paths", "case_id"):
        if field not in out:
            raise SurgeryError(f"output_contract missing required dynamic field {field}")
    if out["case_id"] != case_id:
        raise SurgeryError("output_contract.case_id must equal dynamic case_id")
    expected = {k: v for k, v in out.items() if k not in {"result_file_pointer", "asset_paths", "case_id"}}
    if out["asset_paths"] != expected:
        raise SurgeryError("output_contract.asset_paths must exactly map all declared relative asset fields")
    if out["result_file_pointer"] != out["result"]:
        raise SurgeryError("result_file_pointer must equal output_contract.result")
    return out


def safe_xml(source: Path) -> tuple[ET.ElementTree, list[str], bytes]:
    raw = source.read_bytes()
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise SurgeryError("DOCTYPE/ENTITY declarations are forbidden")
    try:
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
        root = ET.fromstring(raw, parser=parser)
    except ET.ParseError as e:
        raise SurgeryError(f"Invalid XML: {e}") from e
    ids = []
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        ident = el.get("id")
        if not ident:
            raise SurgeryError("Every SVG element requires a stable non-empty id")
        ids.append(ident)
    if len(ids) != len(set(ids)):
        duplicates = sorted({x for x in ids if ids.count(x) > 1})
        raise SurgeryError("Duplicate SVG element id(s): " + ", ".join(duplicates))
    for event, item in ET.iterparse(source, events=("start-ns",)):
        prefix, uri = item
        ET.register_namespace(prefix, uri)
    return ET.ElementTree(root), ids, raw


def index(tree: ET.ElementTree) -> dict[str, ET.Element]:
    return {el.get("id"): el for el in tree.getroot().iter() if isinstance(el.tag, str)}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def check_attribute(name: str, value: str) -> None:
    lname = local_name(name).lower()
    if name == "id" or lname == "id" or name.lower().startswith("xmlns"):
        raise SurgeryError("Operations may not change IDs or namespace declarations")
    if lname.startswith("on"):
        raise SurgeryError("Event-handler attributes are forbidden")
    if lname in {"href", "src"}:
        if not value.startswith("#"):
            raise SurgeryError("Only local fragment href references are allowed")
    if any(x in value.lower() for x in ("javascript:", "<script", "data:text/html")):
        raise SurgeryError("Unsafe attribute value")


def parse_style(el: ET.Element) -> dict[str, str]:
    result = {}
    for token in el.get("style", "").split(";"):
        if ":" in token:
            k, v = token.split(":", 1)
            result[k.strip()] = v.strip()
    return result


def apply_operation(tree: ET.ElementTree, op: dict, number: int) -> dict:
    if not isinstance(op, dict) or not isinstance(op.get("id"), str):
        raise SurgeryError(f"Operation {number}: missing string id")
    kind = op.get("op")
    ident = op["id"]
    matches = [el for el in tree.getroot().iter() if isinstance(el.tag, str) and el.get("id") == ident]
    if len(matches) != 1:
        raise SurgeryError(f"Operation {number}: id {ident!r} matched {len(matches)} elements")
    el = matches[0]
    before = ET.tostring(el, encoding="unicode")
    changed = {"operation_index": number, "op": kind, "id": ident, "before": before}
    if kind == "set_text":
        if len(el):
            raise SurgeryError("set_text refuses mixed-content/container elements")
        text = op.get("text")
        if not isinstance(text, str):
            raise SurgeryError("set_text.text must be a string")
        el.text = text
        changed.update({"field": "text", "old": before, "new": text})
    elif kind == "set_attribute":
        name, value = op.get("attribute"), op.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            raise SurgeryError("set_attribute requires string attribute/value")
        check_attribute(name, value)
        old = el.get(name)
        el.set(name, value)
        changed.update({"field": name, "old": old, "new": value})
    elif kind == "set_style":
        props = op.get("properties")
        if not isinstance(props, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in props.items()):
            raise SurgeryError("set_style.properties must be a string map")
        styles = parse_style(el)
        old = {k: styles.get(k) for k in props}
        for k, v in props.items():
            if UNSAFE_STYLE.search(k) or UNSAFE_STYLE.search(v):
                raise SurgeryError("Unsafe CSS property/value")
            styles[k] = v
        for k in op.get("remove", []):
            styles.pop(k, None)
        new_style = "; ".join(f"{k}: {v}" for k, v in styles.items())
        el.set("style", new_style)
        changed.update({"field": "style", "old": old, "new": props})
    elif kind == "move_by":
        dx, dy = op.get("dx"), op.get("dy")
        if isinstance(dx, bool) or isinstance(dy, bool) or not isinstance(dx, (int, float)) or not isinstance(dy, (int, float)):
            raise SurgeryError("move_by.dx/dy must be finite numbers")
        import math
        if not math.isfinite(dx) or not math.isfinite(dy):
            raise SurgeryError("move_by.dx/dy must be finite")
        old = el.get("transform", "").strip()
        translation = f"translate({dx:g} {dy:g})"
        el.set("transform", translation + (" " + old if old else ""))
        changed.update({"field": "transform", "old": old, "new": el.get("transform")})
    elif kind == "replace_edge_kind":
        kind_value = op.get("kind")
        if kind_value not in ALLOWED_EDGE_KINDS:
            raise SurgeryError("Unsupported edge kind: " + str(kind_value))
        if local_name(el.tag) not in {"path", "line", "polyline"}:
            raise SurgeryError("replace_edge_kind requires a path/line/polyline")
        dash, marker, stroke = ALLOWED_EDGE_KINDS[kind_value]
        old = {"data-edge-kind": el.get("data-edge-kind"), "stroke-dasharray": el.get("stroke-dasharray"), "marker-end": el.get("marker-end"), "stroke": el.get("stroke")}
        el.set("data-edge-kind", kind_value)
        for key, val in (("stroke-dasharray", dash), ("marker-end", marker)):
            if val is None:
                el.attrib.pop(key, None)
            else:
                el.set(key, val)
        if stroke is not None:
            el.set("stroke", stroke)
        changed.update({"field": "edge_kind", "old": old, "new": kind_value})
    else:
        raise SurgeryError(f"Unsupported operation {kind!r}")
    after = ET.tostring(el, encoding="unicode")
    changed["after"] = after
    if before == after:
        raise SurgeryError(f"Operation {number} is a no-op; surgery must be minimal and intentional")
    return changed


def shallow_hash(el: ET.Element) -> str:
    payload = {"tag": el.tag, "attributes": sorted(el.attrib.items()), "text": el.text, "tail": el.tail}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def has_id(root: ET.Element, ident: str) -> bool:
    return any(isinstance(el.tag, str) and el.get("id") == ident for el in root.iter())


def compare_trees(before: ET.ElementTree, after: ET.ElementTree, target_ids: set[str]) -> tuple[dict, list[dict]]:
    a, b = index(before), index(after)
    if set(a) != set(b):
        raise SurgeryError("Element IDs were added/deleted")
    detail, unchanged = [], []
    for ident in a:
        deep_a, deep_b = ET.tostring(a[ident]), ET.tostring(b[ident])
        shallow_same = shallow_hash(a[ident]) == shallow_hash(b[ident])
        deep_same = deep_a == deep_b
        ancestor = any(ident != t and has_id(a[ident], t) for t in target_ids)
        if ident not in target_ids and not shallow_same:
            raise SurgeryError(f"Unintended edit to unchanged element {ident}")
        if ident not in target_ids and not ancestor and not deep_same:
            raise SurgeryError(f"Unintended descendant edit under {ident}")
        item = {"id": ident, "target": ident in target_ids, "ancestor_of_target": ancestor, "before_sha256": hashlib.sha256(deep_a).hexdigest(), "after_sha256": hashlib.sha256(deep_b).hexdigest(), "unchanged": deep_same, "own_content_unchanged": shallow_same}
        detail.append(item)
        if deep_same:
            unchanged.append(item)
    return {"policy": "Every non-target element has identical tag/attributes/direct text/tail. Non-target, non-ancestor subtrees are byte-identical after XML serialization; ancestors may differ only through declared descendants. IDs are invariant.", "unchanged_element_count": len(unchanged), "total_element_count": len(detail), "elements": detail}, detail


def export_svg(svg: Path, png: Path, pdf: Path) -> dict:
    try:
        import pymupdf
    except ImportError as e:
        raise SurgeryError("PyMuPDF is required: install pymupdf") from e
    raw = svg.read_bytes()
    try:
        doc = pymupdf.open(stream=raw, filetype="svg")
        if doc.page_count != 1:
            raise SurgeryError("SVG export must produce one page")
        page = doc[0]
        pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
        atomic_bytes(png, pix.tobytes("png"))
        atomic_bytes(pdf, doc.convert_to_pdf())
    except SurgeryError:
        raise
    except Exception as e:
        raise SurgeryError(f"PyMuPDF export failed: {e}") from e
    with pymupdf.open(pdf) as exported:
        text = "\n".join(p.get_text() for p in exported)
        pages = exported.page_count
    if pages != 1 or not text.strip():
        raise SurgeryError("PDF page/text readback failed")
    if not png.is_file() or png.stat().st_size < 100:
        raise SurgeryError("PNG export missing or empty")
    return {"renderer": "PyMuPDF", "png_pixels": [pix.width, pix.height], "pdf_pages": pages, "pdf_text": text, "png_sha256": sha256(png), "pdf_sha256": sha256(pdf)}


def content_mapping(workorder: dict, changes: list[dict], source: Path) -> dict:
    mappings = []
    for c in changes:
        mappings.append({"element_id": c["id"], "operation": c["op"], "source": "source_surgery/workorder.json", "source_location": "source.svg#" + c["id"], "target_location": "edited source.svg#" + c["id"], "change": {"before": c.get("old", c.get("before")), "after": c.get("new", c.get("after"))}})
    return {"mapping": mappings, "basis": "Deterministic SVG DOM edits; scientific labels and relations are supplied by the work order/source, never invented by this script."}


def partial_result(cfg: dict, case_id: str, status: str, error: str | None = None) -> dict:
    result = {"case_id": case_id, "status": status, "sources": "(pending)", "uncertainty": ["Run incomplete; values and artifacts are provisional."], "change_records": []}
    for key, value in cfg.get("output_contract", {}).items():
        result[key] = value if key in {"asset_paths", "case_id", "result_file_pointer"} else None
    result["case_id"] = case_id
    if error:
        result["error"] = error
    return result


def run_surgery(args: argparse.Namespace) -> int:
    cfg, cj, tm = resolve_case(args.case_root)
    case_id, *_ = derive_case_id(cfg)
    layout = case_paths(args.case_root, cj)
    out, work = args.output.resolve(), args.work.resolve()
    contract = expected_record_contract(cfg, case_id)
    source = layout["source_svg"].resolve()
    out_result = out / contract["result"]
    if out == source or out in source.parents or source == work or work in source.parents:
        raise SurgeryError("Input source may not be overwritten or placed under work/output")
    out.mkdir(parents=True, exist_ok=True)
    atomic_json(out_result, partial_result(cfg, case_id, "partial"))
    original_hash = sha256(source)
    manifest = {"case_id": case_id, "status": "partial", "original_svg_sha256": original_hash, "operation_count": 0, "checkpoints": []}
    atomic_json(work / "run_manifest.json", manifest)
    workorder = load_json(layout["workorder"])
    backup = work / "backup" / "original.svg"
    if not backup.exists():
        atomic_bytes(backup, source.read_bytes())
    if sha256(backup) != original_hash:
        raise SurgeryError("Backup hash differs from original")
    final_paths = {k: out / v for k, v in contract.items() if k not in {"asset_paths", "case_id", "result_file_pointer"}}
    for key in ("edited_svg", "edited_png", "edited_pdf"):
        p = final_paths[key].resolve()
        if p == source or source in p.parents:
            raise SurgeryError("Refusing to overwrite input source")
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            p.unlink()
    staging = work / "transaction"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    changes = []
    try:
        before, _, _ = safe_xml(source)
        after = copy.deepcopy(before)
        operations = workorder.get("operations")
        if not isinstance(operations, list) or not operations:
            raise SurgeryError("Workorder requires a non-empty operations list")
        for n, op in enumerate(operations, 1):
            changes.append(apply_operation(after, op, n))
            manifest["operation_count"] = n
            manifest["checkpoints"].append({"operation": n, "id": op.get("id"), "status": "applied_in_memory"})
            atomic_json(work / "run_manifest.json", manifest)
        targets = {op["id"] for op in operations}
        unchanged, detail = compare_trees(before, after, targets)
        before_xml = ET.tostring(before.getroot(), encoding="utf-8", xml_declaration=True)
        after_xml = ET.tostring(after.getroot(), encoding="utf-8", xml_declaration=True)
        atomic_bytes(staging / "before.xml", before_xml)
        atomic_bytes(staging / "after.xml", after_xml)
        staged_svg = staging / "edited.svg"
        atomic_bytes(staged_svg, after_xml)
        # Final edited artifacts are committed only after every operation and audit succeeds.
        export = export_svg(staged_svg, staging / "edited.png", staging / "edited.pdf")
        if sha256(source) != original_hash:
            raise SurgeryError("Input source changed during run")
        for src, dst in ((staged_svg, final_paths["edited_svg"]), (staging / "edited.png", final_paths["edited_png"]), (staging / "edited.pdf", final_paths["edited_pdf"])):
            atomic_bytes(dst, src.read_bytes())
        for key, stage in (("before_xml", staging / "before.xml"), ("after_xml", staging / "after.xml")):
            if key in final_paths:
                atomic_bytes(final_paths[key], stage.read_bytes())
        if "unchanged_elements" in final_paths:
            atomic_json(final_paths["unchanged_elements"], unchanged)
        if "change_records" in final_paths:
            atomic_json(final_paths["change_records"], changes)
        if "source_map" in final_paths:
            atomic_json(final_paths["source_map"], content_mapping(workorder, changes, source))
        sources = {"case_id": case_id, "inputs": [{"role": k, "path": str(v), "sha256": sha256(v)} for k, v in sorted(layout.items())], "original_svg_sha256_before_and_after": [original_hash, sha256(source)]}
        if "sources" in final_paths:
            atomic_json(final_paths["sources"], sources)
        uncertainty = workorder.get("uncertainty", []) + ["Visual appearance still requires Agent/human image inspection before status complete."]
        if "uncertainty" in final_paths:
            atomic_json(final_paths["uncertainty"], uncertainty)
        visual = {"status": "pending", "reviewer": None, "observations": [], "limitations": ["Automated pixel/PDF checks do not replace scientific or visual inspection."]}
        if "visual_review" in final_paths:
            atomic_json(final_paths["visual_review"], visual)
        validation = {"all_operations_succeeded": True, "transaction_committed": True, "original_unchanged": True, "backup_sha256": sha256(backup), "unchanged_audit": unchanged, "export": export, "visual_review": "pending", "scientific_judgement": "Agent must verify edited content against the supplied source; not inferred by this script."}
        if "validation" in final_paths:
            atomic_json(final_paths["validation"], validation)
        result = partial_result(cfg, case_id, "partial")
        for k, p in final_paths.items():
            result[k] = str(p)
        result.update({"asset_paths": dict(contract["asset_paths"]), "result_file_pointer": str(out_result), "sources_detail": sources, "uncertainty_detail": uncertainty, "change_record_details": changes, "visual_review_detail": visual, "original_svg_sha256": original_hash, "edited_svg_sha256": sha256(final_paths["edited_svg"])})
        atomic_json(out_result, result)
        if "record_key" in final_paths:
            atomic_json(final_paths["record_key"], recorder(layout, "book-figure-3->" + BUNDLE + "/", case_id) | {"edited": str(final_paths["edited"]), "result": str(out_result)})
        if "edited" in final_paths:
            atomic_json(final_paths["edited"], {"case_id": case_id, "svg": str(final_paths["edited_svg"]), "png": str(final_paths["edited_png"]), "pdf": str(final_paths["edited_pdf"]), "status": "partial", "visual_review": "pending"})
        meta = manifest if work.name != "input" else write_manifest(layout, work, case_id)
        # Never write case_manifest into canonical input during a normal run.
        meta["edited_artifact"] = {"svg": str(final_paths["edited_svg"]), "sha256": sha256(final_paths["edited_svg"])}
        manifest["status"] = "partial"
        manifest["final_result"] = str(out_result)
        atomic_json(work / "run_manifest.json", manifest)
        if "run_manifest" in final_paths:
            atomic_json(final_paths["run_manifest"], manifest)
        print(json.dumps({"case_id": case_id, "status": "partial", "result": str(out_result), "next": "Inspect edited PNG/PDF, then run attest command.", "manifest": meta}, ensure_ascii=False))
        return 0
    except Exception as e:
        for key in ("edited_svg", "edited_png", "edited_pdf"):
            p = final_paths[key]
            if p.exists():
                p.unlink()
        manifest["status"] = "failed"
        manifest["error"] = str(e)
        atomic_json(work / "run_manifest.json", manifest)
        if "run_manifest" in final_paths:
            atomic_json(final_paths["run_manifest"], manifest)
        failed = partial_result(cfg, case_id, "failed", str(e))
        failed["transaction_committed"] = False
        failed["original_svg_sha256"] = original_hash
        atomic_json(out_result, failed)
        for key in ("edited", "record_key"):
            p = final_paths.get(key)
            if p and p.is_file():
                pointer = load_json(p)
                pointer.update({"status": "failed", "error": str(e), "result": str(out_result)})
                atomic_json(p, pointer)
        raise


def attest(args: argparse.Namespace) -> int:
    cfg, cj, _ = resolve_case(args.case_root)
    case_id, *_ = derive_case_id(cfg)
    contract = expected_record_contract(cfg, case_id)
    out = args.output.resolve()
    result_path = out / contract["result"]
    result = load_json(result_path)
    required = [out / contract[k] for k in ("edited_svg", "edited_png", "edited_pdf")]
    if any(not p.is_file() or p.stat().st_size == 0 for p in required):
        raise SurgeryError("Cannot attest: exported artifacts missing/empty")
    image = pymupdf_image_stats(required[1])
    review = {"status": "passed" if args.passed else "failed", "reviewer": args.reviewer, "observations": [x for x in args.observation if x], "image_readback": image, "edited_svg_sha256": sha256(required[0]), "png_sha256": sha256(required[1]), "pdf_sha256": sha256(required[2]), "limitations": [x for x in args.limitation if x], "scientific_scope": "Visual attestation only; scientific meaning remains governed by workorder/source review."}
    if not review["observations"]:
        raise SurgeryError("At least one concrete --observation is required")
    if not review["limitations"]:
        raise SurgeryError("At least one concrete --limitation is required")
    if "visual_review" in contract:
        atomic_json(out / contract["visual_review"], review)
    result["status"] = "complete" if args.passed else "failed"
    result["visual_review_detail"] = review
    atomic_json(result_path, result)
    if "edited" in contract:
        p = out / contract["edited"]
        edited = load_json(p)
        edited.update({"status": result["status"], "visual_review": review["status"], "result": str(result_path)})
        atomic_json(p, edited)
    if "record_key" in contract:
        p = out / contract["record_key"]
        rec = load_json(p)
        rec.update({"edited": str(out / contract["edited"]), "result": str(result_path), "status": result["status"]})
        atomic_json(p, rec)
    if "validation" in contract:
        p = out / contract["validation"]
        val = load_json(p)
        val["visual_review"] = review
        atomic_json(p, val)
    if "run_manifest" in contract:
        p = out / contract["run_manifest"]
        manifest = load_json(p)
        manifest.update({"status": result["status"], "visual_review": review["status"], "final_result": str(result_path)})
        atomic_json(p, manifest)
        work_manifest = args.work.resolve() / "run_manifest.json"
        if work_manifest.is_file():
            saved = load_json(work_manifest)
            if saved.get("case_id") != case_id:
                raise SurgeryError("Work manifest belongs to another case")
            saved.update({"status": result["status"], "visual_review": review["status"], "final_result": str(result_path)})
            atomic_json(work_manifest, saved)
    print(json.dumps({"case_id": case_id, "status": result["status"], "result": str(result_path)}, ensure_ascii=False))
    return 0 if args.passed else 4


def pymupdf_image_stats(path: Path) -> dict:
    import pymupdf
    with pymupdf.open(path) as d:
        p = d[0]
        pix = p.get_pixmap(alpha=False)
        return {"png_pages": d.page_count, "size": [pix.width, pix.height], "sha256": sha256(path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "attest"):
        p = sub.add_parser(name)
        p.add_argument("--case-root", type=Path, default=DEFAULT_CASE)
        p.add_argument("--work", type=Path, default=DEFAULT_WORK)
        p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    sub.choices["attest"].add_argument("--reviewer", required=True)
    sub.choices["attest"].add_argument("--observation", action="append", default=[])
    sub.choices["attest"].add_argument("--limitation", action="append", default=[])
    sub.choices["attest"].add_argument("--passed", action="store_true")
    args = parser.parse_args(argv)
    try:
        return run_surgery(args) if args.command == "run" else attest(args)
    except SurgeryError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
