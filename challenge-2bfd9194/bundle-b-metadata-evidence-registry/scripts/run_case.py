#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_case.py — metadata-evidence-registry 分阶段编排器（仅标准库）。

子命令：init / scan / extract / plan / apply / verify / finalize / all
统一参数：--input /input --work /app/work --out /app/output

阶段契约（详见 SKILL.md 与 SPEC）：
  init     防御式解析 case.json/task.md，数秒内写出第一版 result.json(in_progress)
  scan     递归盘点：SHA-256(64KB 流式)、字节、mtime、NFC 相对路径；错误入 skipped 绝不崩溃
  extract  四级来源元数据抽取与裁定（registry.py），写 registry/conflicts/coverage
  plan     目标路由（task.md 模板优先，缺省类别桶）、去重、版本链、__vN 预分配
  apply    复制落库（不移动），写 manifest / journal / skipped_and_conflicts；幂等
  verify   子进程跑独立校验器 verify_registry.py -> audit_report.json
  finalize 折进 result.json：全 PASS 且无未决项 -> complete，否则 partial/blocked

任何阶段异常都记入 failures_and_recovery 并继续；任何情况下都保留 result.json。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import registry  # noqa: E402  (同目录脚本，bundle 内部依赖)

DEFAULT_BUCKETS = ["papers", "data", "scans", "supplementary", "drafts", "admin",
                   "_unassigned"]
CONTRACT_MAP = {
    "metadata_registry": "metadata_registry.jsonl",
    "registry": "metadata_registry.jsonl",
    "library_manifest": "LIBRARY_MANIFEST.jsonl",
    "manifest": "LIBRARY_MANIFEST.jsonl",
    "library": "library/",
    "coverage_report": "coverage_report.json",
    "coverage": "coverage_report.json",
    "audit_report": "audit_report.json",
    "audit": "audit_report.json",
    "conflicts": "conflicts.json",
    "conflict_matrix": "conflicts.json",
    "duplicates": "duplicates.json",
    "version_chains": "version_chains.json",
    "operations_journal": "operations_journal.jsonl",
    "journal": "operations_journal.jsonl",
    "skipped_and_conflicts": "skipped_and_conflicts.json",
    "skipped": "skipped_and_conflicts.json",
    "qa_log": "QA_LOG.json",
    "result": "result.json",
    "result_json": "result.json",
}


