#!/usr/bin/env python3
"""run_case.py — run-ledger-audit 分阶段编排器（stdlib only）。

子命令：init / preflight / scan / plan / apply / replay / verify / finalize / all
统一参数：--input /input --work /app/work --out /app/output

阶段职责：
  init       防御式解析 case.json + task.md，立即写第一版 result.json（in_progress）
  preflight  输入盘点 + 磁盘余量 + 风险清单 → PREFLIGHT.json；磁盘不足 1.2× → blocked
  scan       流式 SHA-256 全量盘点 → 去重分组 duplicates.json、版本链 version_chains.json
  plan       计算目标路径（类别桶 + 冲突 __vN + 幂等 already_committed_identical）
  apply      WAL 两段式提交执行（journal_exec），先 reconcile 再复制 → library/ +
             LIBRARY_MANIFEST.jsonl + operations_journal.jsonl + skipped_and_conflicts.json
  replay     子进程 replay.py：仅凭 journal 复放，产物在 work/replay，REPLAY_DIFF.json 进 output
  verify     子进程 audit_run.py：独立审计 → AUDIT_REPORT.json
  finalize   折叠 AUDIT + REPLAY_DIFF + QA 进 result.json 的 status 与 summary

任何阶段异常都记入 result.json 的 failures_and_recovery 并继续，绝不丢 result.json。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import journal_exec  # noqa: E402  (同目录脚本，非其他 bundle)

EXCLUDE_INPUT = {"case.json", "task.md"}
BUCKETS = ["papers", "data", "scans", "supplementary", "drafts", "admin", "_unassigned"]
BIG_FILE = 100 * 1024 * 1024       # 100MB 风险阈值
MAX_DEPTH = 8                      # 目录深度风险阈值
DISK_MARGIN = 1.2                  # 磁盘余量安全系数
CORRUPT_MARKER = "X-SIMULATED-CORRUPT"

CONTRACT_MAP = [
    (("manifest", "清单"), "LIBRARY_MANIFEST.jsonl"),
    (("journal", "ledger", "日志"), "operations_journal.jsonl"),
    (("audit", "审计"), "AUDIT_REPORT.json"),
    (("replay", "复跑", "复放"), "REPLAY_DIFF.json"),
    (("duplicat", "重复"), "duplicates.json"),
    (("version", "版本"), "version_chains.json"),
    (("skip", "conflict", "跳过", "冲突"), "skipped_and_conflicts.json"),
    (("preflight", "预检"), "PREFLIGHT.json"),
    (("qa", "question", "answer", "问答", "检索"), "QA_LOG.json"),
    (("library", "资料库", "文库"), "library/"),
    (("result",), "result.json"),
]


# ---------- 小工具 ----------

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def nfc(s):
    return unicodedata.normalize("NFC", s)


def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def rel_depth(rel):
    return len([p for p in rel.replace("\\", "/").split("/") if p])


def is_special_name(name):
    if nfc(name) != name:
        return True
    if name != name.strip() or name.endswith("."):
        return True
    return any(ord(c) < 32 or c in ':*?"<>|' for c in name)


def find_keys(obj, names, hits):
    """递归在任意 JSON 结构里找指定键（大小写不敏感）。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in names:
                hits.append(v)
            find_keys(v, names, hits)
    elif isinstance(obj, list):
        for v in obj:
            find_keys(v, names, hits)


