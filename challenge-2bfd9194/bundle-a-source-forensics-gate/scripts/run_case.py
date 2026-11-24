#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_case.py — source-forensics-gate 分阶段编排器（仅 Python 标准库）。

子命令：init / scan / forensics / plan / apply / verify / finalize / all
参数：  --input /input --work /app/work --out /app/output

任何阶段异常都记录进 result.json 的 failures_and_recovery 并降级状态，
任何情况下都保证 /app/output/result.json 存在。复制不移动；幂等，重跑收敛零操作。
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import forensics  # noqa: E402  (同目录特色引擎)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VERIFY_SCRIPT = os.path.join(SCRIPT_DIR, "verify_forensics.py")

SKIP_INPUT_NAMES = {"case.json", "task.md"}

# 契约字段名 → 交付物相对路径的映射线索（小写包含匹配）
CONTRACT_HINTS = [
    ("library_manifest", "LIBRARY_MANIFEST.jsonl"),
    ("manifest", "LIBRARY_MANIFEST.jsonl"),
    ("forensics_report", "FORENSICS_REPORT.json"),
    ("forensics", "FORENSICS_REPORT.json"),
    ("audit_report", "audit_report.json"),
    ("audit", "audit_report.json"),
    ("qa_log", "QA_LOG.json"),
    ("qa", "QA_LOG.json"),
    ("duplicates", "duplicates.json"),
    ("version_chains", "version_chains.json"),
    ("journal", "operations_journal.jsonl"),
    ("operations", "operations_journal.jsonl"),
    ("skipped", "skipped_and_conflicts.json"),
    ("conflicts", "skipped_and_conflicts.json"),
    ("library", "library/"),
    ("result", "result.json"),
]

