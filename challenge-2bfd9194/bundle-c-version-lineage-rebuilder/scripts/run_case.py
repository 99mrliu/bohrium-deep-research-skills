#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_case.py — version-lineage-rebuilder 分阶段编排器（仅标准库，无网络）。

子命令：init / scan / lineage / plan / apply / verify / finalize / all
用法：  python3 run_case.py all --input /input --work /app/work --out /app/output

阶段说明：
  init     防御式解析 case.json，秒级写出第一版 result.json（status=in_progress）
  scan     流式 SHA-256 盘点全部材料，记录跳过项，绝不崩溃
  lineage  特色阶段：三级证据重建版本世系图（version_graph.json + LINEAGE_REPORT.md）
  plan     计算落库目标路径（latest→主目录规范化名，superseded→_versions/<stem>/，
           别名不重复入库，孤儿正常入库），冲突自动 __vN
  apply    复制不移动，幂等，写清单/日志/重复组/跳过与冲突
  verify   子进程跑独立校验器 verify_lineage.py，出 audit_report.json
  finalize 把校验结果折进 result.json：全 PASS 且无未决冲突→complete，
           有降级项→partial 并列明 limits，无法运行→blocked
任何阶段异常都记入 failures_and_recovery 并继续；任何情况下都留下 result.json。
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lineage  # noqa: E402

BUCKETS = ["papers", "data", "scans", "supplementary", "drafts", "admin",
           "_unassigned", "_versions"]
DATA_EXTS = {".csv", ".tsv", ".json", ".dat", ".xlsx", ".xls"}
PAPER_EXTS = {".pdf", ".doc", ".docx", ".tex", ".bib"}
TEXT_EXTS = {".txt", ".md"}

CONTRACT_MAP = {
    "result": "result.json", "result_json": "result.json",
    "library": "library/", "library_dir": "library/",
    "library_manifest": "LIBRARY_MANIFEST.jsonl", "manifest": "LIBRARY_MANIFEST.jsonl",
    "version_graph": "version_graph.json", "graph": "version_graph.json",
    "lineage_report": "LINEAGE_REPORT.md", "report": "LINEAGE_REPORT.md",
    "duplicates": "duplicates.json", "duplicates_json": "duplicates.json",
    "operations_journal": "operations_journal.jsonl", "journal": "operations_journal.jsonl",
    "skipped_and_conflicts": "skipped_and_conflicts.json",
    "audit_report": "audit_report.json", "audit": "audit_report.json",
    "qa_log": "QA_LOG.json", "qa": "QA_LOG.json",
}

