#!/usr/bin/env python3
"""Extract every MathML math node from publisher and formula XML sources."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from mathml_ir import (
    element_to_ir,
    independent_text_check,
    local_name,
    render_latex,
    roundtrip_ir,
)

SOURCE_FILENAMES = ("publisher-source.xml", "source-formulas.xml")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def load_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def strings_in(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from strings_in(item)
    elif isinstance(value, dict):
        for key in sorted(value):
            yield from strings_in(value[key])


def resolve_source(raw: str, case_dir: Path, input_root: Path) -> Optional[Path]:
    candidate = Path(raw).expanduser()
    options = [candidate] if candidate.is_absolute() else [case_dir / candidate, input_root / candidate]
    for option in options:
        if option.is_file():
            return option.resolve()
    return None


def discover_sources(case: Dict[str, Any], case_path: Path, input_root: Path, explicit: Sequence[str]) -> Tuple[List[Path], List[str]]:
    warnings: List[str] = []
    found: Dict[str, Path] = {}
    candidates: List[str] = list(explicit)
    candidates.extend(
        value
        for value in strings_in(case)
        if Path(value).name in SOURCE_FILENAMES
    )
    for raw in candidates:
        resolved = resolve_source(raw, case_path.parent, input_root)
        if resolved is None:
            if raw in explicit:
                warnings.append(f"Explicit source not found: {raw}")
            continue
        found[str(resolved)] = resolved
    if input_root.is_dir():
        for directory, dirnames, filenames in os.walk(input_root):
            dirnames.sort()
            for filename in sorted(filenames):
                if filename in SOURCE_FILENAMES:
                    resolved = (Path(directory) / filename).resolve()
                    found[str(resolved)] = resolved
    return [found[key] for key in sorted(found)], warnings


def direct_child(element: ET.Element, tag: str) -> Optional[ET.Element]:
    for child in list(element):
        if isinstance(child.tag, str) and local_name(child.tag) == tag:
            return child
    return None


def nearest(element: ET.Element, parents: Dict[ET.Element, ET.Element], tags: Iterable[str]) -> Optional[ET.Element]:
    accepted = set(tags)
    current: Optional[ET.Element] = element
    while current is not None:
        if local_name(current.tag) in accepted:
            return current
        current = parents.get(current)
    return None


def source_metadata(math: ET.Element, parents: Dict[ET.Element, ET.Element]) -> Dict[str, str]:
    owner = nearest(math, parents, {"disp-formula", "inline-formula", "formula"})
    id_owner = math if "id" in math.attrib else None
    if id_owner is None:
        current: Optional[ET.Element] = owner if owner is not None else parents.get(math)
        while current is not None:
            if "id" in current.attrib:
                id_owner = current
                break
            current = parents.get(current)
    source_id = id_owner.attrib.get("id", "") if id_owner is not None else ""

    label = math.attrib.get("label", "")
    if not label and owner is not None:
        label_node = direct_child(owner, "label")
        if label_node is not None:
            label = "".join(label_node.itertext()).strip()

    parent = parents.get(math)
    section_node = nearest(parent if parent is not None else math, parents, {"sec", "section"})
    section = ""
    if section_node is not None:
        title = direct_child(section_node, "title")
        if title is not None:
            section = " ".join("".join(title.itertext()).split())
        elif "id" in section_node.attrib:
            section = section_node.attrib["id"]
    return {"id": source_id, "label": label, "section": section}


def ordered_path(math: ET.Element, parents: Dict[ET.Element, ET.Element]) -> Tuple[List[Dict[str, Any]], str]:
    lineage: List[ET.Element] = []
    current: Optional[ET.Element] = math
    while current is not None:
        lineage.append(current)
        current = parents.get(current)
    lineage.reverse()
    steps: List[Dict[str, Any]] = []
    for index, element in enumerate(lineage):
        tag = local_name(element.tag)
        if index == 0:
            child_index = 1
            tag_index = 1
        else:
            siblings = [child for child in list(lineage[index - 1]) if isinstance(child.tag, str)]
            child_index = siblings.index(element) + 1
            same_tag = [child for child in siblings if local_name(child.tag) == tag]
            tag_index = same_tag.index(element) + 1
        steps.append({"tag": tag, "child_index": child_index, "tag_index": tag_index})
    xpath = "/" + "/".join(f"{step['tag']}[{step['tag_index']}]" for step in steps)
    return steps, xpath


def associated_tex_math(math: ET.Element, parents: Dict[ET.Element, ET.Element]) -> Optional[str]:
    containers: List[ET.Element] = []
    parent = parents.get(math)
    if parent is not None:
        containers.append(parent)
        grandparent = parents.get(parent)
        if grandparent is not None:
            containers.append(grandparent)
    for container in containers:
        tex = direct_child(container, "tex-math")
        if tex is not None:
            return "".join(tex.itertext())
    return None


def display_path(path: Path, input_root: Path) -> str:
    try:
        return path.relative_to(input_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def safe_key(path: Path, source_id: str, occurrence: int) -> str:
    raw = f"{path.stem}_{source_id or 'math'}_{occurrence:04d}"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", raw)


def markdown_catalog(catalog: Dict[str, Any]) -> str:
    lines = [
        "# MathML evidence catalog",
        "",
        f"- Case: `{catalog['case_id']}`",
        f"- Extraction status: **{catalog['status']}**",
        f"- Math nodes: **{catalog['formula_count']}**",
        "- Publisher `alttext`/`tex-math` comparisons are advisory and non-authoritative.",
        "- LaTeX and extraction are not scientific formula, variable, derivation, or numeric analysis.",
        "",
    ]
    if catalog.get("warnings"):
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {warning}" for warning in catalog["warnings"])
        lines.append("")
    if not catalog["formulas"]:
        lines.extend(
            [
                "## Insufficient evidence",
                "",
                "No `<math>` nodes were found in the discovered sources. No formula is inferred from prose, publisher text alone, or unrelated cases.",
                "",
            ]
        )
        return "\n".join(lines)
    lines.extend(["## Formula index", ""])
    for entry in catalog["formulas"]:
        source = entry["source"]
        lines.extend(
            [
                f"### `{entry['formula_key']}`",
                "",
                f"- XML source: `{source['path']}`",
                f"- Source id: `{source['id'] or '(none)'}`; label: `{source['label'] or '(none)'}`; section: `{source['section'] or '(none)'}`",
                f"- Ordered path: `{entry['xpath']}`",
                f"- IR: `{entry['ir_file']}`",
                f"- Roundtrip: **{entry['roundtrip']['status']}**; discrepancies: **{len(entry['roundtrip']['discrepancies'])}**",
                f"- Render status: **{entry['render_status']}**",
                f"- Publisher alttext: **{entry['publisher_checks']['alttext']['status']}**; tex-math: **{entry['publisher_checks']['tex_math']['status']}**",
                "",
                "```latex",
                entry["latex"],
                "```",
                "",
            ]
        )
        for issue in entry["render_issues"]:
            lines.append(f"- RENDER ISSUE `{issue['kind']}` at `{issue['path']}`: {issue['detail']}")
        for discrepancy in entry["roundtrip"]["discrepancies"]:
            lines.append(f"- ROUNDTRIP ISSUE `{discrepancy['kind']}` at `{discrepancy['path']}`")
        for unsupported in entry["roundtrip"]["unsupported_nodes"]:
            lines.append(f"- UNSUPPORTED `{unsupported['tag']}` at `{unsupported['path']}`")
        if entry["render_issues"] or entry["roundtrip"]["discrepancies"] or entry["roundtrip"]["unsupported_nodes"]:
            lines.append("")
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    bundle_root = Path(__file__).resolve().parents[1]
    case_path = Path(args.case).expanduser().resolve()
    task_path = Path(args.task).expanduser().resolve()
    work = Path(args.work).expanduser().resolve()
    input_root = Path(args.input_root).expanduser().resolve() if args.input_root else case_path.parent
    case = load_json(case_path)
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("case.json must contain a non-empty string case_id")
    task_text = task_path.read_text(encoding="utf-8")
    sources, warnings = discover_sources(case, case_path, input_root, args.source)
    destination = work / "mathml"
    formulas: List[Dict[str, Any]] = []
    source_summaries: List[Dict[str, Any]] = []
    used_keys: Dict[str, int] = {}

    for source_index, source_path in enumerate(sources, 1):
        try:
            root = ET.parse(source_path).getroot()
            parse_error = None
        except (ET.ParseError, OSError) as exc:
            warnings.append(f"Could not parse {source_path}: {exc}")
            source_summaries.append({"path": display_path(source_path, input_root), "math_count": 0, "parse_error": str(exc)})
            continue
        parents = {child: parent for parent in root.iter() for child in list(parent)}
        math_nodes = [node for node in root.iter() if isinstance(node.tag, str) and local_name(node.tag) == "math"]
        source_summaries.append({"path": display_path(source_path, input_root), "math_count": len(math_nodes), "parse_error": parse_error})
        for occurrence, math in enumerate(math_nodes, 1):
            metadata = source_metadata(math, parents)
            rel_path = display_path(source_path, input_root)
            base_key = safe_key(source_path, metadata["id"], occurrence)
            # Identical basenames/ids in different directories must not overwrite
            # one another's IR.  Preserve the simple key unless it collides.
            key = base_key if base_key not in used_keys else f"{base_key}_source-{source_index:02d}"
            while key in used_keys:
                key += "_x"
            used_keys[key] = source_index
            steps, xpath = ordered_path(math, parents)
            ir = element_to_ir(math)
            latex, render_issues = render_latex(ir)
            roundtrip = roundtrip_ir(ir)
            alttext = math.attrib.get("alttext")
            publisher_checks = {
                "alttext": independent_text_check(latex, alttext),
                "tex_math": independent_text_check(latex, associated_tex_math(math, parents)),
            }
            ir_file = Path("ir") / f"{key}.json"
            latex_file = Path("latex") / f"{key}.tex"
            roundtrip_file = Path("roundtrip") / f"{key}.json"
            entry = {
                "formula_key": key,
                "source": {"path": rel_path, **metadata},
                "ordered_path": steps,
                "xpath": xpath,
                "ir_file": (Path("mathml") / ir_file).as_posix(),
                "latex_file": (Path("mathml") / latex_file).as_posix(),
                "roundtrip_file": (Path("mathml") / roundtrip_file).as_posix(),
                "ir": ir,
                "latex": latex,
                "render_status": "partial" if render_issues else "success",
                "render_issues": render_issues,
                "roundtrip": roundtrip,
                "publisher_checks": publisher_checks,
            }
            formulas.append(entry)
            write_json(destination / ir_file, ir)
            write_text(destination / latex_file, latex + "\n")
            report = {"formula_key": key, **roundtrip}
            write_json(destination / roundtrip_file, report)

    if not sources:
        warnings.append("No publisher-source.xml or source-formulas.xml was discovered; no formula can be claimed.")
    if not formulas:
        status = "insufficient_evidence"
    elif any(
        entry["render_issues"]
        or entry["roundtrip"]["status"] != "pass"
        for entry in formulas
    ):
        status = "partial"
    else:
        status = "success"
    catalog = {
        "schema_version": "mathml-treemap-catalog-1",
        "case_id": case_id,
        "status": status,
        "task_file": task_path.name,
        "task_utf8_bytes": len(task_text.encode("utf-8")),
        "source_count": len(sources),
        "sources": source_summaries,
        "formula_count": len(formulas),
        "warnings": warnings,
        "formulas": formulas,
        "bundle": {"name": "mathml-treemap", "root": bundle_root.name},
    }
    write_json(destination / "catalog.json", catalog)
    write_text(destination / "catalog.md", markdown_catalog(catalog))
    write_json(
        destination / "summary.json",
        {
            "case_id": case_id,
            "status": status,
            "formula_count": len(formulas),
            "source_count": len(sources),
            "roundtrip_status_counts": {
                name: sum(entry["roundtrip"]["status"] == name for entry in formulas)
                for name in ("pass", "unsupported", "mismatch")
            },
            "catalog": "mathml/catalog.json",
            "catalog_markdown": "mathml/catalog.md",
            "warnings": warnings,
            "note": "Extraction does not supply scientific formula/variable/derivation/numeric analysis.",
        },
    )
    print(f"mathml-treemap: status={status}, formulas={len(formulas)}, catalog={destination / 'catalog.json'}")
    if status == "partial":
        print("mathml-treemap: unsupported/malformed nodes or roundtrip discrepancies were reported explicitly", file=sys.stderr)
        return 2
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--case", default="/input/case.json", help="Original case.json")
    result.add_argument("--task", default="/input/task.md", help="Original task.md")
    result.add_argument("--work", default="/app/work", help="Writable work directory")
    result.add_argument("--input-root", help="XML discovery root; defaults to case.json directory")
    result.add_argument("--source", action="append", default=[], help="Additional/explicit XML source (repeatable)")
    return result


def main() -> int:
    return run(parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