def collect_strings(obj, acc):
    if isinstance(obj, str):
        acc.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_strings(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            collect_strings(v, acc)


def contract_mirror(fields, out_dir):
    """output_contract 字段 → 交付物相对路径镜像；映射不了如实给 null + reason。"""
    mirror = {}
    for f in fields:
        key = str(f)
        low = key.lower()
        path = None
        for kws, p in CONTRACT_MAP:
            if any(k in low for k in kws):
                path = p
                break
        if path is None:
            mirror[key] = {"value": None,
                           "reason": "output_contract 字段未映射到本 skill 交付物，"
                                     "请核对 task.md 是否另有约定"}
        else:
            mirror[key] = {"path": path,
                           "present": os.path.exists(os.path.join(out_dir, path))}
    return mirror


# ---------- 上下文 ----------

class Ctx:
    def __init__(self, input_dir, work_dir, out_dir):
        self.input = os.path.abspath(input_dir)
        self.work = os.path.abspath(work_dir)
        self.out = os.path.abspath(out_dir)
        os.makedirs(self.work, exist_ok=True)
        os.makedirs(self.out, exist_ok=True)
        self.staging = os.path.join(self.work, "staging")

    def w(self, *p):
        return os.path.join(self.work, *p)

    def o(self, *p):
        return os.path.join(self.out, *p)

    def load_result(self):
        r = read_json(self.o("result.json"))
        if not r:
            r = {"case_id": "unknown_case", "status": "in_progress",
                 "skill": "run-ledger-audit", "created_at": utc_now(),
                 "contract_fields": {}, "sources": [], "uncertainties": [],
                 "change_records": [], "failures_and_recovery": [], "summary": {}}
        return r

    def save_result(self, r):
        r["updated_at"] = utc_now()
        write_json(self.o("result.json"), r)

    def fail(self, r, stage, exc):
        r.setdefault("failures_and_recovery", []).append(
            {"stage": stage, "error": str(exc), "at": utc_now(),
             "recovery": "异常已捕获，继续后续阶段，status 如实降级"})


# ---------- 输入遍历（preflight 与 scan 共用） ----------

def iter_input_files(ctx):
    """产出 (rel_nfc, abspath)；顶层 case.json/task.md 排除；错误记入 skipped。"""
    items, skipped = [], []
    for root, dirs, files in os.walk(ctx.input):
        dirs.sort()
        for name in sorted(files):
            if os.path.abspath(root) == ctx.input and name in EXCLUDE_INPUT:
                continue
            ap = os.path.join(root, name)
            rel = nfc(os.path.relpath(ap, ctx.input))
            items.append((rel, ap))
    # case.json 引用的 /input 之外路径：不复制，如实记 skipped（写 /input 之外同样禁止）
    case = read_json(os.path.join(ctx.input, "case.json")) or {}
    strs = []
    collect_strings(case, strs)
    for s in strs:
        if os.path.isabs(s) and os.path.isfile(s) and \
                not os.path.abspath(s).startswith(ctx.input + os.sep):
            skipped.append({"path": s, "reason": "case.json 引用了 /input 之外的路径，"
                                                 "按安全规则不复制，请人工确认"})
    items.sort(key=lambda x: x[0])
    return items, skipped


# ---------- 阶段：init ----------

def stage_init(ctx):
    r = ctx.load_result()
    r["status"] = "in_progress"
    case_path = os.path.join(ctx.input, "case.json")
    case = read_json(case_path)
    if case is None:
        r["case_id"] = "unknown_case"
        r.setdefault("uncertainties", []).append("case.json 缺失或不可解析，case_id 记为 unknown_case")
        case = {}
    hits = []
    find_keys(case, {"case_id", "caseid", "id", "case"}, hits)
    cid = None
    for h in hits:
        if isinstance(h, (str, int)):
            cid = str(h)
            break
    if cid:
        r["case_id"] = cid
    elif r.get("case_id") in (None, "unknown_case"):
        r["case_id"] = "unknown_case"
        r.setdefault("uncertainties", []).append("case.json 中未找到 case_id 字段")

    hits = []
    find_keys(case, {"output_contract", "contract", "output_fields", "required_fields",
                     "outputs", "result_fields"}, hits)
    fields = []
    for h in hits:
        if isinstance(h, dict):
            fields.extend(str(k) for k in h.keys())
        elif isinstance(h, list):
            fields.extend(str(x) for x in h if isinstance(x, (str, int)))
        elif isinstance(h, str):
            fields.append(h)
    seen, fields_u = set(), []
    for f in fields:
        if f not in seen:
            seen.add(f)
            fields_u.append(f)
    r["contract_fields"] = contract_mirror(fields_u, ctx.out)
    r["output_contract_fields"] = fields_u

    task_path = os.path.join(ctx.input, "task.md")
    task = ""
    try:
        with open(task_path, "r", encoding="utf-8", errors="replace") as f:
            task = f.read()
    except OSError:
        r.setdefault("uncertainties", []).append("task.md 缺失或不可读")
    with open(ctx.w("task_excerpt.txt"), "w", encoding="utf-8") as f:
        f.write(task[:8000])
    r["sources"] = sorted({"case.json" if case else None, "task.md" if task else None,
                           "input_files"} - {None})

    # task.md 中的检索/问题 → QA_LOG.json（保留既有作答）
    questions = [ln.strip() for ln in task.splitlines()
                 if ("?" in ln or "？" in ln) and ln.strip()]
    if questions:
        qa_path = ctx.o("QA_LOG.json")
        qa = read_json(qa_path) or {"note": "task.md 检索/问题作答记录", "items": []}
        known = {it.get("question") for it in qa.get("items", [])}
        for q in questions:
            if q not in known:
                qa.setdefault("items", []).append(
                    {"question": q, "answer": None, "evidence_paths": [],
                     "status": "pending_model_answer"})
        write_json(qa_path, qa)
        r.setdefault("uncertainties", []).append(
            "task.md 含 %d 个检索/问题，待模型作答写入 QA_LOG.json 后重跑 finalize" % len(questions))
    ctx.save_result(r)
    return r


# ---------- 阶段：preflight ----------

def stage_preflight(ctx):
    r = ctx.load_result()
    items, skipped = iter_input_files(ctx)
    total = 0
    nfiles = 0
    depth_dist = {}
    unreadable, risks = [], []
    for rel, ap in items:
        depth = rel_depth(rel)
        depth_dist[str(depth)] = depth_dist.get(str(depth), 0) + 1
        try:
            size = os.path.getsize(ap)
            with open(ap, "rb") as f:
                f.read(1)
        except (OSError, PermissionError) as e:
            unreadable.append({"path": rel, "error": str(e)})
            continue
        nfiles += 1
        total += size
        if size > BIG_FILE:
            risks.append({"path": rel, "risk": "file_gt_100MB", "bytes": size})
        if depth > MAX_DEPTH:
            risks.append({"path": rel, "risk": "depth_gt_8", "depth": depth})
        if any(is_special_name(p) for p in rel.replace("\\", "/").split("/")):
            risks.append({"path": rel, "risk": "special_chars_in_name"})
    usage = shutil.disk_usage(ctx.work)
    need = int(total * DISK_MARGIN)
    ok = usage.free >= need
    pre = {"preflight": "run-ledger-audit PREFLIGHT", "generated_at": utc_now(),
           "status": "ok" if ok else "blocked",
           "inventory": {"file_count": nfiles, "total_bytes": total,
                         "depth_distribution": depth_dist, "unreadable": unreadable},
           "disk": {"total": usage.total, "used": usage.used, "free": usage.free,
                    "required_with_margin": need, "margin": DISK_MARGIN},
           "estimated_ops": nfiles,
           "risks": risks,
           "external_paths_not_copied": skipped,
           "blocking_reason": None if ok else
               "磁盘余量 %d 字节 < 预计写入 %d 字节（总量×%.1f），为避免半截复制而阻断"
               % (usage.free, need, DISK_MARGIN)}
    write_json(ctx.o("PREFLIGHT.json"), pre)
    r["preflight_status"] = pre["status"]
    if not ok:
        r["status"] = "blocked"
        r.setdefault("uncertainties", []).append(pre["blocking_reason"])
    ctx.save_result(r)
    return ok


# ---------- 阶段：scan ----------

def norm_stem(name):
    """规范化词干：去扩展名、NFC、小写、循环剥离版本/定稿/日期/副本后缀。"""
    s = name.rsplit(".", 1)[0] if "." in name else name
    s = nfc(s).lower()
    pat = re.compile(r"[_\-\s（(]*(v\d+|final|最终版|定稿|终稿|最新版|修订版|修改版|"
                     r"rev\d*|copy|副本|\d{8}|\d{4}[-_年]\d{1,2}[-_月]\d{1,2}日?)[)）]?$")
    prev = None
    while prev != s:
        prev = s
        s = pat.sub("", s)
    return re.sub(r"[_\-\s（）()]+", "", s)


def classify(name):
    """类别桶规则（task.md 约定优先；此处为缺省）。返回 BUCKETS 之一。"""
    low = nfc(name).lower()
    stem = low.rsplit(".", 1)[0] if "." in low else low
    ext = low.rsplit(".", 1)[1] if "." in low else ""
    if re.search(r"(行政|备注|通知|memo|admin|notice|采购|报销)", low):
        return "admin"
    if re.search(r"(草稿|draft|最终版|定稿|终稿|_v\d+$|_final)", stem):
        return "drafts"
    if ext in ("csv", "tsv", "json", "jsonl", "xlsx", "xml") or "metadata" in low \
            or re.search(r"(数据|观测|记录表)", low):
        return "data"
    if re.search(r"(scan|扫描|发票|收据|票据)", low) or ext in ("png", "jpg", "jpeg", "tif", "tiff"):
        return "scans"
    if re.search(r"(supp|补充|附录|appendix|附件)", low):
        return "supplementary"
    if re.search(r"(paper|论文|文献|report|报告|综述|article)", low) or ext in ("pdf", "doc", "docx"):
        return "papers"
    return "_unassigned"


def stage_scan(ctx):
    r = ctx.load_result()
    items, skipped_ext = iter_input_files(ctx)
    inv = []
    skipped = list(skipped_ext)
    for rel, ap in items:
        ent = {"path": rel, "bytes": None, "sha256": None, "mtime": None}
        try:
            st = os.stat(ap)
            ent["bytes"] = st.st_size
            ent["mtime"] = datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds")
            ent["sha256"] = journal_exec.sha256_file(ap)
            with open(ap, "rb") as f:
                head = f.read(256).decode("utf-8", errors="replace")
            if CORRUPT_MARKER in head:
                ent["quarantine"] = "simulated_corrupt_marker"
        except (OSError, PermissionError) as e:
            ent["error"] = str(e)
            skipped.append({"path": rel, "reason": "unreadable: %s" % e})
        inv.append(ent)
    write_json(ctx.w("inventory.json"), {"files": inv, "skipped": skipped})

    good = [e for e in inv if e.get("sha256")]
    by_hash = {}
    for e in good:
        by_hash.setdefault(e["sha256"], []).append(e["path"])
    groups = []
    for sha, paths in sorted(by_hash.items()):
        if len(paths) > 1:
            paths = sorted(paths)
            groups.append({"sha256": sha,
                           "bytes": next(e["bytes"] for e in good if e["path"] == paths[0]),
                           "canonical": paths[0], "aliases": paths[1:],
                           "members": paths})
    write_json(ctx.o("duplicates.json"),
               {"note": "按内容 SHA-256 去重分组；canonical 为字典序最前者，aliases 为同内容别名",
                "group_count": len(groups), "groups": groups})

    by_stem = {}
    for e in good:
        key = (norm_stem(os.path.basename(e["path"])),
               e["path"].rsplit(".", 1)[-1].lower() if "." in e["path"] else "")
        by_stem.setdefault(key, []).append(e)
    chains = []
    for (stem, ext), ents in sorted(by_stem.items()):
        shas = {e["sha256"] for e in ents}
        if len(ents) >= 2 and len(shas) >= 2:
            ents_s = sorted(ents, key=lambda e: (e.get("mtime") or "", e["path"]))
            chains.append({"stem": stem, "ext": ext,
                           "members": [e["path"] for e in ents_s],
                           "distinct_hashes": len(shas),
                           "latest_by_mtime": ents_s[-1]["path"],
                           "note": "词干相同但内容不同 → 版本候选链；latest_by_mtime 仅为推断，"
                                   "以 task.md 或行政备注约定为准"})
    write_json(ctx.o("version_chains.json"),
               {"note": "按规范化词干聚类的版本候选链（内容不同的同名族）",
                "chain_count": len(chains), "chains": chains})
    r["summary"].update({"input_files": len(inv),
                         "unreadable_or_skipped": len(skipped),
                         "duplicate_groups": len(groups),
                         "version_chains": len(chains)})
    ctx.save_result(r)


# ---------- 阶段：plan ----------

def compute_plan(ctx):
    inv = read_json(ctx.w("inventory.json")) or {"files": [], "skipped": []}
    dups = read_json(ctx.o("duplicates.json")) or {"groups": []}
    alias_of = {}
    for g in dups.get("groups", []):
        for a in g.get("aliases", []):
            alias_of[a] = g["canonical"]
    plan, conflicts, skipped = [], [], list(inv.get("skipped", []))
    used = {}  # dst_rel -> src sha256（本计划内）
    for e in inv["files"]:
        rel, sha = e["path"], e.get("sha256")
        name = os.path.basename(rel)
        if e.get("error"):
            skipped.append({"path": rel, "reason": "unreadable: %s" % e["error"]})
            continue
        if e.get("quarantine"):
            plan.append({"src": rel, "dst": None, "sha256": sha, "bytes": e.get("bytes"),
                         "action": "skipped_simulated_corrupt",
                         "reason": "文件含 %s 标记，按隔离规则不复制" % CORRUPT_MARKER})
            skipped.append({"path": rel, "reason": "simulated_corrupt_marker"})
            continue
        if rel in alias_of:
            canon = alias_of[rel]
            plan.append({"src": rel, "dst": None, "sha256": sha, "bytes": e.get("bytes"),
                         "action": "duplicate_alias", "canonical": canon,
                         "reason": "内容与 %s 完全相同（SHA-256 一致），不重复入库" % canon})
            continue

        bucket = classify(name)
        dst = "library/%s/%s" % (bucket, name)
        existing = ctx.o(dst)
        if os.path.exists(existing):
            try:
                ex_sha = journal_exec.sha256_file(existing)
            except OSError:
                ex_sha = None
            if ex_sha == sha:
                plan.append({"src": rel, "dst": dst, "sha256": sha, "bytes": e.get("bytes"),
                             "action": "already_committed_identical",
                             "reason": "目标已存在且内容一致，幂等跳过（不追加 journal）"})
                continue
            base, dot, ext = name.rpartition(".")
            n = 2
            while True:
                cand_name = "%s__v%d%s%s" % (base or name, n, "." if dot else "", ext if dot else "")
                cand = "library/%s/%s" % (bucket, cand_name)
                if not os.path.exists(ctx.o(cand)) and cand not in used:
                    conflicts.append({"src": rel, "original_dst": dst, "renamed_to": cand,
                                      "reason": "目标已被不同内容占用，自动 __vN，不覆盖"})
                    dst = cand
                    break
                n += 1
        if dst in used and used[dst] != sha:
            base, dot, ext = name.rpartition(".")
            n = 2
            while True:
                cand = "library/%s/%s__v%d%s%s" % (bucket, base or name, n,
                                                   "." if dot else "", ext if dot else "")
                if cand not in used and not os.path.exists(ctx.o(cand)):
                    conflicts.append({"src": rel, "original_dst": dst, "renamed_to": cand,
                                      "reason": "计划内目标重名且内容不同，自动 __vN"})
                    dst = cand
                    break
                n += 1
        used[dst] = sha
        plan.append({"src": rel, "dst": dst, "sha256": sha, "bytes": e.get("bytes"),
                     "action": "commit"})
    # 别名记录回指 canonical 的实际 dst（去向必须显式，审计 A 项要求）
    dst_of = {p["src"]: p["dst"] for p in plan
              if p["action"] in ("commit", "already_committed_identical") and p.get("dst")}
    for p in plan:
        if p["action"] == "duplicate_alias":
            p["dst"] = dst_of.get(p["canonical"])
    return {"generated_at": utc_now(), "plan": plan,
            "conflicts": conflicts, "skipped": skipped}


def stage_plan(ctx):
    plan_doc = compute_plan(ctx)
    write_json(ctx.w("plan.json"), plan_doc)
    r = ctx.load_result()
    r["summary"]["planned_commits"] = sum(1 for p in plan_doc["plan"] if p["action"] == "commit")
    r["summary"]["conflicts"] = len(plan_doc["conflicts"])
    ctx.save_result(r)


# ---------- 阶段：apply ----------

def stage_apply(ctx):
    j = journal_exec.Journal(ctx.o("operations_journal.jsonl"))
    n_reconciled = journal_exec.reconcile(j, ctx.staging)
    plan_doc = read_json(ctx.w("plan.json")) or compute_plan(ctx)
    plan = plan_doc["plan"]
    manifest, change_records = [], []
    counter = 0
    for p in plan:
        line = {"src": p["src"], "dst": p.get("dst"), "sha256": p.get("sha256"),
                "bytes": p.get("bytes"), "action": p["action"]}
        if p.get("reason"):
            line["reason"] = p["reason"]
        if p.get("canonical"):
            line["canonical"] = p["canonical"]
        if p["action"] == "commit":
            # 幂等护栏：即便 plan.json 陈旧，dst 已存在且内容一致也直接跳过，不追加 journal
            dst_abs = ctx.o(p["dst"])
            if os.path.exists(dst_abs) and p.get("sha256"):
                try:
                    if journal_exec.sha256_file(dst_abs) == p["sha256"]:
                        line["action"] = "already_committed_identical"
                        line["reason"] = "apply 时检测到目标已存在且内容一致，幂等跳过"
                        line["journal_done_seq"] = j.done_seq_for(p["dst"])
                        manifest.append(line)
                        change_records.append({"src": p["src"], "dst": p.get("dst"),
                                               "action": line["action"]})
                        continue
                except OSError:
                    pass
            counter += 1
            op_id = "op%04d" % counter
            ok, done = journal_exec.copy_with_wal(
                j, op_id, os.path.join(ctx.input, p["src"]),
                ctx.o(p["dst"]), ctx.staging, src_rel=p["src"], dst_rel=p["dst"])
            if ok:
                line["action"] = "committed"
                line["journal_done_seq"] = done.get("seq")
            else:
                line["action"] = "failed"
                line["reason"] = "WAL 提交失败，详见 operations_journal.jsonl 中 id=%s" % op_id
        elif p["action"] == "already_committed_identical":
            line["journal_done_seq"] = j.done_seq_for(p["dst"])
        manifest.append(line)
        change_records.append({"src": p["src"], "dst": p.get("dst"),
                               "action": line["action"]})
    with open(ctx.o("LIBRARY_MANIFEST.jsonl"), "w", encoding="utf-8") as f:
        for m in manifest:
            f.write(json.dumps(m, ensure_ascii=False, sort_keys=True) + "\n")
    sk_conf = {"generated_at": utc_now(),
               "reconciled_at_apply_start": n_reconciled,
               "skipped": plan_doc.get("skipped", []) +
                          [m for m in manifest if m["action"] in
                           ("skipped_simulated_corrupt", "failed")],
               "conflicts": plan_doc.get("conflicts", [])}
    write_json(ctx.o("skipped_and_conflicts.json"), sk_conf)
    r = ctx.load_result()
    r["change_records"] = change_records
    stats = {"begin": 0, "done": 0, "failed": 0, "reconciled": 0}
    for rec in j.records:
        if rec.get("op") in stats:
            stats[rec["op"]] += 1
    r["summary"]["journal_stats"] = stats
    r["summary"]["library_files"] = sum(1 for m in manifest
                                        if m["action"] in ("committed", "already_committed_identical"))
    ctx.save_result(r)


# ---------- 阶段：replay / verify（子进程） ----------

def stage_replay(ctx):
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, "replay.py"),
           "--journal", ctx.o("operations_journal.jsonl"),
           "--input", ctx.input,
           "--out", ctx.w("replay"),
           "--library", ctx.o("library"),
           "--diff-out", ctx.o("REPLAY_DIFF.json")]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    r = ctx.load_result()
    r["summary"]["replay_exit_code"] = proc.returncode
    if proc.returncode not in (0, 1):
        r["failures_and_recovery"].append(
            {"stage": "replay", "error": (proc.stderr or proc.stdout)[-500:],
             "at": utc_now(), "recovery": "REPLAY_DIFF.json 可能缺失，finalize 将如实降级"})
    ctx.save_result(r)
    return proc.returncode


