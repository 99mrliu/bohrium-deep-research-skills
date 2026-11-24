#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_case.py — library-index-qa 分阶段编排器（stdlib only）。

子命令：init / scan / plan / apply / index / qa / rebuild / verify / finalize / all
统一参数：--input /input --work /app/work --out /app/output
另：qa/all 支持 --auto-answer（仅合成示例复跑用）、--answers（模型撰写答案合并）。

重心：落库的终点是可查询。整理 → 索引 → 带证据问答 → 仅凭清单重建，闭环。
任何阶段异常都记入 failures_and_recovery 并继续；任何情况下保留 result.json。
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONTRACT_MAP = {
    "library_manifest": "LIBRARY_MANIFEST.jsonl",
    "manifest": "LIBRARY_MANIFEST.jsonl",
    "qa_log": "QA_LOG.json",
    "index_stats": "index/index_stats.json",
    "catalog": "index/catalog.db",
    "index": "index/catalog.db",
    "audit_report": "audit_report.json",
    "rebuild_diff": "REBUILD_DIFF.json",
    "duplicates": "duplicates.json",
    "version_chains": "version_chains.json",
    "operations_journal": "operations_journal.jsonl",
    "skipped_and_conflicts": "skipped_and_conflicts.json",
    "search_guide": "SEARCH_GUIDE.md",
    "result": "result.json",
    "library": "library/",
}
QUESTION_KEYS = ("questions", "searches", "queries", "qa")
CORRUPT_MARK = b"[[SIMULATED-CORRUPT"
VERSION_TAILS = re.compile(
    r"(?:[_\-–\s]?(?:v\d+|final|final\d*|copy|副本|备份|最终版|定稿|终稿|修订版|修改版"
    r"|新版|旧版|最新版|草稿|draft|\(\d+\)|（\d+）))+$", re.IGNORECASE)

