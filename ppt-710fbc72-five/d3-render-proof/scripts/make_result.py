#!/usr/bin/env python3
"""make_result.py — 汇总 finalize /app/output/result.json。

字段以 case.json 的 output_contract 为准，缺失字段如实填空并记入 uncertainty。
所有产物附 sha256；状态诚实：success | partial（写明缺什么）| failed。
"""
import json
import os


def sha256_of(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _artifact(path, output_dir, role):
    rel = os.path.relpath(path, output_dir)
    return {"path": rel, "role": role, "sha256": sha256_of(path),
            "bytes": os.path.getsize(path)}


def finalize(input_dir, work_dir, output_dir, status, summary, change_log,
             uncertainty=None, extra_evidence=None):
    with open(os.path.join(input_dir, "case.json"), encoding="utf-8") as f:
        case = json.load(f)
    fields = case.get("output_contract", {}).get("fields", [])

    artifacts = []
    for rel, role in [("deck.pptx", "editable_deck"),
                      ("deck.pdf", "exported_pdf"),
                      ("render_proof.json", "render_qa_report"),
                      ("result.json", "result")]:
        p = os.path.join(output_dir, rel)
        if os.path.exists(p) and rel != "result.json":
            artifacts.append(_artifact(p, output_dir, role))
    prev = os.path.join(output_dir, "preview")
    if os.path.isdir(prev):
        pngs = sorted(f for f in os.listdir(prev) if f.endswith(".png"))
        artifacts.append({"path": "preview/", "role": "rendered_previews",
                          "count": len(pngs), "files": pngs[:4] + (["..."] if len(pngs) > 4 else [])})

    # 证据映射：plan 中每页的 evidence + 页码
    evidence_map = []
    plan_path = os.path.join(work_dir, "slide_plan.json")
    if os.path.exists(plan_path):
        with open(plan_path, encoding="utf-8") as f:
            plan = json.load(f)
        for i, sl in enumerate(plan.get("slides", [])):
            evidence_map.append({
                "slide": i + 1, "title": sl.get("title", ""),
                "claim": sl.get("claim", ""),
                "evidence": sl.get("evidence", []),
                "figures": [fg.get("ref", "") for fg in sl.get("figures", [])]})
    if extra_evidence:
        evidence_map = {"slides": evidence_map, "render_qa": extra_evidence}

    sources = []
    mats = case.get("materials", {})
    for key, rel in mats.items():
        p = os.path.join(input_dir, rel)
        if os.path.exists(p):
            sources.append({"kind": key, "path": rel, "sha256": sha256_of(p)})
    for extra in ("task.md", "case.json"):
        p = os.path.join(input_dir, extra)
        if os.path.exists(p):
            sources.append({"kind": "input", "path": extra, "sha256": sha256_of(p)})

    result = {
        "case_id": case.get("case_id", "unknown"),
        "status": status,
        "summary": summary,
        "artifacts": artifacts,
        "evidence_map": evidence_map,
        "sources": sources,
        "uncertainty": uncertainty or [],
        "change_log": change_log,
    }
    for fld in fields:
        if fld not in result:
            result[fld] = None
            result["uncertainty"].append(f"output_contract 字段 '{fld}' 无对应产物，如实置空")
    with open(os.path.join(output_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result
