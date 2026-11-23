#!/usr/bin/env python3
"""Build the formula dependency graph of a paper.

Nodes: math nodes from the publisher XML (id, display label, section context,
structural signature). Edges:
  - citation edges from prose references (Equation (n), Eq. (n), 式(n), plus
    substitution phrases) resolved through the label map;
  - symbol-flow edges when a symbol used in formula A was introduced in the
    context of formula B.
Unresolved citations (label not present, or ambiguous) are recorded verbatim.
Outputs graph.json, graph.mmd, and graph.png when matplotlib is available.
Stdlib only; matplotlib optional.
"""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

GREEK = {"α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "μ": "mu",
         "ν": "nu", "π": "pi", "ρ": "rho", "σ": "sigma", "τ": "tau",
         "φ": "phi", "ψ": "psi", "ω": "omega", "ε": "epsilon", "η": "eta",
         "θ": "theta", "κ": "kappa", "λ": "lambda", "ξ": "xi"}

CITE_RE = re.compile(
    r"(?:Equation|Eq\.?|式|公式)\s*[(（]\s*([0-9]+[a-zA-Z]?)\s*[)）]")
SUBST_RE = re.compile(
    r"[Ss]ubstitut\w+\s+(?:[^.]{0,80}?)\s+into\s+(?:[^.]{0,40}?)"
    r"(?:Equation|Eq\.?)\s*[(（]?\s*([0-9]+[a-zA-Z]?)\s*[)）]?")


def local(tag):
    return tag.rsplit("}", 1)[-1]


def symbols_of(node):
    out = set()
    for el in node.iter():
        if local(el.tag) == "mi":
            t = (el.text or "").strip()
            out.add("".join(GREEK.get(c, c) for c in t))
    return out


