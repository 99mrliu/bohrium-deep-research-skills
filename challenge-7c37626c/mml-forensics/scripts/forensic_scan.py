#!/usr/bin/env python3
"""Forensic scan of input artifacts: integrity hashes, XML well-formedness
with error location, corrupted-XML math-fragment salvage, MathML structure
statistics, and subset-vs-source consistency checks. Stdlib only.
"""
import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from signature import find_math_nodes, local, mathml_signature, compare_multisets

MATH_NS = "http://www.w3.org/1998/Math/MathML"


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def salvage_math_fragments(text):
    """Recover parseable <math> fragments from a malformed XML document."""
    salvaged = []
    for m in re.finditer(r"<([A-Za-z0-9_]+:)?math\b[^>]*>.*?</\1?math\s*>",
                         text, re.S):
        frag = m.group(0)
        node = None
        error = None
        try:
            if re.search(r"<[A-Za-z0-9_]+:math", frag) and "xmlns" not in frag:
                open_tag = frag[:frag.index(">") + 1]
                frag = frag.replace(
                    open_tag, open_tag.replace("<mml:math", '<mml:math xmlns:mml="%s"' % MATH_NS, 1), 1)
            node = ET.fromstring(frag)
        except ET.ParseError as exc:
            error = str(exc)
        salvaged.append({
            "byte_start": m.start(), "byte_end": m.end(),
            "parsed": node is not None, "parse_error": error,
            "salvaged_fragment": True,
        })
    return salvaged


def structure_stats(root):
    stats = Counter()
    for el in root.iter():
        stats[local(el.tag)] += 1
    return dict(sorted(stats.items()))


def math_inventory(root):
    items = []
    for node in find_math_nodes(root):
        c = Counter()
        mathml_signature(node, c)
        items.append({
            "id": node.get("id"),
            "alttext": node.get("alttext"),
            "features": dict(sorted(c.items())),
        })
    return items


def subset_check(source_root, subset_root):
    """Match subset math nodes against source math nodes by id + structure."""
    src = {n.get("id"): n for n in find_math_nodes(source_root)}
    report = []
    for node in find_math_nodes(subset_root):
        sid = node.get("id")
        entry = {"id": sid, "matched_in_source": None}
        if sid not in src:
            entry["matched_in_source"] = "id_absent"
        else:
            a, b = Counter(), Counter()
            mathml_signature(node, a)
            mathml_signature(src[sid], b)
            match, missing, extra = compare_multisets(a, b)
            entry["matched_in_source"] = "identical" if match else "divergent"
            if not match:
                entry["missing_in_source"] = missing
                entry["extra_in_source"] = extra
        report.append(entry)
    return report


def scan_xml(path, root_text):
    entry = {"path": str(path), "well_formed": True}
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        entry["structure_stats"] = structure_stats(root)
        entry["math_nodes"] = math_inventory(root)
        entry["root_tag"] = local(root.tag)
    except ET.ParseError as exc:
        entry["well_formed"] = False
        entry["error"] = str(exc)
        entry["salvaged"] = salvage_math_fragments(root_text)
        entry["salvage_note"] = (
            "salvaged fragments are weaker evidence than parsed nodes; "
            "downstream steps must carry degraded status")
    return entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args()
    inp = Path(args.input)
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)

    files = []
    for p in sorted(inp.rglob("*")):
        if p.is_file():
            files.append({"path": str(p.relative_to(inp)),
                          "bytes": p.stat().st_size,
                          "sha256": sha256_of(p)})

    xmls = {}
    for p in sorted(inp.rglob("*.xml")):
        xmls[str(p.relative_to(inp))] = scan_xml(p, p.read_text(encoding="utf-8", errors="replace"))

    report = {
        "input_root": str(inp),
        "files": files,
        "xml": xmls,
        "summary": {
            "files": len(files),
            "xml_well_formed": sum(1 for v in xmls.values() if v["well_formed"]),
            "xml_malformed": sum(1 for v in xmls.values() if not v["well_formed"]),
        },
    }

    # subset vs source consistency (e.g. source-formulas.xml vs publisher XML)
    subset = next((k for k in xmls if "formulas" in Path(k).name), None)
    source = next((k for k in xmls if "formulas" not in Path(k).name and xmls[k]["well_formed"]), None)
    if subset and source and xmls[subset]["well_formed"] and xmls[source]["well_formed"]:
        sr = ET.parse(inp / source).getroot()
        sub = ET.parse(inp / subset).getroot()
        report["subset_vs_source"] = {
            "subset": subset, "source": source,
            "items": subset_check(sr, sub),
        }

    (work / "forensic_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    print("report -> %s" % (work / "forensic_report.json"))


if __name__ == "__main__":
    main()