CATEGORY_RULES = [
    # (bucket, 判定函数) —— 顺序敏感，先匹配先生效；规则确定性、无随机
    ("scans", lambda n, e: e in (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp")
     or "扫描" in n or "scan" in n.lower()),
    ("supplementary", lambda n, e: "supp" in n.lower() or "补充" in n
     or n.lower().startswith("si_") or "supporting" in n.lower()),
    ("drafts", lambda n, e: "draft" in n.lower() or "草稿" in n),
    ("admin", lambda n, e: any(k in n for k in ("行政", "通知", "纪要", "备注", "备忘录"))
     or "admin" in n.lower() or "memo" in n.lower()),
    ("data", lambda n, e: e in (".csv", ".tsv", ".dat", ".xy", ".raw", ".xrdml", ".json")
     or "数据" in n or "记录" in n or "实验" in n or "metadata" in n.lower()),
    ("papers", lambda n, e: e in (".pdf", ".doc", ".docx", ".tex")
     or any(k in n.lower() for k in ("paper", "report", "manuscript"))
     or any(k in n for k in ("论文", "报告", "文献"))),
]


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def nfc(s):
    return unicodedata.normalize("NFC", s)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def state_path(work):
    return os.path.join(work, "state.json")


def load_state(work):
    if os.path.isfile(state_path(work)):
        with open(state_path(work), "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(work, state):
    os.makedirs(work, exist_ok=True)
    with open(state_path(work), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def journal(out, event, **fields):
    os.makedirs(out, exist_ok=True)
    rec = {"ts": now_iso(), "event": event}
    rec.update(fields)
    with open(os.path.join(out, "operations_journal.jsonl"), "a",
              encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_json_safe(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def find_key_recursive(obj, keys):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in keys:
                return v
        for v in obj.values():
            r = find_key_recursive(v, keys)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for item in obj:
            r = find_key_recursive(item, keys)
            if r is not None:
                return r
    return None


def collect_contract_fields(obj, found):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in (
                    "output_contract", "contract", "output_fields",
                    "required_fields", "outputs", "result_fields"):
                _collect_names(v, found)
            else:
                collect_contract_fields(v, found)
    elif isinstance(obj, list):
        for item in obj:
            collect_contract_fields(item, found)


def _collect_names(v, found):
    if isinstance(v, str) and v.strip():
        found.append(v.strip())
    elif isinstance(v, dict):
        for k in v:
            found.append(str(k))
    elif isinstance(v, list):
        for item in v:
            _collect_names(item, found)


def mirror_contract(names):
    fields = {}
    for name in names:
        key = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        path = CONTRACT_MAP.get(key) or CONTRACT_MAP.get(key.rstrip("s"))
        if path:
            fields[name] = {"value": path}
        else:
            fields[name] = {"value": None,
                            "reason": "未识别的契约字段，无对应交付物映射"}
    return fields


def write_result(out, state):
    os.makedirs(out, exist_ok=True)
    result = {
        "case_id": state.get("case_id", "unknown_case"),
        "status": state.get("status", "in_progress"),
        "skill": "library-index-qa",
        "contract_fields": state.get("contract_fields", {}),
        "summary": state.get("summary", {}),
        "qa_summary": state.get("qa_summary", {}),
        "degraded": state.get("degraded", False),
        "sources": state.get("sources", []),
        "uncertainties": state.get("uncertainties", []),
        "change_records": state.get("change_records", []),
        "failures_and_recovery": state.get("failures_and_recovery", []),
        "updated_at": now_iso(),
    }
    with open(os.path.join(out, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


def run_stage(fn):
    def wrapper(args, state):
        try:
            fn(args, state)
        except Exception as exc:  # 绝不崩溃：记录并继续
            state.setdefault("failures_and_recovery", []).append(
                {"stage": fn.__name__, "error": repr(exc),
                 "recovery": "已记录，继续后续阶段", "ts": now_iso()})
            save_state(args.work, state)
            write_result(args.out, state)
    return wrapper


# ---------------- init ----------------
@run_stage
def stage_init(args, state):
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)
    # 全新一轮：清空日志，保证重跑可核对
    for p in ("operations_journal.jsonl",):
        fp = os.path.join(args.out, p)
        if os.path.exists(fp):
            os.remove(fp)
    case = read_json_safe(os.path.join(args.input, "case.json")) or {}
    case_id = find_key_recursive(case, ("case_id", "caseid", "id", "case"))
    if isinstance(case_id, dict):
        case_id = None
    state["case_id"] = str(case_id) if case_id else "unknown_case"
    state.setdefault("uncertainties", [])
    if not case_id:
        state["uncertainties"].append(
            "case.json 中未找到 case_id|caseId|id|case，记为 unknown_case")
    names = []
    collect_contract_fields(case, names)
    state["contract_fields"] = mirror_contract(list(dict.fromkeys(names)))
    state["status"] = "in_progress"
    state["sources"] = ["/input/case.json", "/input/task.md"]
    task_path = os.path.join(args.input, "task.md")
    if os.path.isfile(task_path):
        with open(task_path, "r", encoding="utf-8", errors="replace") as f:
            excerpt = f.read(4096)
        with open(os.path.join(args.work, "task_excerpt.txt"), "w",
                  encoding="utf-8") as f:
            f.write(excerpt)
    state["change_records"] = [{"ts": now_iso(), "change": "init: result.json 建立"}]
    journal(args.out, "init", case_id=state["case_id"],
            contract_fields=len(state["contract_fields"]))
    save_state(args.work, state)
    write_result(args.out, state)


# ---------------- scan ----------------
@run_stage
def stage_scan(args, state):
    entries, skipped = [], []
    for root, dirs, names in os.walk(args.input):
        dirs.sort()
        for name in sorted(names, key=nfc):
            full = os.path.join(root, name)
            rel = nfc(os.path.relpath(full, args.input))
            if rel in ("case.json", "task.md"):
                continue
            try:
                st = os.stat(full)
                with open(full, "rb") as f:
                    head = f.read(4096)
                if CORRUPT_MARK in head:
                    skipped.append({
                        "path": rel,
                        "reason": "simulated_corrupt_marker: 文件含模拟损坏标记，"
                                  "按不可读处理",
                        "size": st.st_size})
                    entries.append({
                        "source_path": rel, "sha256": None, "size": st.st_size,
                        "mtime": datetime.datetime.fromtimestamp(
                            st.st_mtime, datetime.timezone.utc).isoformat(
                                timespec="seconds"),
                        "corrupt_simulated": True})
                    continue
                entries.append({
                    "source_path": rel, "sha256": sha256_file(full),
                    "size": st.st_size,
                    "mtime": datetime.datetime.fromtimestamp(
                        st.st_mtime, datetime.timezone.utc).isoformat(
                            timespec="seconds")})
            except (PermissionError, OSError, UnicodeError) as exc:
                skipped.append({"path": rel, "reason": "read_error: %r" % exc})
                entries.append({"source_path": rel, "sha256": None,
                                "size": None, "mtime": None})
    entries.sort(key=lambda e: nfc(e["source_path"]))
    state["scan"] = entries
    state["skipped"] = skipped
    journal(args.out, "scan", files=len(entries), skipped=len(skipped))
    save_state(args.work, state)


# ---------------- plan ----------------
def categorize(source_path):
    base = os.path.basename(source_path)
    name, ext = os.path.splitext(base)
    ext = ext.lower()
    for bucket, rule in CATEGORY_RULES:
        if rule(name, ext):
            return bucket
    return "_unassigned"


def norm_stem(source_path):
    base = nfc(os.path.splitext(os.path.basename(source_path))[0]).lower()
    stem = VERSION_TAILS.sub("", base).strip("_-– ")
    return stem or base


@run_stage
def stage_plan(args, state):
    entries = state.get("scan", [])
    plan = []
    # 重复组：按内容哈希
    by_hash = {}
    for e in entries:
        if e.get("sha256"):
            by_hash.setdefault(e["sha256"], []).append(e["source_path"])
    duplicates = [{"sha256": h, "members": sorted(ms, key=nfc),
                   "canonical": sorted(ms, key=nfc)[0]}
                  for h, ms in sorted(by_hash.items()) if len(ms) > 1]
    canonical_of = {}
    for d in duplicates:
        for m in d["members"][1:]:
            canonical_of[m] = d["canonical"]
    # 版本候选：规范化词干分组
    by_stem = {}
    for e in entries:
        if e.get("sha256"):
            by_stem.setdefault(norm_stem(e["source_path"]), []).append(e)
    version_chains = []
    for stem, members in sorted(by_stem.items()):
        if len(members) > 1:
            ordered = sorted(members, key=lambda m: (m.get("mtime") or "",
                                                     nfc(m["source_path"])))
            version_chains.append({
                "stem": stem,
                "chain": [{"source_path": m["source_path"],
                           "sha256": m["sha256"], "mtime": m["mtime"]}
                          for m in ordered],
                "note": "词干相同内容不同，按 mtime 排序；内容相同者另见 duplicates"})
    # 目标路径 + 冲突
    planned_targets = {}
    conflicts = []
    for e in entries:
        src = e["source_path"]
        if e.get("corrupt_simulated") or not e.get("sha256"):
            plan.append({**e, "category": None, "rel_path": None,
                         "action": "skipped",
                         "reason": "不可读或模拟损坏，不入库",
                         "duplicate_of": None})
            continue
        category = categorize(src)
        target = nfc(os.path.join(category, os.path.basename(src)))
        if src in canonical_of:
            canon = canonical_of[src]
            plan.append({**e, "category": category, "rel_path": None,
                         "action": "already_committed_identical",
                         "reason": "内容哈希与 %s 相同，按别名登记不重复落库" % canon,
                         "duplicate_of": canon})
            continue
        # 同批次内目标冲突：不同内容同名 -> __vN
        final = target
        n = 2
        while final in planned_targets and planned_targets[final] != e["sha256"]:
            stem, ext = os.path.splitext(target)
            final = "%s__v%d%s" % (stem, n, ext)
            n += 1
        if final != target:
            conflicts.append({"source": src, "intended": target,
                              "resolved": final,
                              "reason": "同批内同名不同内容，加 __vN 后缀"})
        planned_targets[final] = e["sha256"]
        plan.append({**e, "category": category, "rel_path": final,
                     "action": "commit_new", "reason": "", "duplicate_of": None})
    state["plan"] = plan
    state["duplicates"] = duplicates
    state["version_chains"] = version_chains
    state["conflicts"] = conflicts
    with open(os.path.join(args.out, "duplicates.json"), "w",
              encoding="utf-8") as f:
        json.dump({"duplicate_groups": duplicates,
                   "rule": "按内容 SHA-256 分组，不按文件名"}, f,
                  ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "version_chains.json"), "w",
              encoding="utf-8") as f:
        json.dump({"version_chains": version_chains,
                   "rule": "规范化词干（去版本尾巴）分组，按 mtime 排序"}, f,
                  ensure_ascii=False, indent=2)
    journal(args.out, "plan", planned=len(plan),
            duplicate_groups=len(duplicates),
            version_chains=len(version_chains), conflicts=len(conflicts))
    save_state(args.work, state)


# ---------------- apply ----------------
@run_stage
def stage_apply(args, state):
    plan = state.get("plan", [])
    lib = os.path.join(args.out, "library")
    os.makedirs(lib, exist_ok=True)
    manifest_rows = []
    new_conflicts = state.setdefault("conflicts", [])
    for p in plan:
        action, rel = p["action"], p.get("rel_path")
        if action == "commit_new":
            dst = os.path.join(lib, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.exists(dst):
                disk_hash = sha256_file(dst)
                if disk_hash == p["sha256"]:
                    # 幂等重跑：内容已在库，不重复复制；action 保持 commit_new，
                    # 与"别名"（duplicate_of 非空）语义区分，保证 manifest 跨轮稳定
                    p["reason"] = "库中已有同内容文件（幂等重跑，未重复复制）"
                    journal(args.out, "apply", source=p["source_path"],
                            target=rel, action="noop_identical")
                    manifest_rows.append({
                        "source_path": p["source_path"], "rel_path": rel,
                        "sha256": p.get("sha256"), "size": p.get("size"),
                        "mtime": p.get("mtime"), "category": p.get("category"),
                        "action": action, "duplicate_of": p.get("duplicate_of"),
                        "title_guess": "", "reason": p.get("reason", "")})
                    continue
                else:
                    stem, ext = os.path.splitext(rel)
                    n = 2
                    while os.path.exists(dst) and sha256_file(dst) != p["sha256"]:
                        rel = "%s__v%d%s" % (stem, n, ext)
                        dst = os.path.join(lib, rel)
                        n += 1
                    new_conflicts.append({
                        "source": p["source_path"], "intended": p["rel_path"],
                        "resolved": rel,
                        "reason": "库中已有不同内容同名文件，加 __vN 后缀，不覆盖"})
                    p["rel_path"] = rel
                    shutil.copy2(os.path.join(args.input, p["source_path"]), dst)
            else:
                shutil.copy2(os.path.join(args.input, p["source_path"]), dst)
            journal(args.out, "apply", source=p["source_path"],
                    target=rel, action=action)
        elif action == "already_committed_identical":
            # 别名：登记到规范副本的 rel_path
            canon = p.get("duplicate_of")
            canon_row = next((q for q in plan if q["source_path"] == canon), None)
            rel = canon_row.get("rel_path") if canon_row else None
            journal(args.out, "apply", source=p["source_path"],
                    target=rel, action=action)
        else:
            journal(args.out, "apply", source=p["source_path"],
                    target=None, action="skipped", reason=p.get("reason"))
        manifest_rows.append({
            "source_path": p["source_path"], "rel_path": rel,
            "sha256": p.get("sha256"), "size": p.get("size"),
            "mtime": p.get("mtime"), "category": p.get("category"),
            "action": action, "duplicate_of": p.get("duplicate_of"),
            "title_guess": "", "reason": p.get("reason", "")})
    manifest_rows.sort(key=lambda r: nfc(r["source_path"]))
    with open(os.path.join(args.out, "LIBRARY_MANIFEST.jsonl"), "w",
              encoding="utf-8") as f:
        for r in manifest_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    merged_skipped = {}
    for item in state.get("skipped", []):
        merged_skipped[item["path"]] = item
    for r in manifest_rows:
        if r["action"] == "skipped" and r["source_path"] not in merged_skipped:
            merged_skipped[r["source_path"]] = {"path": r["source_path"],
                                                "reason": r["reason"]}
    skipped_list = [merged_skipped[k] for k in sorted(merged_skipped, key=nfc)]
    state["skipped_merged"] = skipped_list
    skipped_conflicts = {
        "skipped": skipped_list,
        "conflicts": new_conflicts,
        "note": "绝不静默跳过；冲突一律加 __vN 不覆盖",
    }
    with open(os.path.join(args.out, "skipped_and_conflicts.json"), "w",
              encoding="utf-8") as f:
        json.dump(skipped_conflicts, f, ensure_ascii=False, indent=2)
    state["manifest_rows"] = len(manifest_rows)
    state.setdefault("change_records", []).append(
        {"ts": now_iso(), "change": "apply: %d 行写入 manifest" % len(manifest_rows)})
    save_state(args.work, state)
    write_result(args.out, state)


# ---------------- index ----------------
@run_stage
def stage_index(args, state):
    proc = subprocess.run(
        [sys.executable, os.path.join(SCRIPT_DIR, "indexer.py"),
         "--manifest", os.path.join(args.out, "LIBRARY_MANIFEST.jsonl"),
         "--library", os.path.join(args.out, "library"),
         "--out-dir", os.path.join(args.out, "index"),
         "--stats", os.path.join(args.out, "index", "index_stats.json"),
         "--guide", os.path.join(args.out, "SEARCH_GUIDE.md")],
        capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError("indexer failed: %s" % proc.stderr[-500:])
    info = json.loads(proc.stdout.strip().splitlines()[-1])
    state["degraded"] = bool(info.get("degraded"))
    state["index_stats"] = info
    journal(args.out, "index", **info)
    save_state(args.work, state)


# ---------------- qa ----------------
@run_stage
def stage_qa(args, state):
    questions_path = os.path.join(args.work, "questions.json")
    if not os.path.isfile(questions_path):
        # 防御式提取：从 case.json 递归找 questions|searches|queries|qa
        case = read_json_safe(os.path.join(args.input, "case.json")) or {}
        found = []
        _extract_q(case, found)
        with open(questions_path, "w", encoding="utf-8") as f:
            json.dump({"questions": found, "origin": "extracted_by_run_case"},
                      f, ensure_ascii=False, indent=2)
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, "query.py"),
           "--db", os.path.join(args.out, "index", "catalog.db"),
           "--questions", questions_path,
           "--case", os.path.join(args.input, "case.json"),
           "--task", os.path.join(args.input, "task.md"),
           "--out", os.path.join(args.out, "QA_LOG.json"),
           "--raw", os.path.join(args.work, "query_raw.json")]
    if getattr(args, "auto_answer", False):
        cmd.append("--auto-answer")
    answers = getattr(args, "answers", None) or os.path.join(
        args.work, "qa_answers.json")
    if os.path.isfile(answers):
        cmd += ["--answers", answers]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError("query failed: %s" % proc.stderr[-500:])
    info = json.loads(proc.stdout.strip().splitlines()[-1])
    state["qa_summary"] = info
    if info.get("questions", 0) > 0 and info.get("unanswered", 0) > 0:
        state.setdefault("uncertainties", []).append(
            "%d 个问题检索无命中，已如实标 unanswered" % info["unanswered"])
    journal(args.out, "qa", **info)
    save_state(args.work, state)
    write_result(args.out, state)


def _extract_q(obj, found):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in QUESTION_KEYS:
                _collect(v, found)
            else:
                _extract_q(v, found)
    elif isinstance(obj, list):
        for item in obj:
            _extract_q(item, found)


def _collect(v, found):
    if isinstance(v, str) and v.strip():
        found.append(v.strip())
    elif isinstance(v, dict):
        for k in ("question", "q", "query", "text", "search"):
            if isinstance(v.get(k), str):
                found.append(v[k].strip())
                return
    elif isinstance(v, list):
        for item in v:
            _collect(item, found)


# ---------------- rebuild ----------------
@run_stage
def stage_rebuild(args, state):
    proc = subprocess.run(
        [sys.executable, os.path.join(SCRIPT_DIR, "rebuild_index.py"),
         "--manifest", os.path.join(args.out, "LIBRARY_MANIFEST.jsonl"),
         "--library", os.path.join(args.out, "library"),
         "--out", os.path.join(args.out, "index"),
         "--runtime-db", os.path.join(args.out, "index", "catalog.db"),
         "--diff-out", os.path.join(args.out, "REBUILD_DIFF.json")],
        capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError("rebuild failed: %s" % proc.stderr[-500:])
    info = json.loads(proc.stdout.strip().splitlines()[-1])
    journal(args.out, "rebuild", **info)
    state["rebuild"] = info
    save_state(args.work, state)


# ---------------- verify ----------------
@run_stage
def stage_verify(args, state):
    proc = subprocess.run(
        [sys.executable, os.path.join(SCRIPT_DIR, "verify_index.py"),
         "--input", args.input, "--out", args.out,
         "--report", os.path.join(args.out, "audit_report.json")],
        capture_output=True, text=True, timeout=600)
    # verify 返回 1 表示 FAIL，不是崩溃
    state["verify_returncode"] = proc.returncode
    journal(args.out, "verify", output=proc.stdout.strip()[-300:])
    save_state(args.work, state)


# ---------------- finalize ----------------
@run_stage
def stage_finalize(args, state):
    report = read_json_safe(os.path.join(args.out, "audit_report.json")) or {}
    overall = report.get("overall", "FAIL")
    failed = [c["check"] for c in report.get("checks", [])
              if c.get("status") != "PASS"]
    scan = state.get("scan", [])
    summary = {
        "input_files": len(scan),
        "manifest_rows": state.get("manifest_rows", 0),
        "committed_bytes": sum(e.get("size") or 0 for e in scan),
        "duplicate_groups": len(state.get("duplicates", [])),
        "version_chains": len(state.get("version_chains", [])),
        "skipped": len(state.get("skipped_merged", state.get("skipped", []))),
        "conflicts": len(state.get("conflicts", [])),
        "indexed_text_files": state.get("index_stats", {}).get("indexed", 0),
        "qa": state.get("qa_summary", {}),
    }
    state["summary"] = summary
    limits = []
    if state.get("degraded"):
        limits.append("运行环境 sqlite 无 FTS5，索引降级为 LIKE 检索（功能可用）")
    if summary["skipped"]:
        limits.append("%d 个文件被跳过（见 skipped_and_conflicts.json）"
                      % summary["skipped"])
    if summary["conflicts"]:
        limits.append("%d 起命名冲突已加 __vN 解决，未覆盖任何文件"
                      % summary["conflicts"])
    if overall == "PASS" and not limits:
        state["status"] = "complete"
    elif overall == "PASS" or state.get("manifest_rows"):
        state["status"] = "partial"
        if overall != "PASS":
            limits.append("audit 未全 PASS：%s" % ", ".join(failed))
    else:
        state["status"] = "blocked"
        limits.append("未能完成落库：%s" % ", ".join(failed))
    if limits:
        state.setdefault("uncertainties", []).extend(
            l for l in limits if l not in state.get("uncertainties", []))
    state.setdefault("change_records", []).append(
        {"ts": now_iso(), "change": "finalize: status=%s (audit=%s)"
         % (state["status"], overall)})
    journal(args.out, "finalize", status=state["status"], audit=overall)
    save_state(args.work, state)
    write_result(args.out, state)


STAGES = {
    "init": stage_init, "scan": stage_scan, "plan": stage_plan,
    "apply": stage_apply, "index": stage_index, "qa": stage_qa,
    "rebuild": stage_rebuild, "verify": stage_verify, "finalize": stage_finalize,
}
ALL_ORDER = ["init", "scan", "plan", "apply", "index", "qa",
             "rebuild", "verify", "finalize"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="library-index-qa 编排器")
    ap.add_argument("command", choices=list(STAGES) + ["all"])
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    ap.add_argument("--auto-answer", action="store_true",
                    help="仅合成示例：qa 阶段用 top-1 snippet 作草稿答案")
    ap.add_argument("--answers", help="模型撰写的 qa_answers.json（正式运行用）")
    args = ap.parse_args(argv)

    state = load_state(args.work)
    order = ALL_ORDER if args.command == "all" else [args.command]
    for name in order:
        STAGES[name](args, state)
    # 无论发生什么，最后都保证 result.json 存在
    if not os.path.isfile(os.path.join(args.out, "result.json")):
        write_result(args.out, state)
    print(json.dumps({"command": args.command,
                      "status": state.get("status", "in_progress"),
                      "failures": len(state.get("failures_and_recovery", []))},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
