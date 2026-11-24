#!/usr/bin/env python3
"""Two-phase entry point for template-native-deck (重心: 模板套用工程).

    python3 run_case.py prepare --input /input --work /app/work \
        --output /app/output
    python3 run_case.py finish  --input /input --work /app/work \
        --output /app/output

prepare: bootstrap deps, read case.json/task.md/materials, dissect the
template into template_inventory.json (the ONLY legal source of layouts),
extract paper text + page renders for the agent, write a partial-first
result.json containing every output_contract field, prefill slide_plan.json
(with a per-slide `layout` chosen from the inventory), print NEXT ACTION.

finish: validate plan layouts against the inventory, build deck.pptx
strictly from the template, run the XML-level inheritance audit (the
spike; a failing audit blocks status=success), export PDF/PNG + QA, and
finalize result.json.
"""
import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONTRACT_FIELDS = ["case_id", "status", "summary", "artifacts",
                           "evidence_map", "sources", "uncertainty",
                           "change_log"]


# ---------------------------------------------------------------- helpers

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds")


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_script(script, args, change_log, label):
    cmd = [sys.executable, os.path.join(HERE, script)] + args
    proc = subprocess.run(cmd, capture_output=True, text=True)
    change_log.append({"ts": now_iso(), "event": f"ran {label}",
                       "returncode": proc.returncode,
                       "stdout_tail": (proc.stdout or "")[-400:],
                       "stderr_tail": (proc.stderr or "")[-400:]})
    sys.stdout.write(proc.stdout or "")
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or "")
    return proc.returncode


def bootstrap_deps(change_log):
    """Ensure python-pptx / PyMuPDF / pillow; pip install if missing."""
    needed = {"pptx": "python-pptx", "pymupdf": "PyMuPDF", "PIL": "pillow"}
    missing = []
    for module, pkg in needed.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(pkg)
    if not missing:
        change_log.append({"ts": now_iso(),
                           "event": "deps ok: python-pptx/PyMuPDF/pillow"})
        return []
    for pkg in missing:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg],
            capture_output=True, text=True, timeout=600)
        change_log.append({"ts": now_iso(), "event": f"pip install {pkg}",
                           "returncode": proc.returncode})
    still = []
    for module, pkg in needed.items():
        try:
            __import__(module)
        except ImportError:
            still.append(pkg)
    return still  # caller records as degraded/uncertainty if non-empty


def discover_materials(input_dir, case):
    """Resolve template / starting_deck / paper paths. Never guess content
    from names alone: only choose among files that actually exist."""
    mats = case.get("materials") or {}
    found = {"template": None, "starting_deck": None, "paper": None,
             "all_pptx": [], "all_pdf": []}
    for root, _dirs, files in os.walk(input_dir):
        for fn in files:
            low = fn.lower()
            full = os.path.join(root, fn)
            if low.endswith(".pptx"):
                found["all_pptx"].append(full)
            elif low.endswith(".pdf"):
                found["all_pdf"].append(full)

    def resolve(key):
        val = mats.get(key)
        if not val:
            return None
        cand = val if os.path.isabs(val) else os.path.join(input_dir, val)
        return cand if os.path.exists(cand) else None

    found["template"] = resolve("template")
    found["starting_deck"] = resolve("starting_deck") \
        or resolve("starting") or resolve("deck")
    found["paper"] = resolve("paper")

    pptx_left = [p for p in found["all_pptx"]
                 if p not in (found["template"], found["starting_deck"])]
    if found["template"] is None:
        named = [p for p in pptx_left if "template" in
                 os.path.basename(p).lower()]
        if named:
            found["template"] = named[0]
            pptx_left.remove(named[0])
    if found["starting_deck"] is None:
        named = [p for p in pptx_left if any(
            k in os.path.basename(p).lower()
            for k in ("start", "deck", "draft", "origin"))]
        if named:
            found["starting_deck"] = named[0]
            pptx_left.remove(named[0])
    if found["template"] is None and found["starting_deck"] is None \
            and found["all_pptx"]:
        found["template"] = found["all_pptx"][0]  # single deck = template
    elif found["template"] is None:
        found["template"] = found["starting_deck"]
    if found["paper"] is None and found["all_pdf"]:
        found["paper"] = found["all_pdf"][0]
    return found