# 目录缺省桶：扩展名 → 桶
BUCKET_BY_EXT = {
    "papers": {".pdf", ".md", ".tex", ".doc", ".docx", ".rtf"},
    "data": {".csv", ".tsv", ".json", ".jsonl", ".xlsx", ".xls", ".sqlite", ".sqlite3", ".db", ".yaml", ".yml"},
    "scans": {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif"},
    "supplementary": {".zip", ".gz", ".rar", ".7z", ".xml", ".html", ".htm"},
}
ADMIN_HINT = re.compile(r"(admin|note|notes|memo|备注|说明|备忘|行政)", re.I)
DRAFT_HINT = re.compile(r"(draft|草稿|草案|初稿|半成品)", re.I)

VER_RE = [
    re.compile(r"\.bak$", re.I),
    re.compile(r"[ _\-（(]?(最终版|终稿|定稿|最新版|正式版|final|副本|拷贝|备份|backup|copy)[ _\-）)]?$", re.I),
    re.compile(r"[ _\-]?v\d+(\.\d+)?$", re.I),
    re.compile(r"[ _\-]?(19|20)\d{2}[-_.年]?\d{1,2}[-_.月]?\d{1,2}日?$"),
]


# ------------------------------------------------------------------ 小工具
def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def nfc(s):
    return unicodedata.normalize("NFC", s)


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def append_jsonl(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def deep_find(obj, keys):
    """递归在嵌套 dict/list 中查找任一 key（不区分大小写）的值。"""
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


def normalize_stem(filename):
    """剥离版本/别名/备份/尾日期标记，得到分组用词干（NFC，小写）。"""
    stem = nfc(os.path.splitext(filename)[0])
    stem = re.sub(r"\.bak$", "", stem, flags=re.I)
    prev = None
    while prev != stem:
        prev = stem
        for rx in VER_RE[1:]:
            stem = rx.sub("", stem)
    return stem.strip(" _-").lower()


def bucket_for(filename):
    ext = os.path.splitext(filename)[1].lower()
    if DRAFT_HINT.search(filename):
        return "drafts"
    if ADMIN_HINT.search(filename):
        return "admin"
    for bucket, exts in BUCKET_BY_EXT.items():
        if ext in exts:
            return bucket
    return "_unassigned"


def map_contract_fields(case):
    raw = deep_find(case, {"output_contract", "contract", "output_fields",
                           "required_fields", "outputs", "result_fields"})
    fields = []
    if isinstance(raw, dict):
        fields = list(raw.keys())
    elif isinstance(raw, list):
        fields = [x for x in raw if isinstance(x, str)]
    elif isinstance(raw, str):
        fields = [raw]
    out = {}
    for name in fields:
        low = name.lower()
        target = None
        for token, path in CONTRACT_HINTS:
            if token in low:
                target = path
                break
        out[name] = target if target else {"value": None,
                                           "reason": "未识别的契约字段，无法映射到交付物"}
    return out


def collect_input_paths(input_dir, case):
    """递归遍历 /input（排除 case.json/task.md），并收纳 case.json 引用的路径。"""
    rels = set()
    for dirpath, _dirs, files in os.walk(input_dir):
        for fn in files:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, input_dir)
            if nfc(rel) in SKIP_INPUT_NAMES and dirpath == input_dir:
                continue
            rels.add(rel)

    strings = []

    def _walk(o):
        if isinstance(o, dict):
            for v in o.values():
                _walk(v)
        elif isinstance(o, list):
            for v in o:
                _walk(v)
        elif isinstance(o, str):
            strings.append(o)

    if isinstance(case, dict):
        _walk(case)
    for s in strings:
        cand = s.strip().lstrip("./")
        if not cand or len(cand) > 512 or "\n" in cand:
            continue
        full = os.path.join(input_dir, cand)
        if os.path.isfile(full):
            rel = os.path.relpath(full, input_dir)
            if nfc(rel) not in SKIP_INPUT_NAMES:
                rels.add(rel)
    return sorted(rels, key=nfc)


# ------------------------------------------------------------------ 阶段
class Ctx:
    def __init__(self, args):
        self.input = os.path.abspath(args.input)
        self.work = os.path.abspath(args.work)
        self.out = os.path.abspath(args.out)
        os.makedirs(self.work, exist_ok=True)
        os.makedirs(self.out, exist_ok=True)
        self.result_path = os.path.join(self.out, "result.json")

    def result(self):
        return load_json(self.result_path, {}) or {}

    def save_result(self, res):
        save_json(self.result_path, res)

    def fail(self, res, stage, exc):
        res.setdefault("failures_and_recovery", []).append({
            "stage": stage, "time": now_iso(),
            "error": "%s: %s" % (type(exc).__name__, exc),
            "traceback_tail": traceback.format_exc()[-1500:],
            "recovery": "已记录，继续后续阶段；状态如实降级",
        })
        res["status"] = "blocked" if stage == "init" else res.get("status", "in_progress")
        self.save_result(res)

    def mark(self, res, stage):
        res.setdefault("change_records", []).append(
            {"stage": stage, "time": now_iso(), "note": "stage finished"})
        self.save_result(res)


def stage_init(ctx):
    res = ctx.result()
    res.setdefault("skill", "source-forensics-gate")
    res["status"] = "in_progress"
    res.setdefault("started_at", now_iso())
    res.setdefault("sources", [])
    res.setdefault("uncertainties", [])
    res.setdefault("change_records", [])
    res.setdefault("failures_and_recovery", [])

    case = {}
    case_path = os.path.join(ctx.input, "case.json")
    try:
        with open(case_path, "r", encoding="utf-8", errors="replace") as f:
            case = json.load(f)
    except FileNotFoundError:
        res["uncertainties"].append("缺少 /input/case.json，case_id 记为 unknown_case")
    except ValueError as exc:
        res["uncertainties"].append("case.json 解析失败（%s），case_id 记为 unknown_case" % exc)

    case_id = deep_find(case, {"case_id", "caseid", "id", "case"})
    if isinstance(case_id, (dict, list)):
        case_id = None
    res["case_id"] = str(case_id) if case_id else "unknown_case"
    if not case_id and "缺少 /input/case.json" not in " ".join(res["uncertainties"]):
        res["uncertainties"].append("case.json 中未找到 case_id 字段，记为 unknown_case")

    res["contract_fields"] = map_contract_fields(case)
    save_json(os.path.join(ctx.work, "case_parsed.json"),
              {"case_id": res["case_id"], "contract_fields": res["contract_fields"]})

    task_path = os.path.join(ctx.input, "task.md")
    try:
        with open(task_path, "r", encoding="utf-8", errors="replace") as f:
            task_text = f.read()
    except OSError:
        task_text = ""
        res["uncertainties"].append("缺少或不可读 /input/task.md")
    with open(os.path.join(ctx.work, "task_excerpt.txt"), "w", encoding="utf-8") as f:
        f.write(task_text[:8000])
    res["task_excerpt_path"] = os.path.join("work", "task_excerpt.txt")
    ctx.save_result(res)
    ctx.mark(res, "init")


def stage_scan(ctx):
    res = ctx.result()
    case = load_json(os.path.join(ctx.work, "case_parsed.json"), {}) or {}
    rels = collect_input_paths(ctx.input, case)
    records, skipped = [], []
    for rel in rels:
        full = os.path.join(ctx.input, rel)
        rec = {"path": rel, "size": None, "mtime": None, "sha256": None, "readable": True}
        try:
            st = os.stat(full)
            rec["size"] = st.st_size
            rec["mtime"] = st.st_mtime
            rec["mode"] = oct(st.st_mode & 0o777)
            rec["sha256"] = forensics.stream_sha256(full)
        except (PermissionError, UnicodeError, OSError) as exc:
            rec["readable"] = False
            rec["error"] = "%s: %s" % (type(exc).__name__, exc)
            skipped.append({"path": rel, "reason": rec["error"], "stage": "scan"})
        records.append(rec)
    save_json(os.path.join(ctx.work, "scan.json"),
              {"input_root": ctx.input, "file_count": len(records), "records": records})
    save_json(os.path.join(ctx.out, "skipped_and_conflicts.json"),
              {"skipped": skipped, "conflicts": []})
    res["sources"] = [r["path"] for r in records]
    ctx.save_result(res)
    ctx.mark(res, "scan")


def stage_forensics(ctx):
    res = ctx.result()
    scan = load_json(os.path.join(ctx.work, "scan.json"), {}) or {}
    rels = [r["path"] for r in scan.get("records", [])]
    report = forensics.forensic_tree(ctx.input, rels)
    report["generated_at"] = now_iso()
    save_json(os.path.join(ctx.work, "forensics_report.json"), report)
    save_json(os.path.join(ctx.out, "FORENSICS_REPORT.json"), report)
    bad = [r for r in report["records"] if r["verdict"] != "authentic"]
    for r in bad:
        res.setdefault("uncertainties", []).append(
            "取证判定 %s：%s（详见 FORENSICS_REPORT.json 证据字段）" % (r["verdict"], r["path"]))
    ctx.save_result(res)
    ctx.mark(res, "forensics")


def stage_plan(ctx):
    """去重（canonical=mtime 最早）+ 版本候选分组 + 目标路径规划。"""
    scan = load_json(os.path.join(ctx.work, "scan.json"), {}) or {}
    report = load_json(os.path.join(ctx.work, "forensics_report.json"), {}) or {}
    records = scan.get("records", [])
    by_path = {r["path"]: r for r in records}
    verdict = {r["path"]: r["verdict"] for r in report.get("records", [])}

    # 1) 内容哈希去重：canonical = mtime 最早（并列取路径字典序小者）
    groups = {}
    for r in records:
        if r.get("sha256"):
            groups.setdefault(r["sha256"], []).append(r["path"])
    duplicates, alias_of = [], {}
    for sha, paths in groups.items():
        paths.sort(key=lambda p: (by_path[p].get("mtime") or 0, nfc(p)))
        canonical = paths[0]
        aliases = paths[1:]
        for a in aliases:
            alias_of[a] = canonical
        if aliases:
            duplicates.append({"sha256": sha, "canonical": canonical,
                               "aliases": aliases,
                               "reason": "内容哈希一致；canonical 取 mtime 最早者"})
    duplicates.sort(key=lambda g: nfc(g["canonical"]))
    save_json(os.path.join(ctx.out, "duplicates.json"), {"groups": duplicates})

    # 2) 版本候选：规范化词干分组；内容不同 + mtime 排序连 supersedes 边
    stems = {}
    for r in records:
        stem = normalize_stem(os.path.basename(r["path"]))
        stems.setdefault(stem, []).append(r["path"])
    chains = []
    for stem, paths in sorted(stems.items()):
        distinct = {}
        for p in paths:
            sha = by_path[p].get("sha256") or p
            distinct.setdefault(sha, p)
        if len(paths) < 2 or len(distinct) < 2:
            continue
        ordered = sorted(paths, key=lambda p: (by_path[p].get("mtime") or 0, nfc(p)))
        edges = [{"from": ordered[i], "to": ordered[i + 1], "relation": "supersedes"}
                 for i in range(len(ordered) - 1)]
        chains.append({"stem": stem, "members": ordered,
                       "distinct_contents": len(distinct), "edges": edges})
    save_json(os.path.join(ctx.out, "version_chains.json"), {"chains": chains})
    stem_of = {p: normalize_stem(os.path.basename(p)) for r in records for p in [r["path"]]}

    # 3) 目标路径：verdict≠authentic → _quarantine/ 保留原相对路径；否则按桶
    plan = {}
    for r in records:
        p = r["path"]
        if p in alias_of:
            plan[p] = {"action": "alias", "canonical": alias_of[p], "target": None}
            continue
        v = verdict.get(p, "unreadable")
        if v != "authentic":
            target = os.path.join("library", "_quarantine", p)
        else:
            target = os.path.join("library", bucket_for(os.path.basename(p)),
                                  os.path.basename(p))
        plan[p] = {"action": "commit", "target": target, "verdict": v,
                   "version_stem": stem_of.get(p)}
    save_json(os.path.join(ctx.work, "plan.json"), {"plan": plan})
    res = ctx.result()
    ctx.save_result(res)
    ctx.mark(res, "plan")


def _resolve_conflict(ctx, target_rel, src_sha, conflicts):
    """目标已被不同内容占用时追加 __vN 后缀，绝不覆盖。"""
    base, ext = os.path.splitext(target_rel)
    n = 2
    cand = target_rel
    while True:
        full = os.path.join(ctx.out, cand)
        if not os.path.exists(full):
            return cand
        try:
            if forensics.stream_sha256(full) == src_sha:
                return cand  # 同内容，apply 会记 already_committed_identical
        except OSError:
            pass
        cand = "%s__v%d%s" % (base, n, ext)
        n += 1
        if n == 3:
            conflicts.append({"target": target_rel, "resolution": cand,
                              "reason": "目标路径被不同内容占用，追加 __vN 后缀，不覆盖"})


def stage_apply(ctx):
    res = ctx.result()
    scan = load_json(os.path.join(ctx.work, "scan.json"), {}) or {}
    report = load_json(os.path.join(ctx.work, "forensics_report.json"), {}) or {}
    plan = load_json(os.path.join(ctx.work, "plan.json"), {}) or {}
    dup = load_json(os.path.join(ctx.out, "duplicates.json"), {}) or {}
    by_path = {r["path"]: r for r in scan.get("records", [])}
    forensic_rec = {r["path"]: r for r in report.get("records", [])}
    journal_path = os.path.join(ctx.out, "operations_journal.jsonl")
    manifest_path = os.path.join(ctx.out, "LIBRARY_MANIFEST.jsonl")
    for p in (journal_path, manifest_path):
        if os.path.exists(p):
            os.remove(p)

    skc_path = os.path.join(ctx.out, "skipped_and_conflicts.json")
    skc = load_json(skc_path, {}) or {"skipped": [], "conflicts": []}
    skc.setdefault("skipped", [])
    skc["conflicts"] = []
    conflicts = skc["conflicts"]
    seq = 0
    stats = {"committed": 0, "already_committed_identical": 0, "alias": 0,
             "quarantined": 0, "copy_failed": 0}

    def jlog(obj):
        nonlocal seq
        seq += 1
        obj["seq"] = seq
        obj["time"] = now_iso()
        append_jsonl(journal_path, obj)

    # 先确定 canonical 的目标（含冲突消解），再处理 alias 行
    targets = {}
    for p, item in plan.get("plan", {}).items():
        if item["action"] != "commit":
            continue
        src_sha = by_path[p].get("sha256") or ""
        targets[p] = _resolve_conflict(ctx, item["target"], src_sha, conflicts)

    for p in sorted(plan.get("plan", {}), key=nfc):
        item = plan["plan"][p]
        fr = forensic_rec.get(p, {})
        src_sha = by_path[p].get("sha256")
        row = {
            "src": p, "target": None,
            "src_sha256": src_sha, "dst_sha256": None, "fixity_match": None,
            "forensic_verdict": fr.get("verdict"),
            "forensic_evidence": fr.get("evidence", {}),
            "alias_of": None, "version_stem": normalize_stem(os.path.basename(p)),
            "action": None, "copied": False,
        }
        if item["action"] == "alias":
            canonical = item["canonical"]
            row.update({"alias_of": canonical, "target": targets.get(canonical),
                        "action": "alias_recorded"})
            # alias 与 canonical 同内容：fixity 以 canonical 目标复核
            tgt_full = os.path.join(ctx.out, row["target"]) if row["target"] else None
            if tgt_full and os.path.isfile(tgt_full):
                row["dst_sha256"] = forensics.stream_sha256(tgt_full)
                row["fixity_match"] = (row["dst_sha256"] == src_sha)
            jlog({"stage": "apply", "action": "alias_recorded", "src": p,
                  "canonical": canonical, "status": "done"})
            stats["alias"] += 1
            append_jsonl(manifest_path, row)
            continue

        target = targets[p]
        row["target"] = target
        if target.startswith(os.path.join("library", "_quarantine")):
            stats["quarantined"] += 1
        tgt_full = os.path.join(ctx.out, target)
        src_full = os.path.join(ctx.input, p)
        try:
            if os.path.exists(tgt_full) and \
                    forensics.stream_sha256(tgt_full) == (src_sha or ""):
                row["action"] = "already_committed_identical"
                stats["already_committed_identical"] += 1
            else:
                os.makedirs(os.path.dirname(tgt_full), exist_ok=True)
                shutil.copy2(src_full, tgt_full)
                row["action"] = "committed"
                stats["committed"] += 1
            row["copied"] = True
            row["dst_sha256"] = forensics.stream_sha256(tgt_full)
            row["fixity_match"] = (row["dst_sha256"] == src_sha)
            jlog({"stage": "apply", "action": row["action"], "src": p,
                  "dst": target, "status": "done"})
        except (PermissionError, OSError) as exc:
            row["action"] = "copy_failed"
            row["error"] = "%s: %s" % (type(exc).__name__, exc)
            stats["copy_failed"] += 1
            skc["skipped"].append({"path": p, "stage": "apply",
                                   "reason": row["error"]})
            jlog({"stage": "apply", "action": "copy_failed", "src": p,
                  "status": "failed", "error": row["error"]})
        append_jsonl(manifest_path, row)

    jlog({"stage": "apply", "event": "stage_complete", "status": "done",
          "stats": stats})
    save_json(skc_path, skc)
    save_json(os.path.join(ctx.work, "apply_stats.json"), stats)
    ctx.save_result(res)
    ctx.mark(res, "apply")


def stage_verify(ctx):
    res = ctx.result()
    cmd = [sys.executable, VERIFY_SCRIPT, "--input", ctx.input, "--out", ctx.out]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        res.setdefault("failures_and_recovery", []).append({
            "stage": "verify", "time": now_iso(),
            "error": "verify_forensics exit=%d: %s" % (proc.returncode,
                                                       proc.stderr[-800:]),
            "recovery": "audit_report.json 可能缺失或含 FAIL，finalize 将如实降级",
        })
    ctx.save_result(res)
    ctx.mark(res, "verify")


def stage_finalize(ctx):
    res = ctx.result()
    audit = load_json(os.path.join(ctx.out, "audit_report.json"), {}) or {}
    stats = load_json(os.path.join(ctx.work, "apply_stats.json"), {}) or {}
    report = load_json(os.path.join(ctx.work, "forensics_report.json"), {}) or {}
    skc = load_json(os.path.join(ctx.out, "skipped_and_conflicts.json"), {}) or {}
    scan = load_json(os.path.join(ctx.work, "scan.json"), {}) or {}
    dup = load_json(os.path.join(ctx.out, "duplicates.json"), {}) or {}
    vc = load_json(os.path.join(ctx.out, "version_chains.json"), {}) or {}

    quarantined = [r["path"] for r in report.get("records", [])
                   if r.get("verdict") != "authentic"]
    audit_overall = audit.get("overall", "MISSING")
    audit_fails = [c["name"] for c in audit.get("checks", [])
                   if c.get("status") == "FAIL"]

    limits = []
    if audit_overall != "PASS":
        limits.append("audit 未全 PASS：overall=%s，FAIL 项=%s"
                      % (audit_overall, audit_fails or "audit_report 缺失"))
    if quarantined:
        limits.append("%d 个文件取证未通过，已隔离至 library/_quarantine/：%s"
                      % (len(quarantined), quarantined))
    if stats.get("copy_failed"):
        limits.append("%d 个文件复制失败（见 skipped_and_conflicts.json）"
                      % stats["copy_failed"])

    if res.get("status") == "blocked":
        pass  # init 阶段已失败，保持 blocked
    elif limits:
        res["status"] = "partial"
        res["limits"] = limits
    else:
        res["status"] = "complete"

    res["summary"] = {
        "input_files": scan.get("file_count", 0),
        "input_bytes": sum(r.get("size") or 0 for r in scan.get("records", [])),
        "verdict_counts": report.get("verdict_counts", {}),
        "quarantined": len(quarantined),
        "duplicate_groups": len(dup.get("groups", [])),
        "version_chains": len(vc.get("chains", [])),
        "skipped": len(skc.get("skipped", [])),
        "conflicts": len(skc.get("conflicts", [])),
        "audit_overall": audit_overall,
        "apply_stats": stats,
    }
    res["finished_at"] = now_iso()
    ctx.save_result(res)
    ctx.mark(res, "finalize")


def scaffold_qa_log(ctx):
    """从 task.md 提取检索/问题行，搭 QA_LOG 骨架（答案留待模型裁定）。"""
    task_path = os.path.join(ctx.work, "task_excerpt.txt")
    try:
        with open(task_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    q_pat = re.compile(r"[?？]|^(请|检索|查找|找出|回答|列出|统计|说明)")
    questions = [ln.strip() for ln in lines if ln.strip() and q_pat.search(ln.strip())]
    qa = {
        "note": "由 run_case.py 自动提取的候选问题；answer 需模型依据 library/ 证据填写，"
                "答不出必须保留 status=unanswered，不得编造。",
        "questions": [
            {"question": q, "answer": None, "evidence": [],
             "confidence": 0.0, "status": "unanswered_pending_model"}
            for q in questions
        ],
    }
    if not questions:
        qa["questions"] = []
        qa["note"] = "task.md 未包含可识别的检索/问题。"
    save_json(os.path.join(ctx.out, "QA_LOG.json"), qa)


STAGES = {
    "init": stage_init,
    "scan": stage_scan,
    "forensics": stage_forensics,
    "plan": stage_plan,
    "apply": stage_apply,
    "verify": stage_verify,
    "finalize": stage_finalize,
}
ALL_ORDER = ["init", "scan", "forensics", "plan", "apply", "verify", "finalize"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="source-forensics-gate 编排器")
    ap.add_argument("stage", choices=list(STAGES) + ["all"])
    ap.add_argument("--input", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    ctx = Ctx(args)

    stages = ALL_ORDER if args.stage == "all" else [args.stage]
    for name in stages:
        res = ctx.result()
        try:
            STAGES[name](ctx)
        except Exception as exc:  # 任何阶段崩溃：记录、降级、继续
            ctx.fail(res, name, exc)
    scaffold_qa_log(ctx)
    res = ctx.result()
    res.setdefault("status", "blocked")
    ctx.save_result(res)
    print("status=%s  result=%s" % (res.get("status"), ctx.result_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