def stage_verify(ctx):
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, "audit_run.py"),
           "--input", ctx.input, "--out", ctx.out]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    r = ctx.load_result()
    r["summary"]["audit_exit_code"] = proc.returncode
    if proc.returncode not in (0, 1):
        r["failures_and_recovery"].append(
            {"stage": "verify", "error": (proc.stderr or proc.stdout)[-500:],
             "at": utc_now(), "recovery": "AUDIT_REPORT.json 可能缺失，finalize 将如实降级"})
    ctx.save_result(r)
    return proc.returncode


# ---------- 阶段：finalize ----------

def stage_finalize(ctx):
    r = ctx.load_result()
    audit = read_json(ctx.o("AUDIT_REPORT.json")) or {}
    replay = read_json(ctx.o("REPLAY_DIFF.json")) or {}
    qa = read_json(ctx.o("QA_LOG.json")) or {}
    limits = []
    if r.get("preflight_status") == "blocked":
        r["status"] = "blocked"
        limits.append("preflight 阻断：磁盘余量不足或输入不可盘点，未执行整理")
    else:
        if audit.get("overall") != "PASS":
            limits.append("AUDIT_REPORT.json 未全 PASS：%s" %
                          {c["id"]: c["status"] for c in audit.get("checks", [])} or "审计缺失")
        if not replay.get("equal", False):
            limits.append("REPLAY_DIFF.json 非空：仅凭 journal 未能完整复现 library/")
        qa_pending = [it for it in qa.get("items", []) if not it.get("answer")]
        if qa_pending:
            limits.append("QA_LOG.json 有 %d 个检索/问题未作答" % len(qa_pending))
        if any(m.get("action") == "failed" for m in r.get("change_records", [])):
            limits.append("存在 failed 的复制操作（见 operations_journal.jsonl）")
        r["status"] = "complete" if not limits else "partial"
    if limits:
        r["limits"] = limits
    elif "limits" in r:
        del r["limits"]
    r["contract_fields"] = contract_mirror(r.get("output_contract_fields", []), ctx.out)
    s = r.setdefault("summary", {})
    s["audit_overall"] = audit.get("overall")
    s["replay_equal"] = replay.get("equal")
    s["finalized_at"] = utc_now()
    ctx.save_result(r)
    return r["status"]


# ---------- 编排 ----------

STAGES = {"init": stage_init, "preflight": stage_preflight, "scan": stage_scan,
          "plan": stage_plan, "apply": stage_apply, "replay": stage_replay,
          "verify": stage_verify, "finalize": stage_finalize}
ALL_ORDER = ["init", "preflight", "scan", "plan", "apply", "replay", "verify", "finalize"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="run-ledger-audit 编排器")
    ap.add_argument("cmd", choices=list(STAGES) + ["all"])
    ap.add_argument("--input", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    ctx = Ctx(a.input, a.work, a.out)
    cmds = ALL_ORDER if a.cmd == "all" else [a.cmd]
    for c in cmds:
        r = ctx.load_result()
        if r.get("status") == "blocked" and c not in ("finalize",):
            continue  # 已阻断：跳到 finalize 收尾
        try:
            STAGES[c](ctx)
        except Exception as e:  # 任何阶段异常都不许吞掉 result.json
            r = ctx.load_result()
            ctx.fail(r, c, e)
            ctx.save_result(r)
    r = ctx.load_result()
    print(json.dumps({"status": r.get("status"), "case_id": r.get("case_id"),
                      "summary": r.get("summary", {})}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