# 未决冲突类型（出现即降级 partial，需模型裁定）
UNRESOLVED_CONFLICT_TYPES = {"cycle", "multi_parent", "multi_sink",
                             "unresolved_admin_reference"}


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def deep_find(obj, keys):
    """递归查找第一个命中键的值。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in keys:
                return v
        for v in obj.values():
            r = deep_find(v, keys)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = deep_find(v, keys)
            if r is not None:
                return r
    return None


def collect_contract_fields(obj):
    """递归收集 output_contract 字段名。"""
    raw = deep_find(obj, {"output_contract", "contract", "output_fields",
                          "required_fields", "outputs", "result_fields"})
    fields = []
    if isinstance(raw, dict):
        fields = [str(k) for k in raw.keys()]
    elif isinstance(raw, list):
        for it in raw:
            if isinstance(it, str):
                fields.append(it)
            elif isinstance(it, dict):
                for k in ("name", "field", "key", "id"):
                    if k in it:
                        fields.append(str(it[k]))
                        break
    elif isinstance(raw, str):
        fields = [raw]
    seen, out = set(), []
    for f in fields:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def classify_bucket(name: str) -> str:
    low = name.lower()
    _, dot, ext = name.rpartition(".")
    ext = ("." + ext.lower()) if dot else ""
    if lineage.NOTE_NAME_RE.search(name):
        return "admin"
    if "scan" in low or "扫描" in name:
        return "scans"
    if ext in DATA_EXTS:
        return "data"
    if "draft" in low or "草稿" in name or "草案" in name:
        return "drafts"
    if ext in PAPER_EXTS:
        return "papers"
    if ext in TEXT_EXTS:
        return "supplementary"
    return "_unassigned"


class Ctx:
    def __init__(self, args):
        self.input = os.path.abspath(args.input)
        self.work = os.path.abspath(args.work)
        self.out = os.path.abspath(args.out)
        os.makedirs(self.work, exist_ok=True)
        os.makedirs(self.out, exist_ok=True)

    def w(self, *p):
        return os.path.join(self.work, *p)

    def o(self, *p):
        return os.path.join(self.out, *p)


def load_failures(ctx):
    return read_json(ctx.w("failures.json"), []) or []


def save_failures(ctx, failures):
    write_json(ctx.w("failures.json"), failures)


def record_failure(ctx, stage, exc):
    failures = load_failures(ctx)
    failures.append({"stage": stage, "error": type(exc).__name__,
                     "detail": str(exc)[:500],
                     "traceback_tail": traceback.format_exc()[-800:],
                     "ts": now_iso()})
    save_failures(ctx, failures)


# ---------------------------------------------------------------- init
def stage_init(ctx):
    case_path = os.path.join(ctx.input, "case.json")
    case = read_json(case_path, {}) or {}
    uncertainties = []
    case_id = deep_find(case, {"case_id", "caseid", "id", "case"})
    if not case_id or not isinstance(case_id, (str, int)):
        case_id = "unknown_case"
        uncertainties.append("case.json 中未找到 case_id（尝试 case_id|caseId|id|case），记为 unknown_case")
    contract = collect_contract_fields(case)
    if not contract:
        uncertainties.append("case.json 中未找到 output_contract（尝试 6 种键名），contract_fields 为空")
    contract_fields = {}
    for f in contract:
        key = f.lower().replace("-", "_").replace(" ", "_")
        if key in CONTRACT_MAP:
            contract_fields[f] = CONTRACT_MAP[key]
        else:
            contract_fields[f] = {"value": None,
                                  "reason": "无默认映射，需按 task.md 约定人工确认交付物路径"}
    task_text = ""
    task_path = os.path.join(ctx.input, "task.md")
    try:
        with open(task_path, encoding="utf-8", errors="replace") as f:
            task_text = f.read()
    except OSError:
        uncertainties.append("未读到 task.md")
    with open(ctx.w("task_excerpt.txt"), "w", encoding="utf-8") as f:
        f.write(task_text[:4000])
    result = {
        "case_id": str(case_id),
        "status": "in_progress",
        "skill": "version-lineage-rebuilder",
        "contract_fields": contract_fields,
        "sources": [case_path if os.path.exists(case_path) else None,
                    task_path if os.path.exists(task_path) else None],
        "uncertainties": uncertainties,
        "change_records": [],
        "summary": {},
        "failures_and_recovery": [],
        "started_at": now_iso(),
    }
    result["sources"] = [s for s in result["sources"] if s]
    write_json(ctx.o("result.json"), result)
    write_json(ctx.w("case_meta.json"),
               {"case_id": str(case_id), "contract": contract})
    return result


# ---------------------------------------------------------------- scan
def stage_scan(ctx):
    records, skipped = lineage.scan_tree(ctx.input)
    write_json(ctx.w("scan.json"), {"records": records, "skipped": skipped})
    return records, skipped


# ---------------------------------------------------------------- lineage
def stage_lineage(ctx, records):
    overrides = read_json(ctx.w("lineage_overrides.json"), None)
    # task.md 可用“备注文件：xxx”显式指定备注文件
    extra = []
    try:
        with open(ctx.w("task_excerpt.txt"), encoding="utf-8") as f:
            for ln in f:
                m = None
                for sep in ("备注文件：", "备注文件:", "note file:", "notes file:"):
                    if sep in ln:
                        m = ln.split(sep, 1)[1].strip()
                        break
                if m:
                    extra.append(lineage.nfc(m))
    except OSError:
        pass
    graph = lineage.build_graph(records, ctx.input,
                                overrides=overrides, extra_note_paths=extra or None)
    write_json(ctx.o("version_graph.json"), graph)
    with open(ctx.o("LINEAGE_REPORT.md"), "w", encoding="utf-8") as f:
        f.write(lineage.render_report(graph))
    write_json(ctx.w("graph.json"), graph)
    return graph


# ---------------------------------------------------------------- plan
def stage_plan(ctx, records, graph):
    by_sha = {n["sha256"]: n for n in graph["nodes"]}
    rec_by_path = {r["path"]: r for r in records}
    latest_of = {m["latest_sha"]: m["stem"] for m in graph["chain_meta"]}
    chain_of = {}
    for ch, meta in zip(graph["chains"], graph["chain_meta"]):
        for pos, sha in enumerate(ch):
            chain_of[sha] = (meta, pos, len(ch))
    alias_paths = {a["alias_path"]: a for a in graph["aliases"]}

    plan = []
    for r in records:
        sha = r["sha256"]
        if r["path"] in alias_paths:
            a = alias_paths[r["path"]]
            plan.append({"source_path": r["path"], "sha256": sha, "size": r["size"],
                         "mtime": r["mtime"], "stem": r["stem"], "role": "alias",
                         "library_path": None, "bucket": None,
                         "alias_of": a["canonical_sha"],
                         "alias_of_path": a["canonical_path"]})
            continue
        if sha in latest_of:
            stem = latest_of[sha]
            ext = ("." + r["ext"]) if r["ext"] else ""
            bucket = classify_bucket(r["name"])
            lib = "%s/%s%s" % (bucket, stem, ext)
            plan.append({"source_path": r["path"], "sha256": sha, "size": r["size"],
                         "mtime": r["mtime"], "stem": stem, "role": "latest",
                         "library_path": lib, "bucket": bucket})
        elif sha in chain_of:
            meta, pos, total = chain_of[sha]
            lib = "_versions/%s/%s" % (meta["stem"], r["name"])
            plan.append({"source_path": r["path"], "sha256": sha, "size": r["size"],
                         "mtime": r["mtime"], "stem": r["stem"], "role": "superseded",
                         "library_path": lib, "bucket": "_versions"})
        else:
            bucket = classify_bucket(r["name"])
            lib = "%s/%s" % (bucket, r["name"])
            plan.append({"source_path": r["path"], "sha256": sha, "size": r["size"],
                         "mtime": r["mtime"], "stem": r["stem"], "role": "orphan",
                         "library_path": lib, "bucket": bucket})

    # 目标路径冲突：不同内容占用同一目标 → __vN（不覆盖）
    conflicts = []
    taken = {}
    for p in plan:
        lib = p["library_path"]
        if lib is None:
            continue
        if lib in taken and taken[lib]["sha256"] != p["sha256"]:
            base, dot, ext = p["library_path"].rpartition(".")
            n = 2
            while True:
                cand = "%s__v%d%s%s" % (base, n, dot, ext)
                if cand not in taken:
                    break
                n += 1
            conflicts.append({"type": "target_name_collision", "target": lib,
                              "kept": taken[lib]["source_path"],
                              "renamed": p["source_path"], "new_target": cand,
                              "resolution": "auto_suffix __v%d，不覆盖" % n})
            p["library_path"] = cand
            lib = cand
        taken[lib] = p
    write_json(ctx.w("plan.json"), {"plan": plan, "plan_conflicts": conflicts})
    return plan, conflicts


# ---------------------------------------------------------------- apply
def stage_apply(ctx, plan):
    lib_root = ctx.o("library")
    for b in BUCKETS:
        os.makedirs(os.path.join(lib_root, b), exist_ok=True)
    journal, manifest = [], []
    seq = 0
    for p in sorted(plan, key=lambda x: x["source_path"]):
        seq += 1
        entry = {"seq": seq, "op": "copy", "src": p["source_path"],
                 "dst": p["library_path"], "sha256": p["sha256"],
                 "role": p["role"]}  # 不记时间戳：保证重跑字节级幂等
        if p["library_path"] is None:  # 别名：不重复入库
            entry["op"] = "alias_record"
            entry["status"] = "recorded_not_copied"
            journal.append(entry)
            manifest.append({"source_path": p["source_path"], "sha256": p["sha256"],
                             "size": p["size"], "mtime": p["mtime"], "stem": p["stem"],
                             "role": "alias", "library_path": None,
                             "bucket": None, "alias_of": p["alias_of"],
                             "alias_of_path": p["alias_of_path"]})
            continue
        src = os.path.join(ctx.input, p["source_path"])
        dst = os.path.join(lib_root, p["library_path"])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            if os.path.exists(dst):
                if lineage.sha256_file(dst) == p["sha256"]:
                    entry["status"] = "already_committed_identical"
                else:  # 库里已有不同内容占名：再找 __vN，不覆盖
                    base, dot, ext = dst.rpartition(".")
                    n = 2
                    while os.path.exists("%s__v%d%s%s" % (base, n, dot, ext)):
                        if lineage.sha256_file("%s__v%d%s%s" % (base, n, dot, ext)) == p["sha256"]:
                            break
                        n += 1
                    dst = "%s__v%d%s%s" % (base, n, dot, ext)
                    p["library_path"] = os.path.relpath(dst, lib_root)
                    entry["dst"] = p["library_path"]
                    if lineage.sha256_file(dst) == p["sha256"]:
                        entry["status"] = "already_committed_identical"
                    else:
                        shutil.copy2(src, dst)
                        entry["status"] = "copied_with_suffix"
            else:
                shutil.copy2(src, dst)
                entry["status"] = "copied"
        except (OSError, shutil.Error) as e:
            entry["status"] = "failed"
            entry["error"] = str(e)[:200]
        journal.append(entry)
        manifest.append({"source_path": p["source_path"], "sha256": p["sha256"],
                         "size": p["size"], "mtime": p["mtime"], "stem": p["stem"],
                         "role": p["role"], "library_path": p["library_path"],
                         "bucket": p["bucket"]})
    with open(ctx.o("operations_journal.jsonl"), "w", encoding="utf-8") as f:
        for e in journal:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    with open(ctx.o("LIBRARY_MANIFEST.jsonl"), "w", encoding="utf-8") as f:
        for m in manifest:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    write_json(ctx.w("manifest.json"), manifest)
    return journal, manifest


def write_side_outputs(ctx, graph, skipped, plan_conflicts):
    dup_groups = {}
    for a in graph["aliases"]:
        g = dup_groups.setdefault(a["canonical_sha"],
                                  {"sha256": a["canonical_sha"],
                                   "canonical": a["canonical_path"], "aliases": []})
        g["aliases"].append(a["alias_path"])
    write_json(ctx.o("duplicates.json"),
               {"note": "同内容不同名为别名（alias），不是版本关系；仅正本入库",
                "groups": list(dup_groups.values())})
    write_json(ctx.o("skipped_and_conflicts.json"),
               {"skipped": skipped,
                "lineage_conflicts": graph["conflicts"],
                "plan_conflicts": plan_conflicts})


# ---------------------------------------------------------------- verify
def stage_verify(ctx):
    verifier = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "verify_lineage.py")
    proc = subprocess.run(
        [sys.executable, verifier, "--input", ctx.input, "--out", ctx.out],
        capture_output=True, text=True, timeout=600)
    audit = read_json(ctx.o("audit_report.json"), None)
    if audit is None:
        audit = {"overall": "FAIL",
                 "checks": [{"id": "verifier_run", "status": "FAIL",
                             "detail": "校验器未产出 audit_report.json；stderr: %s"
                                       % proc.stderr[-400:]}]}
        write_json(ctx.o("audit_report.json"), audit)
    return audit


# ---------------------------------------------------------------- finalize
def stage_finalize(ctx, audit):
    result = read_json(ctx.o("result.json"), None) or stage_init(ctx)
    scan = read_json(ctx.w("scan.json"), {}) or {}
    graph = read_json(ctx.w("graph.json"), {}) or {}
    manifest = read_json(ctx.w("manifest.json"), []) or []
    failures = load_failures(ctx)

    checks = audit.get("checks", [])
    failed_checks = [c for c in checks if c.get("status") != "PASS"]
    unresolved = [c for c in graph.get("conflicts", [])
                  if c.get("type") in UNRESOLVED_CONFLICT_TYPES]
    committed = [m for m in manifest if m.get("library_path")]
    summary = {
        "files_scanned": len(scan.get("records", [])),
        "files_committed": len(committed),
        "bytes_committed": sum(m.get("size", 0) for m in committed),
        "alias_groups": len({a["canonical_sha"] for a in graph.get("aliases", [])}),
        "version_chains": len(graph.get("chains", [])),
        "version_edges": len(graph.get("edges", [])),
        "skipped": len(scan.get("skipped", [])),
        "conflicts": len(graph.get("conflicts", [])),
        "audit_pass": sum(1 for c in checks if c.get("status") == "PASS"),
        "audit_fail": len(failed_checks),
    }
    limits = []
    if failed_checks:
        limits.append("audit 未全 PASS: " + "; ".join(
            "%s(%s)" % (c.get("id"), str(c.get("detail", ""))[:80])
            for c in failed_checks[:5]))
    if unresolved:
        limits.append("未决世系冲突: " + "; ".join(
            c.get("type", "?") for c in unresolved[:5])
            + "（可在 work/lineage_overrides.json 裁定后重跑）")
    if failures:
        limits.append("存在阶段异常 %d 起，见 failures_and_recovery" % len(failures))

    if not checks:
        status = "blocked"
        limits.append("校验器未产出任何检查项")
    elif failed_checks or unresolved or failures:
        status = "partial"
    else:
        status = "complete"

    # task.md 疑似含问题但未交付 QA_LOG.json → 诚实提示
    try:
        with open(ctx.w("task_excerpt.txt"), encoding="utf-8") as f:
            task_text = f.read()
    except OSError:
        task_text = ""
    if any(q in task_text for q in ("?", "？", "请回答", "检索", "查询")) \
            and not os.path.exists(ctx.o("QA_LOG.json")):
        result.setdefault("uncertainties", []).append(
            "task.md 疑似包含检索/问题，但 /app/output/QA_LOG.json 不存在；问答由模型负责作答")

    result.update({
        "status": status,
        "summary": summary,
        "limits": limits,
        "failures_and_recovery": failures,
        "audit_overall": audit.get("overall"),
        "change_records": [
            {"artifact": "library/", "action": "copy（不移动），latest 以规范化名入主目录，"
             "superseded 进 _versions/<stem>/，别名不重复入库"},
            {"artifact": "version_graph.json / LINEAGE_REPORT.md",
             "action": "三级证据重建版本世系；无证据不连边"},
        ],
        "finished_at": now_iso(),
    })
    write_json(ctx.o("result.json"), result)
    return result


# ---------------------------------------------------------------- driver
STAGES = ["init", "scan", "lineage", "plan", "apply", "verify", "finalize"]


def run_pipeline(ctx, only=None):
    todo = only or STAGES
    records, graph, plan, audit = [], {}, [], None
    skipped, plan_conflicts = [], []

    def need_scan():
        nonlocal records, skipped
        if not records:
            data = read_json(ctx.w("scan.json"), None)
            if data is None:
                records, skipped = stage_scan(ctx)
            else:
                records, skipped = data["records"], data["skipped"]

    def need_graph():
        nonlocal graph
        if not graph:
            graph = read_json(ctx.w("graph.json"), None)
            if graph is None:
                need_scan()
                graph = stage_lineage(ctx, records)

    for st in todo:
        try:
            if st == "init":
                stage_init(ctx)
            elif st == "scan":
                records, skipped = stage_scan(ctx)
            elif st == "lineage":
                need_scan()
                graph = stage_lineage(ctx, records)
            elif st == "plan":
                need_scan()
                need_graph()
                plan, plan_conflicts = stage_plan(ctx, records, graph)
            elif st == "apply":
                need_scan()
                need_graph()
                if not plan:
                    pdata = read_json(ctx.w("plan.json"), None)
                    if pdata is None:
                        plan, plan_conflicts = stage_plan(ctx, records, graph)
                    else:
                        plan, plan_conflicts = pdata["plan"], pdata["plan_conflicts"]
                stage_apply(ctx, plan)
                write_side_outputs(ctx, graph, skipped, plan_conflicts)
                plan = []  # 防重复执行
            elif st == "verify":
                audit = stage_verify(ctx)
            elif st == "finalize":
                if audit is None:
                    audit = read_json(ctx.o("audit_report.json"),
                                      {"overall": "FAIL", "checks": []})
                stage_finalize(ctx, audit)
        except Exception as exc:  # 记录并继续后续阶段
            record_failure(ctx, st, exc)


def main(argv=None):
    ap = argparse.ArgumentParser(description="version-lineage-rebuilder 编排器")
    ap.add_argument("command", choices=STAGES + ["all"])
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    args = ap.parse_args(argv)
    ctx = Ctx(args)
    if args.command == "all":
        run_pipeline(ctx)
    else:
        run_pipeline(ctx, only=[args.command])
    result = read_json(ctx.o("result.json"), {}) or {}
    print(json.dumps({"command": args.command,
                      "status": result.get("status", "in_progress"),
                      "summary": result.get("summary", {})},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