def collect_sections(root):
    """Yield (section_id, paragraph_text, math_nodes_in_order)."""
    secs = [el for el in root.iter() if local(el.tag) == "sec"] or [root]
    for sec in secs:
        sid = sec.get("id", "?")
        texts = []
        for el in sec.iter():
            if local(el.tag) in ("p", "title"):
                texts.append("".join(el.itertext()))
        maths = [el for el in sec.iter() if local(el.tag) == "math"]
        labels = {}
        for el in sec.iter():
            if local(el.tag) == "disp-formula":
                lab = el.findtext(".//label")
                if lab:
                    m = re.search(r"([0-9]+[a-zA-Z]?)", lab)
                    for node in el.iter():
                        if local(node.tag) == "math" and m:
                            labels.setdefault(m.group(1), set()).add(node.get("id"))
        yield sid, "\n".join(texts), maths, labels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--input", default=None)
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args()
    case_path = Path(args.case)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    input_root = Path(args.input) if args.input else case_path.parent
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    artifacts = (case.get("artifacts") or {})
    pub = artifacts.get("publisher_source_xml") or artifacts.get("source_formulas_xml")

    graph = {"nodes": [], "edges": [], "unresolved_citations": [], "notes": []}
    if not pub or not (input_root / pub).exists():
        graph["notes"].append("no formula-bearing artifact; graph empty")
        (work / "graph.json").write_text(json.dumps(graph, indent=2, ensure_ascii=False))
        print("no formula artifact; empty graph -> %s" % (work / "graph.json"))
        return

    root = ET.parse(input_root / pub).getroot()
    nodes, label_map, sec_of = {}, {}, {}
    sym_of, sec_texts = {}, {}
    for sid, text, maths, labels in collect_sections(root):
        sec_texts[sid] = text
        for lab, ids in labels.items():
            label_map.setdefault(lab, set()).update(ids)
        for node in maths:
            nid = node.get("id") or ("anon-%d" % len(nodes))
            nodes[nid] = {"id": nid, "section": sid,
                          "symbols": sorted(symbols_of(node)),
                          "alttext_present": node.get("alttext") is not None}
            sec_of[nid] = sid
            sym_of[nid] = symbols_of(node)
    graph["nodes"] = sorted(nodes.values(), key=lambda n: n["id"])

    # Citation edges with verbatim evidence.
    for sid, text in sec_texts.items():
        for m in CITE_RE.finditer(text):
            lab = m.group(1)
            ctx = text[max(0, m.start() - 60):m.end() + 40].strip()
            targets = sorted(label_map.get(lab, set()))
            if len(targets) == 1:
                graph["edges"].append({
                    "from": "text:" + sid, "to": targets[0], "type": "citation",
                    "label": lab, "evidence": ctx})
            else:
                graph["unresolved_citations"].append({
                    "label": lab, "section": sid, "evidence": ctx,
                    "reason": ("no formula carries this label" if not targets
                               else "ambiguous: %s" % targets)})
        for m in SUBST_RE.finditer(text):
            lab = m.group(1)
            targets = sorted(label_map.get(lab, set()))
            src_symbols = re.findall(r"([A-Za-z]+_[0-9]+|[A-Za-zα-ωΑ-Ω]+)\s*=", m.group(0))
            src = sorted({n for n, syms in sym_of.items()
                          if any("".join(GREEK.get(c, c) for c in s) in syms for s in src_symbols)})
            for t in targets or []:
                for s in src:
                    if s != t:
                        graph["edges"].append({
                            "from": s, "to": t, "type": "substitution",
                            "evidence": m.group(0)[:200]})

    # Symbol-flow edges: symbol used in A, introduced in B (B != A), same doc.
    first_use = {}
    order = [n["id"] for n in graph["nodes"]]
    for nid in order:
        for s in sym_of.get(nid, set()):
            first_use.setdefault(s, nid)
    seen = set()
    for nid in order:
        for s in sym_of.get(nid, set()):
            src = first_use.get(s)
            if src and src != nid:
                key = (src, nid, "symbol_flow")
                if key not in seen:
                    seen.add(key)
                    graph["edges"].append({
                        "from": src, "to": nid, "type": "symbol_flow",
                        "symbol": s, "evidence": "symbol %s introduced at %s" % (s, src)})
    graph["summary"] = {"nodes": len(graph["nodes"]), "edges": len(graph["edges"]),
                        "unresolved_citations": len(graph["unresolved_citations"])}
    (work / "graph.json").write_text(json.dumps(graph, indent=2, ensure_ascii=False),
                                     encoding="utf-8")

    # Mermaid for reuse.
    lines = ["graph TD"]
    for n in graph["nodes"]:
        lines.append('  %s["%s (%s)"]' % (n["id"].replace("-", "_"), n["id"], n["section"]))
    for e in graph["edges"]:
        f = e["from"].replace(":", "_").replace("-", "_")
        t = e["to"].replace(":", "_").replace("-", "_")
        lines.append("  %s -->|%s| %s" % (f, e["type"], t))
    (work / "graph.mmd").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # PNG rendering when matplotlib is present.
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        ids = order
        pos = {nid: (i, 0) for i, nid in enumerate(ids)}
        fig, ax = plt.subplots(figsize=(max(4, 1.8 * len(ids)), 2.6))
        for nid, (x, y) in pos.items():
            ax.add_patch(plt.Rectangle((x - 0.55, y - 0.22), 1.1, 0.44,
                                       fc="#eef3fb", ec="#2a5db0"))
            ax.text(x, y, nid, ha="center", va="center", fontsize=10)
        for i, e in enumerate(graph["edges"]):
            f, t = e["from"], e["to"]
            if f in pos and t in pos:
                ax.annotate("", xy=(pos[t][0] - 0.58 if pos[t][0] > pos[f][0] else pos[t][0],
                                    pos[t][1]),
                            xytext=(pos[f][0] + 0.58 if pos[t][0] > pos[f][0] else pos[f][0],
                                    pos[f][1]),
                            arrowprops=dict(arrowstyle="->", color="#555",
                                            connectionstyle="arc3,rad=-0.25"))
                ax.text((pos[f][0] + pos[t][0]) / 2, 0.3 + 0.12 * i, e["type"],
                        ha="center", fontsize=7, color="#555")
        ax.set_xlim(-1, len(ids)); ax.set_ylim(-0.7, 0.7); ax.axis("off")
        fig.tight_layout(); fig.savefig(work / "graph.png", dpi=140)
        plt.close(fig)
        graph["notes"].append("graph.png rendered with matplotlib")
        print("graph: %d nodes, %d edges, %d unresolved -> %s (+png)"
              % (graph["summary"]["nodes"], graph["summary"]["edges"],
                 graph["summary"]["unresolved_citations"], work / "graph.json"))
    except ImportError:
        graph["notes"].append("matplotlib unavailable; Mermaid output only")
        print("graph: %d nodes, %d edges (Mermaid only) -> %s"
              % (graph["summary"]["nodes"], graph["summary"]["edges"], work / "graph.json"))


if __name__ == "__main__":
    main()