def contract_fields(case):
    oc = case.get("output_contract") or {}
    fields = oc.get("fields") if isinstance(oc, dict) else None
    return list(fields) if fields else list(DEFAULT_CONTRACT_FIELDS)


def empty_result(case_id, fields):
    base = {"case_id": case_id, "status": "partial",
            "summary": "", "artifacts": [], "evidence_map": {},
            "sources": [], "uncertainty": [], "change_log": []}
    for f in fields:
        base.setdefault(f, {} if f == "evidence_map" else
                        ([] if f in ("artifacts", "sources", "uncertainty",
                                     "change_log") else ""))
    return base


# ---------------------------------------------------------------- prepare

def cmd_prepare(args):
    work, out, inp = args.work, args.output, args.input
    os.makedirs(work, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    change_log = [{"ts": now_iso(), "event": "prepare started"}]

    missing_deps = bootstrap_deps(change_log)

    case = load_json(os.path.join(inp, "case.json")) or {}
    case_id = case.get("case_id", "unknown-case")
    fields = contract_fields(case)
    task_path = os.path.join(inp, "task.md")
    task_text = ""
    if os.path.exists(task_path):
        with open(task_path, encoding="utf-8") as f:
            task_text = f.read()
    change_log.append({"ts": now_iso(), "event": "read case.json + task.md",
                       "case_id": case_id,
                       "task_md_bytes": len(task_text)})

    result = empty_result(case_id, fields)
    result["change_log"] = change_log
    result["sources"] = [{"type": "case", "path": "case.json"},
                         {"type": "task", "path": "task.md"}]
    uncertainty = []
    if missing_deps:
        uncertainty.append(
            f"python deps could not be installed: {missing_deps}")

    # --- materials ---
    mats = discover_materials(inp, case)
    change_log.append({"ts": now_iso(), "event": "materials discovered",
                       "template": mats["template"],
                       "starting_deck": mats["starting_deck"],
                       "paper": mats["paper"]})
    base = mats["starting_deck"] or mats["template"]
    if mats["template"] is None:
        uncertainty.append("未找到模板 pptx：无法做模板继承，仅能交付 partial。")
    if mats["paper"] is None:
        uncertainty.append("未找到论文 PDF：paper 抽取被跳过。")
    for role in ("template", "starting_deck", "paper"):
        if mats[role]:
            result["sources"].append({"type": role, "path": mats[role],
                                      "sha256": sha256_file(mats[role])})

    # --- template dissection: the ONLY legal source of layouts ---
    inventory_path = os.path.join(work, "template_inventory.json")
    inventory = None
    if mats["template"]:
        rc = run_script("inspect_template.py",
                        [mats["template"], inventory_path],
                        change_log, "inspect_template")
        if rc == 0:
            inventory = load_json(inventory_path)
        else:
            uncertainty.append("inspect_template.py 失败：无版式清单。")

    # --- paper extraction (convenience layer for the agent) ---
    paper_dir = os.path.join(work, "paper")
    text_dir = os.path.join(paper_dir, "text")
    figs_dir = os.path.join(paper_dir, "figs")
    paper_index = {"pages": []}
    if mats["paper"] and not missing_deps:
        os.makedirs(text_dir, exist_ok=True)
        os.makedirs(figs_dir, exist_ok=True)
        try:
            import pymupdf
            with pymupdf.open(mats["paper"]) as doc:
                for i, page in enumerate(doc, start=1):
                    text = page.get_text("text")
                    with open(os.path.join(text_dir, f"page-{i}.txt"),
                              "w", encoding="utf-8") as f:
                        f.write(text)
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
                    png = os.path.join(figs_dir, f"page-{i}.png")
                    pix.save(png)
                    paper_index["pages"].append(
                        {"page": i, "chars": len(text),
                         "render": png,
                         "first_line": (text.strip().splitlines() or [""])[0]
                         [:120]})
            change_log.append({"ts": now_iso(),
                               "event": f"paper extracted: "
                                        f"{len(paper_index['pages'])} pages"})
        except Exception as exc:
            uncertainty.append(f"论文抽取失败: {exc}")
        write_json(os.path.join(paper_dir, "paper_index.json"), paper_index)

    # --- prefill slide_plan.json (layout chosen from the inventory ONLY) ---
    plan_path = os.path.join(work, "slide_plan.json")
    legal_names = [l["name"] for l in (inventory or {}).get("layouts", [])]

    def pick(*preferred):
        for p in preferred:
            if p in legal_names:
                return p
        return legal_names[0] if legal_names else None

    if not os.path.exists(plan_path):
        skeleton = [
            {"kind": "title",
             "layout": pick("Title Slide", "Title Only"),
             "title": "", "claim": "", "bullets": [], "figures": [],
             "evidence": [], "notes": ""},
            {"kind": "background",
             "layout": pick("Title and Content", "Title Only"),
             "title": "研究背景", "claim": "", "bullets": [], "figures": [],
             "evidence": [], "notes": ""},
            {"kind": "method",
             "layout": pick("Title and Content", "Title Only"),
             "title": "方法", "claim": "", "bullets": [], "figures": [],
             "evidence": [], "notes": ""},
            {"kind": "results",
             "layout": pick("Title and Content", "Title Only"),
             "title": "结果", "claim": "", "bullets": [], "figures": [],
             "evidence": [], "notes": ""},
            {"kind": "discussion",
             "layout": pick("Title and Content", "Title Only"),
             "title": "讨论与限制", "claim": "", "bullets": [],
             "figures": [], "evidence": [], "notes": ""},
            {"kind": "conclusion",
             "layout": pick("Title and Content", "Title Only"),
             "title": "结论", "claim": "", "bullets": [], "figures": [],
             "evidence": [], "notes": ""},
        ]
        plan = {
            "_instructions": (
                "编辑本文件完成创作（唯一需要创作的一步)。规则: "
                "1) layout 只能取 _legal_layouts 中的名字; "
                "2) 数字必须与 paper/text 原文逐字一致, 并在 evidence 里给出来源; "
                "3) figures[].path 用 paper/figs/ 下的页面渲染或自行裁切的图; "
                "4) 找不到出处的内容不上页; 5) 讲稿写进 notes。"),
            "_legal_layouts": legal_names,
            "_base_deck": base,
            "_paper_pages": [p["page"] for p in paper_index["pages"]],
            "mainline": {"problem": "", "method": "", "results": "",
                         "limitations": ""},
            "audience": "", "duration_min": 12,
            "slides": skeleton,
        }
        write_json(plan_path, plan)
        change_log.append({"ts": now_iso(),
                           "event": "prefilled slide_plan.json skeleton"})

    # --- partial-first result.json with ALL contract fields ---
    result["summary"] = ("prepare 完成：模板已解剖为 template_inventory.json，"
                         "论文已抽取，slide_plan.json 骨架待 Agent 填写。")
    result["artifacts"] = [
        {"path": inventory_path, "kind": "template_inventory",
         "sha256": sha256_file(inventory_path)} if inventory else None,
        {"path": plan_path, "kind": "slide_plan_skeleton",
         "sha256": sha256_file(plan_path)},
    ]
    result["artifacts"] = [a for a in result["artifacts"] if a]
    result["uncertainty"] = uncertainty
    result["status"] = "partial"
    write_json(os.path.join(out, "result.json"), result)

    print("\n===== NEXT ACTION =====")
    print(f"1. 阅读论文抽取文本: {text_dir}/page-*.txt "
          f"(页面渲染: {figs_dir}/page-*.png)")
    print(f"2. 查看模板清单(唯一合法版式来源): {inventory_path}")
    print(f"3. 编辑 {plan_path} —— 填充 mainline/每页 title/claim/bullets/"
          f"figures/evidence/notes；layout 只能取自 _legal_layouts。")
    print(f"4. 然后运行: python3 {os.path.join(HERE, 'run_case.py')} finish "
          f"--input {inp} --work {work} --output {out}")
    print("=======================")
    return 0


# ---------------------------------------------------------------- finish

def cmd_finish(args):
    work, out, inp = args.work, args.output, args.input
    os.makedirs(out, exist_ok=True)
    change_log = [{"ts": now_iso(), "event": "finish started"}]

    case = load_json(os.path.join(inp, "case.json")) or {}
    case_id = case.get("case_id", "unknown-case")
    fields = contract_fields(case)
    result = load_json(os.path.join(out, "result.json")) \
        or empty_result(case_id, fields)
    for f in fields:
        result.setdefault(f, empty_result(case_id, fields)[f])
    result["change_log"] = (result.get("change_log") or []) + change_log
    change_log = result["change_log"]
    uncertainty = list(result.get("uncertainty") or [])

    mats = discover_materials(inp, case)
    template = mats["template"]
    base = mats["starting_deck"] or template

    inventory_path = os.path.join(work, "template_inventory.json")
    inventory = load_json(inventory_path)
    if inventory is None and template:
        if run_script("inspect_template.py",
                      [template, inventory_path],
                      change_log, "inspect_template") == 0:
            inventory = load_json(inventory_path)
    legal_names = [l["name"] for l in (inventory or {}).get("layouts", [])]

    plan_path = os.path.join(work, "slide_plan.json")
    plan = load_json(plan_path)
    if plan is None:
        uncertainty.append("slide_plan.json 缺失或无法解析：无法构建。")
        result.update(status="failed",
                      summary="slide_plan.json missing; nothing built.",
                      uncertainty=uncertainty)
        write_json(os.path.join(out, "result.json"), result)
        print("[run_case finish] FAILED: no slide_plan.json")
        return 1

    # plan lint against the inventory (layouts must be legal)
    plan_lint = {"illegal_layouts": [], "slides_without_evidence": [],
                 "n_slides": len(plan.get("slides", []))}
    for i, spec in enumerate(plan.get("slides", []), start=1):
        lay = spec.get("layout")
        if legal_names and lay not in legal_names:
            plan_lint["illegal_layouts"].append({"slide": i, "layout": lay})
        if spec.get("kind") not in ("title",) and not spec.get("evidence"):
            plan_lint["slides_without_evidence"].append(i)
    write_json(os.path.join(work, "plan_lint.json"), plan_lint)
    if plan_lint["illegal_layouts"]:
        uncertainty.append(
            f"plan 含非法版式(将被替换并记录): "
            f"{plan_lint['illegal_layouts']}")
    change_log.append({"ts": now_iso(), "event": "plan linted",
                       "illegal_layouts": len(plan_lint["illegal_layouts"])})

    # --- build strictly from the template ---
    deck_path = os.path.join(out, "deck.pptx")
    build_report_path = os.path.join(work, "build_report.json")
    rc_build = 1
    if base:
        rc_build = run_script(
            "build_deck.py",
            ["--base", base, "--plan", plan_path,
             "--inventory", inventory_path,
             "--out", deck_path, "--report", build_report_path],
            change_log, "build_deck")
    else:
        uncertainty.append("无模板/起始稿：未构建 deck.pptx。")

    # --- XML-level inheritance audit (the spike; gates delivery) ---
    audit_path = os.path.join(out, "inheritance_report.json")
    audit = {"overall_pass": False}
    if rc_build == 0 and template:
        run_script("audit_inheritance.py",
                   ["--deck", deck_path, "--template", template,
                    "--inventory", inventory_path, "--out", audit_path],
                   change_log, "audit_inheritance")
        audit = load_json(audit_path) or audit
    elif rc_build == 0:
        uncertainty.append("无模板参照：继承审计未运行。")
    if not audit.get("overall_pass"):
        uncertainty.append(
            "继承审计未通过 —— 按 SKILL.md 规定不得标记 success；"
            f"failures={audit.get('failures')}")

    # --- export + render QA ---
    qa_path = os.path.join(out, "qa_report.json")
    qa = {"render_ok": False, "degraded": ["deck missing"]}
    if rc_build == 0:
        run_script("export_render.py",
                   ["--deck", deck_path, "--outdir", out,
                    "--report", qa_path],
                   change_log, "export_render")
        qa = load_json(qa_path) or qa
        for d in qa.get("degraded", []):
            uncertainty.append(f"render degraded: {d}")

    # --- evidence map from the plan ---
    evidence_map = {}
    for i, spec in enumerate(plan.get("slides", []), start=1):
        evidence_map[f"slide-{i}"] = {
            "kind": spec.get("kind"), "title": spec.get("title"),
            "layout": spec.get("layout"),
            "evidence": spec.get("evidence", []),
            "figures": [f.get("ref") for f in spec.get("figures", [])],
        }

    # --- finalize result.json (superset of output_contract) ---
    artifacts = []
    for path, kind in ((deck_path, "editable_deck"),
                       (os.path.join(out, "deck.pdf"), "rendered_pdf"),
                       (audit_path, "inheritance_report"),
                       (qa_path, "qa_report"),
                       (inventory_path, "template_inventory"),
                       (build_report_path, "build_report"),
                       (plan_path, "slide_plan")):
        if os.path.exists(path):
            artifacts.append({"path": path, "kind": kind,
                              "sha256": sha256_file(path),
                              "bytes": os.path.getsize(path)})
    preview_dir = os.path.join(out, "preview")
    if os.path.isdir(preview_dir):
        for fn in sorted(os.listdir(preview_dir)):
            full = os.path.join(preview_dir, fn)
            artifacts.append({"path": full, "kind": "preview_png",
                              "sha256": sha256_file(full),
                              "bytes": os.path.getsize(full)})

    build_report = load_json(build_report_path) or {}
    status = "success" if (
        rc_build == 0 and audit.get("overall_pass")
        and qa.get("render_ok")) else "partial"
    if rc_build != 0:
        status = "failed" if not os.path.exists(deck_path) else "partial"

    result.update({
        "case_id": case_id,
        "status": status,
        "summary": (
            f"构建 {len(plan.get('slides', []))} 页；"
            f"删除起始稿旧页 {len(build_report.get('deleted_slides', []))} 页；"
            f"占位符替代 {len(build_report.get('substitutions', []))} 处；"
            f"继承审计 overall_pass={audit.get('overall_pass')}"
            f"(theme_preserved={audit.get('theme_preserved')})；"
            f"渲染 page_parity={qa.get('page_parity')}。"),
        "artifacts": artifacts,
        "evidence_map": evidence_map,
        "uncertainty": uncertainty,
        "mainline": plan.get("mainline"),
        "inheritance_overall_pass": audit.get("overall_pass"),
        "theme_preserved": audit.get("theme_preserved"),
        "render_page_parity": qa.get("page_parity"),
    })
    result["sources"] = result.get("sources") or []
    write_json(os.path.join(out, "result.json"), result)

    print("\n===== 逐页核对清单 =====")
    per = {s["slide"]: s for s in audit.get("per_slide", [])}
    for i, spec in enumerate(plan.get("slides", []), start=1):
        a = per.get(i, {})
        print(f"slide {i}: [{spec.get('kind')}] {spec.get('title')!r} "
              f"layout={spec.get('layout')} chain_ok={a.get('ok')} "
              f"evidence={len(spec.get('evidence', []))} "
              f"figures={len(spec.get('figures', []))} "
              f"notes={len(spec.get('notes', ''))}chars")
    print(f"inheritance overall_pass={audit.get('overall_pass')} "
          f"theme_preserved={audit.get('theme_preserved')}")
    print(f"render: pdf_pages={qa.get('pdf_pages')} "
          f"pptx_slides={qa.get('pptx_slides')} "
          f"parity={qa.get('page_parity')}")
    print(f"status={status} -> {os.path.join(out, 'result.json')}")
    print("=======================")
    return 0 if status == "success" else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("prepare", "finish"):
        p = sub.add_parser(name)
        p.add_argument("--input", required=True)
        p.add_argument("--work", required=True)
        p.add_argument("--output", required=True)
    args = ap.parse_args(argv)
    return cmd_prepare(args) if args.cmd == "prepare" else cmd_finish(args)


if __name__ == "__main__":
    sys.exit(main())