# ---------------------------------------------------------------- 小工具
def nfc(s):
    return unicodedata.normalize("NFC", s)


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def jdump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def jload(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def sha256_file(path, chunk=65536):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def find_keys(obj, names, out):
    """递归收集 case.json 中 names 键的值。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k in names:
                out.append(v)
            find_keys(v, names, out)
    elif isinstance(obj, list):
        for v in obj:
            find_keys(v, names, out)


def sanitize_path_token(s):
    s = re.sub(r"[\\/:*?\"<>|]", "_", str(s))
    s = re.sub(r"\s+", "_", s).strip("._ ")
    return s or ""


class Ctx:
    def __init__(self, args):
        self.input = os.path.abspath(args.input)
        self.work = os.path.abspath(args.work)
        self.out = os.path.abspath(args.out)
        for d in (self.work, self.out):
            os.makedirs(d, exist_ok=True)
        self.result_path = os.path.join(self.out, "result.json")
        self.result = jload(self.result_path) or {}

    # -- 阶段守卫 -----------------------------------------------------
    def stage(self, name, fn):
        try:
            fn(self)
        except Exception as e:  # 绝不崩溃；记录并继续
            fr = self.result.setdefault("failures_and_recovery", [])
            fr.append({"stage": name, "error": "%s: %s" % (type(e).__name__, e),
                       "recovery": "已捕获并继续后续阶段", "ts": now()})
            self.result["status"] = "partial"
            self.save_result()

    def save_result(self):
        self.result["updated_at"] = now()
        jdump(self.result, self.result_path)

    def journal(self, entry):
        entry = dict(entry)
        entry["ts"] = now()
        with open(os.path.join(self.out, "operations_journal.jsonl"), "a",
                  encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- init
def phase_init(ctx):
    case = jload(os.path.join(ctx.input, "case.json")) or {}
    if not isinstance(case, dict):
        case = {}
    ids = []
    find_keys(case, {"case_id", "caseId", "id", "case"}, ids)
    case_id = next((str(x) for x in ids if isinstance(x, (str, int))), None)
    uncertainties = []
    if not case_id:
        case_id = "unknown_case"
        uncertainties.append("case.json 中未找到 case_id/caseId/id/case，记为 unknown_case")

    contracts = []
    find_keys(case, {"output_contract", "contract", "output_fields",
                     "required_fields", "outputs", "result_fields"}, contracts)
    field_names = []
    for c in contracts:
        if isinstance(c, str):
            field_names.append(c)
        elif isinstance(c, list):
            field_names += [x for x in c if isinstance(x, str)]
        elif isinstance(c, dict):
            field_names += [k for k in c if isinstance(k, str)]
    field_names = sorted(set(field_names))
    contract_fields = {}
    for name in field_names:
        path = CONTRACT_MAP.get(name.lower()) or \
            CONTRACT_MAP.get(re.sub(r"[^a-z_]", "", name.lower().replace("-", "_")))
        if path:
            contract_fields[name] = {"path": path, "status": "pending"}
        else:
            contract_fields[name] = {"value": None,
                                     "reason": "未识别的契约字段，无对应交付物映射"}

    # 扩展元数据字段（防御式合并）
    extra = []
    find_keys(case, {"metadata_fields", "extra_fields", "fields"}, extra)
    extra_fields = []
    for e in extra:
        if isinstance(e, list):
            extra_fields += [x for x in e if isinstance(x, str)]

    task_text = ""
    try:
        with open(os.path.join(ctx.input, "task.md"), "rb") as fh:
            task_text = fh.read().decode("utf-8", errors="replace")
    except OSError:
        uncertainties.append("未找到可读的 task.md；使用缺省流程与缺省类别桶")
    with open(os.path.join(ctx.work, "task_excerpt.txt"), "w", encoding="utf-8") as fh:
        fh.write(task_text[:8192])

    ctx.result = {
        "case_id": case_id,
        "skill": "metadata-evidence-registry",
        "status": "in_progress",
        "created_at": now(),
        "contract_fields": contract_fields,
        "contract_field_names": field_names,
        "extra_metadata_fields": sorted(set(extra_fields)),
        "task_md_present": bool(task_text),
        "sources": [],
        "uncertainties": uncertainties,
        "change_records": [{"stage": "init", "ts": now(),
                            "detail": "防御式解析 case.json/task.md 完成"}],
        "failures_and_recovery": [],
        "summary": {},
    }
    ctx.save_result()


# ---------------------------------------------------------------- scan
def phase_scan(ctx):
    entries, skipped = [], []
    exclude = {"case.json", "task.md"}
    for root, dirs, names in os.walk(ctx.input):
        dirs.sort()
        for name in sorted(names):
            full = os.path.join(root, name)
            rel = nfc(os.path.relpath(full, ctx.input))
            if rel in exclude:
                continue
            try:
                st = os.stat(full)
                digest = sha256_file(full)
                entries.append({"rel": rel, "sha256": digest, "bytes": st.st_size,
                                "mtime": st.st_mtime, "readable": True})
            except PermissionError as e:
                skipped.append({"rel": rel, "error": "PermissionError: %s" % e})
            except (OSError, UnicodeError) as e:
                skipped.append({"rel": rel, "error": "%s: %s" % (type(e).__name__, e)})
    entries.sort(key=lambda e: e["rel"])

    # case.json 中引用的外部路径（若存在且在 /input 之外）
    case = jload(os.path.join(ctx.input, "case.json")) or {}
    strs = []
    find_keys(case, {"path", "file", "filepath", "source"}, strs)
    for s in strs:
        if isinstance(s, str) and os.path.isabs(s) and os.path.isfile(s) \
                and not s.startswith(ctx.input):
            try:
                st = os.stat(s)
                entries.append({"rel": nfc("_external/" + os.path.basename(s)),
                                "sha256": sha256_file(s), "bytes": st.st_size,
                                "mtime": st.st_mtime, "readable": True,
                                "external_path": s})
            except OSError as e:
                skipped.append({"rel": s, "error": "%s: %s" % (type(e).__name__, e)})
    entries.sort(key=lambda e: e["rel"])

    groups = {}
    for e in entries:
        groups.setdefault(e["sha256"], []).append(e["rel"])
    duplicates = [{"sha256": h, "files": sorted(fs), "canonical": sorted(fs)[0]}
                  for h, fs in sorted(groups.items()) if len(fs) > 1]

    jdump({"files": entries, "skipped": skipped},
          os.path.join(ctx.work, "scan_index.json"))
    jdump({"duplicate_groups": duplicates,
           "rule": "按内容 SHA-256 分组；canonical 为相对路径字典序最小者"},
          os.path.join(ctx.out, "duplicates.json"))
    ctx.result["sources"] = [e["rel"] for e in entries]
    ctx.result.setdefault("change_records", []).append(
        {"stage": "scan", "ts": now(),
         "detail": "扫描 %d 个文件，跳过 %d，重复组 %d"
                   % (len(entries), len(skipped), len(duplicates))})
    ctx.save_result()


# ---------------------------------------------------------------- extract（方向特色）
def phase_extract(ctx):
    scan_index = jload(os.path.join(ctx.work, "scan_index.json")) or {}
    extra = ctx.result.get("extra_metadata_fields") or None
    res = registry.build(scan_index, ctx.input, ctx.work, extra)
    with open(os.path.join(ctx.out, "metadata_registry.jsonl"), "w",
              encoding="utf-8") as fh:
        for w in res["registry"]:
            fh.write(json.dumps(w, ensure_ascii=False) + "\n")
    jdump({"rule": "同文件同字段多来源不同值即入矩阵；winner 先 L4 裁定后 L1>L2>L3；"
                   "全部候选保留并标注",
           "conflicts": res["conflicts"]},
          os.path.join(ctx.out, "conflicts.json"))
    jdump(res["coverage"], os.path.join(ctx.out, "coverage_report.json"))
    # L4 裁定快照落入 output，供只读校验器回查
    snap = res["overrides_raw"] if isinstance(res["overrides_raw"], dict) else {}
    jdump({"note": "work/metadata_overrides.json 的快照；无裁定时为空对象",
           "overrides": snap},
          os.path.join(ctx.out, "metadata_overrides_snapshot.json"))
    jdump({"fields": res["fields"], "candidate_count": res["candidate_count"]},
          os.path.join(ctx.work, "registry_internal.json"))
    ctx.result.setdefault("change_records", []).append(
        {"stage": "extract", "ts": now(),
         "detail": "registry %d 行，冲突 %d 条" % (len(res["registry"]),
                                                  len(res["conflicts"]))})
    ctx.save_result()


# ---------------------------------------------------------------- plan
VERSION_TOKEN = re.compile(
    r"[_\-（(]?(?:v\d+|final|最终版|终稿|定稿|副本|copy)[)）]?(?=\.|$)", re.IGNORECASE)


def version_stem(rel):
    base, ext = os.path.splitext(os.path.basename(rel))
    stem = VERSION_TOKEN.sub("", base).strip("_- （(").lower()
    return (stem or base.lower(), ext.lower())


def detect_template(task_text):
    m = re.search(r"\{([A-Za-z_]\w*)\}(/\{([A-Za-z_]\w*)\})+", task_text)
    if not m:
        return None
    return re.findall(r"\{([A-Za-z_]\w*)\}", m.group(0))


def default_bucket(rel, sidecars):
    base = os.path.basename(rel).lower()
    ext = os.path.splitext(base)[1]
    if rel in sidecars:
        return "admin", "伴随元数据表/行政备注"
    if re.search(r"行政|备注|admin|note", base):
        return "admin", "名称含行政/备注特征"
    if ext in (".csv", ".tsv", ".json", ".dat"):
        return "data", "扩展名判定为数据"
    if re.search(r"supp|补充", base):
        return "supplementary", "名称含补充材料特征"
    if re.search(r"draft|草稿", base):
        return "drafts", "名称含草稿特征"
    if ext in (".txt", ".md"):
        return "papers", "文本类缺省"
    if ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"):
        return "scans", "图像类缺省"
    return "_unassigned", "无法按缺省规则判定类型"


def phase_plan(ctx):
    scan_index = jload(os.path.join(ctx.work, "scan_index.json")) or {"files": []}
    coverage = jload(os.path.join(ctx.out, "coverage_report.json")) or {}
    sidecars = set(coverage.get("sidecar_files", []))
    task_text = ""
    try:
        with open(os.path.join(ctx.work, "task_excerpt.txt"), "r",
                  encoding="utf-8") as fh:
            task_text = fh.read()
    except OSError:
        pass
    template = detect_template(task_text)

    meta = {}
    reg_path = os.path.join(ctx.out, "metadata_registry.jsonl")
    if os.path.isfile(reg_path):
        with open(reg_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    w = json.loads(line)
                    meta[(w["file"], w["field"])] = w["value"]

    dup = jload(os.path.join(ctx.out, "duplicates.json")) or {}
    dup_of = {}
    for g in dup.get("duplicate_groups", []):
        for f in g["files"]:
            if f != g["canonical"]:
                dup_of[f] = g["canonical"]

    assignments = []
    for e in scan_index["files"]:
        rel = e["rel"]
        a = {"file": rel, "target": None, "unassigned_reason": None,
             "duplicate_of": None, "bucket_vars": {}}
        if rel in sidecars:
            a["target"] = "admin/" + os.path.basename(rel)
            a["bucket_vars"]["_rule"] = "sidecar->admin"
        elif rel in dup_of:
            a["duplicate_of"] = dup_of[rel]
        elif template:
            missing = []
            parts = []
            for var in template:
                val = sanitize_path_token(meta.get((rel, var), ""))
                if val:
                    parts.append(val)
                    a["bucket_vars"][var] = val
                else:
                    missing.append(var)
            if missing:
                a["target"] = "_unassigned/" + os.path.basename(rel)
                a["unassigned_reason"] = "模板 %s 缺字段：%s（已诚实留空，未猜测）" % (
                    "/".join("{%s}" % v for v in template), ",".join(missing))
            else:
                a["target"] = "/".join(parts) + "/" + os.path.basename(rel)
        else:
            bucket, why = default_bucket(rel, sidecars)
            a["target"] = bucket + "/" + os.path.basename(rel)
            a["bucket_vars"]["_rule"] = why
            if bucket == "_unassigned":
                a["unassigned_reason"] = why
        assignments.append(a)

    # 版本链：规范化词干分组，≥2 个不同内容成员才算链
    vgroups = {}
    for e in scan_index["files"]:
        vgroups.setdefault(version_stem(e["rel"]), []).append(e)
    chains = []
    for (stem, ext), members in sorted(vgroups.items()):
        hashes = {m["sha256"] for m in members}
        if len(members) > 1 and len(hashes) > 1:
            ms = sorted(members, key=lambda m: (m["mtime"], m["rel"]))
            chains.append({
                "stem": stem, "ext": ext,
                "members": [{"file": m["rel"], "sha256": m["sha256"],
                             "mtime": m["mtime"], "bytes": m["bytes"]} for m in ms],
                "note": "按 mtime 升序，后者视为较新版本；词干规范化去除版本后缀",
            })
    jdump({"rule": "规范化词干(去 vN/final/最终版/终稿/定稿/副本/copy) + 同扩展名分组",
           "chains": chains}, os.path.join(ctx.out, "version_chains.json"))

    # 未决问题检测：task.md 中的检索/问题
    qa_lines = [l.strip() for l in task_text.splitlines()
                if "？" in l or "?" in l or re.match(r"^(问题|检索|Q\d*)[:：]", l.strip())]
    if qa_lines:
        jdump({"questions": qa_lines, "answers": [],
               "status": "awaiting_model_answer",
               "instruction": "模型须作答并把答案+证据路径写入本文件 answers 数组"},
              os.path.join(ctx.out, "QA_LOG.json"))
        ctx.result.setdefault("uncertainties", []).append(
            "task.md 含检索/问题 %d 条，QA_LOG.json 待模型作答" % len(qa_lines))

    # 回填 coverage 的未归位清单
    coverage["unassigned"] = [
        {"file": a["file"], "reason": a["unassigned_reason"]}
        for a in assignments if a["unassigned_reason"]]
    jdump(coverage, os.path.join(ctx.out, "coverage_report.json"))

    jdump({"template": template, "assignments": assignments},
          os.path.join(ctx.work, "plan.json"))
    ctx.result.setdefault("change_records", []).append(
        {"stage": "plan", "ts": now(),
         "detail": "模板=%s；版本链 %d；_unassigned %d"
                   % (template or "缺省桶", len(chains),
                      sum(1 for a in assignments if a["unassigned_reason"]))})
    ctx.save_result()


# ---------------------------------------------------------------- apply
def phase_apply(ctx):
    plan = jload(os.path.join(ctx.work, "plan.json")) or {"assignments": []}
    scan_index = jload(os.path.join(ctx.work, "scan_index.json")) or {"files": []}
    by_rel = {e["rel"]: e for e in scan_index["files"]}
    lib = os.path.join(ctx.out, "library")
    os.makedirs(lib, exist_ok=True)

    meta, prov = {}, {}
    reg_path = os.path.join(ctx.out, "metadata_registry.jsonl")
    if os.path.isfile(reg_path):
        with open(reg_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    w = json.loads(line)
                    meta.setdefault(w["file"], {})[w["field"]] = w["value"]
                    prov.setdefault(w["file"], {})[w["field"]] = {
                        "level": w["level"], "locator": w["locator"],
                        "source_kind": w["source_kind"],
                        "pattern_id": w["pattern_id"]}

    journal_path = os.path.join(ctx.out, "operations_journal.jsonl")
    if os.path.exists(journal_path):  # 本次运行的日志重新开始（幂等重跑收敛）
        os.remove(journal_path)

    manifest, apply_conflicts = [], []
    committed = {}  # target -> sha256 (本库已承诺内容)

    def free_target(target, digest, src_rel):
        """目标被不同内容占用时自动 __vN。"""
        base, ext = os.path.splitext(target)
        cand, n = target, 2
        while True:
            disk = os.path.join(lib, cand)
            known = committed.get(cand)
            if known is None and os.path.isfile(disk):
                try:
                    known = sha256_file(disk)
                except OSError:
                    known = "?"
            if known is None or known == digest:
                return cand, None
            cand = "%s__v%d%s" % (base, n, ext)
            n += 1

    for a in sorted(plan["assignments"], key=lambda x: x["file"]):
        rel = a["file"]
        e = by_rel.get(rel)
        if e is None:
            apply_conflicts.append({"file": rel, "issue": "scan 索引缺失，跳过"})
            continue
        src = e.get("external_path") or os.path.join(ctx.input, rel)
        line = {"file": rel, "sha256": e["sha256"], "bytes": e["bytes"],
                "target": None, "status": None, "duplicate_of": None,
                "metadata": meta.get(rel, {}), "provenance": prov.get(rel, {}),
                "unassigned_reason": a["unassigned_reason"]}
        if a["duplicate_of"]:
            canon = a["duplicate_of"]
            line["status"] = "duplicate_of_canonical"
            line["duplicate_of"] = canon
            ctx.journal({"phase": "apply", "op": "duplicate_recorded",
                         "src": rel, "dst": None, "detail": "内容同 %s" % canon})
        elif a["target"] is None:
            line["status"] = "skipped"
            apply_conflicts.append({"file": rel, "issue": "无目标路径"})
            ctx.journal({"phase": "apply", "op": "skipped", "src": rel,
                         "dst": None, "detail": "无目标路径"})
        else:
            target, conflict = free_target(a["target"], e["sha256"], rel)
            if conflict:
                apply_conflicts.append(conflict)
            dst = os.path.join(lib, target)
            prior = os.path.isfile(dst)
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if prior and sha256_file(dst) == e["sha256"]:
                    line["status"] = "already_committed_identical"
                    ctx.journal({"phase": "apply", "op": "already_committed_identical",
                                 "src": rel, "dst": "library/" + target, "detail": ""})
                else:
                    if prior:
                        apply_conflicts.append({
                            "file": rel, "issue": "目标被不同内容占用，已改落 %s" % target})
                    shutil.copy2(src, dst)
                    ok = sha256_file(dst) == e["sha256"]
                    line["status"] = "committed" if ok else "hash_mismatch_after_copy"
                    if not ok:
                        apply_conflicts.append({"file": rel,
                                                "issue": "复制后哈希不符"})
                    ctx.journal({"phase": "apply", "op": "copied", "src": rel,
                                 "dst": "library/" + target,
                                 "detail": "sha256 ok" if ok else "sha256 MISMATCH"})
                committed[target] = e["sha256"]
                line["target"] = "library/" + target
            except OSError as ex:
                line["status"] = "copy_failed"
                apply_conflicts.append({"file": rel,
                                        "issue": "%s: %s" % (type(ex).__name__, ex)})
                ctx.journal({"phase": "apply", "op": "copy_failed", "src": rel,
                             "dst": "library/" + target, "detail": str(ex)})
        manifest.append(line)

    with open(os.path.join(ctx.out, "LIBRARY_MANIFEST.jsonl"), "w",
              encoding="utf-8") as fh:
        for line in manifest:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    scan_skipped = (jload(os.path.join(ctx.work, "scan_index.json")) or {}).get("skipped", [])
    jdump({"skipped": scan_skipped,
           "apply_conflicts": apply_conflicts,
           "metadata_conflicts_ref": "conflicts.json",
           "note": "跳过与冲突全量留痕；不静默丢弃任何文件"},
          os.path.join(ctx.out, "skipped_and_conflicts.json"))
    ctx.journal({"phase": "apply", "op": "phase_end", "src": "", "dst": "",
                 "detail": "manifest %d 行" % len(manifest)})
    ctx.result.setdefault("change_records", []).append(
        {"stage": "apply", "ts": now(),
         "detail": "manifest %d 行，冲突 %d" % (len(manifest), len(apply_conflicts))})
    ctx.save_result()


# ---------------------------------------------------------------- verify
def phase_verify(ctx):
    script = os.path.join(HERE, "verify_registry.py")
    proc = subprocess.run(
        [sys.executable, script, "--input", ctx.input, "--out", ctx.out],
        capture_output=True, text=True, timeout=600)
    if proc.returncode not in (0, 1):
        ctx.result.setdefault("failures_and_recovery", []).append(
            {"stage": "verify", "error": proc.stderr[-500:],
             "recovery": "校验器异常退出，状态降级", "ts": now()})
    ctx.result.setdefault("change_records", []).append(
        {"stage": "verify", "ts": now(),
         "detail": (proc.stdout.strip().splitlines() or [""])[-1]})
    ctx.save_result()


# ---------------------------------------------------------------- finalize
def phase_finalize(ctx):
    audit = jload(os.path.join(ctx.out, "audit_report.json")) or {}
    overall = audit.get("overall", "FAIL")
    skipped = jload(os.path.join(ctx.out, "skipped_and_conflicts.json")) or {}
    scan_index = jload(os.path.join(ctx.work, "scan_index.json")) or {"files": []}
    dup = jload(os.path.join(ctx.out, "duplicates.json")) or {}
    vc = jload(os.path.join(ctx.out, "version_chains.json")) or {}
    conflicts = jload(os.path.join(ctx.out, "conflicts.json")) or {}
    manifest_n = 0
    mp = os.path.join(ctx.out, "LIBRARY_MANIFEST.jsonl")
    if os.path.isfile(mp):
        with open(mp, "r", encoding="utf-8") as fh:
            manifest_n = sum(1 for l in fh if l.strip())

    degraded = []
    if overall != "PASS":
        degraded.append("audit_report 存在 FAIL 项")
    if skipped.get("skipped"):
        degraded.append("扫描跳过 %d 项（权限/IO 错误）" % len(skipped["skipped"]))
    if skipped.get("apply_conflicts"):
        degraded.append("落库冲突 %d 项" % len(skipped["apply_conflicts"]))
    if jload(os.path.join(ctx.out, "QA_LOG.json"), {}).get("status") == "awaiting_model_answer":
        degraded.append("QA_LOG.json 待模型作答")
    if ctx.result.get("failures_and_recovery"):
        degraded.append("运行期异常 %d 起（见 failures_and_recovery）"
                        % len(ctx.result["failures_and_recovery"]))

    n_conflicts = len(conflicts.get("conflicts", []))
    if n_conflicts:
        ctx.result.setdefault("uncertainties", []).append(
            "conflicts.json 含 %d 条多来源不同值冲突，已按级别规则裁定并保留全部候选"
            % n_conflicts)

    ctx.result["status"] = "complete" if not degraded else "partial"
    if not audit:
        ctx.result["status"] = "blocked"
        degraded.append("audit_report.json 缺失，校验未运行")
    ctx.result["limits"] = degraded
    ctx.result["summary"] = {
        "input_files": len(scan_index["files"]),
        "manifest_rows": manifest_n,
        "total_bytes": sum(e["bytes"] for e in scan_index["files"]),
        "duplicate_groups": len(dup.get("duplicate_groups", [])),
        "version_chains": len(vc.get("chains", [])),
        "metadata_conflicts": n_conflicts,
        "skipped": len(skipped.get("skipped", [])),
        "apply_conflicts": len(skipped.get("apply_conflicts", [])),
        "audit_overall": overall,
        "audit_pass": audit.get("counts", {}).get("pass"),
        "audit_fail": audit.get("counts", {}).get("fail"),
    }
    for name, cf in ctx.result.get("contract_fields", {}).items():
        if isinstance(cf, dict) and cf.get("path"):
            cf["status"] = "delivered" if os.path.exists(
                os.path.join(ctx.out, cf["path"].rstrip("/"))) else "missing"
    ctx.result.setdefault("change_records", []).append(
        {"stage": "finalize", "ts": now(),
         "detail": "status=%s；degraded=%d" % (ctx.result["status"], len(degraded))})
    ctx.save_result()


# ---------------------------------------------------------------- 入口
PHASES = {"init": phase_init, "scan": phase_scan, "extract": phase_extract,
          "plan": phase_plan, "apply": phase_apply, "verify": phase_verify,
          "finalize": phase_finalize}
ORDER = ["init", "scan", "extract", "plan", "apply", "verify", "finalize"]


def main(argv):
    ap = argparse.ArgumentParser(description="metadata-evidence-registry 编排器")
    ap.add_argument("command", choices=list(PHASES) + ["all"])
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--out", default="/app/output")
    args = ap.parse_args(argv)
    ctx = Ctx(args)
    stages = ORDER if args.command == "all" else [args.command]
    for s in stages:
        ctx.stage(s, PHASES[s])
    res = ctx.result
    print("status=%s audit=%s" % (res.get("status"),
                                  res.get("summary", {}).get("audit_overall")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
