#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_registry.py — 独立只读校验器（仅标准库，只读 /input 与 /app/output）。

逐条回查 provenance：
  L1  重读源文件对应行（或 #record: 键全文检索），核对值真实出现（子串）
  L2  重读目标文件对应行，核对值真实出现（子串）
  L3  用内嵌同名 pattern 集对文件名重跑正则，核对抽取值一致
  L4  核对 output/metadata_overrides_snapshot.json 中该裁定存在且理由非空

另核对：manifest<->library 目录树一致性（存在性+SHA-256 重算）、
重复组哈希一致、日志闭合（每行可解析、manifest 每行有对应操作记录、
日志以 phase_end 收尾）。

用法：python3 verify_registry.py --input /input --out /app/output
退出码：0 全 PASS；1 有 FAIL；2 校验器自身异常。
"""
import argparse
import hashlib
import json
import os
import re
import sys

# 与 registry.py 相同的文件名 pattern 集（独立内嵌副本，避免共因失效）
NAME_PATTERNS = [
    {"id": "rx_year_prefix",   "field": "year",
     "regex": r"^((?:19|20)\d{2})[_\-]"},
    {"id": "rx_year_anywhere", "field": "year",
     "regex": r"(?<!\d)((?:19|20)\d{2})(?!\d)"},
    {"id": "rx_project_code",  "field": "project",
     "regex": r"(?<![A-Za-z0-9])(NSFC[-_]?\d{6,}|[A-Z]{2,5}[-_]\d{3,})(?![A-Za-z0-9])"},
    {"id": "rx_version_suffix", "field": "version_note", "nocase": True,
     "regex": r"(?:^|[_\-（(])(v\d+|final|最终版|终稿|定稿|副本|copy)(?=[)）_.]|$)"},
    {"id": "rx_dtype_raw",     "field": "data_type", "value": "raw_data",
     "nocase": True,
     "regex": r"(?:^|[_\-])raw(?:[_\-.]|$)"},
    {"id": "rx_dtype_report",  "field": "data_type", "value": "report",
     "nocase": True,
     "regex": r"report|报告"},
]


def sha256_file(path, chunk=65536):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def read_lines(path):
    try:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None


class Audit:
    def __init__(self):
        self.checks = []

    def add(self, cid, name, ok, detail=""):
        self.checks.append({"id": cid, "name": name,
                            "status": "PASS" if ok else "FAIL", "detail": detail})

    def report(self):
        npass = sum(1 for c in self.checks if c["status"] == "PASS")
        nfail = len(self.checks) - npass
        return {"overall": "PASS" if not nfail else "FAIL",
                "counts": {"pass": npass, "fail": nfail},
                "checks": self.checks}


def check_registry_provenance(inp, out, audit):
    """逐条回查 metadata_registry.jsonl 的 locator。"""
    reg_path = os.path.join(out, "metadata_registry.jsonl")
    lines = read_lines(reg_path) or []
    records = []
    bad_json = 0
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            records.append(json.loads(ln))
        except ValueError:
            bad_json += 1
    audit.add("REG-JSONL", "metadata_registry.jsonl 全部行可解析",
              bad_json == 0, "坏行 %d" % bad_json)

    snapshot = {}
    snap_path = os.path.join(out, "metadata_overrides_snapshot.json")
    if os.path.isfile(snap_path):
        try:
            with open(snap_path, "r", encoding="utf-8") as fh:
                snapshot = json.load(fh).get("overrides", {}) or {}
        except (OSError, ValueError):
            snapshot = {}

    npass = nfail = 0
    fails = []
    for i, r in enumerate(records, 1):
        ok, why = backcheck_one(inp, r, snapshot)
        if ok:
            npass += 1
        else:
            nfail += 1
            if len(fails) < 10:
                fails.append("行%d %s/%s: %s" % (i, r.get("file"),
                                                 r.get("field"), why))
    audit.add("REG-PROV", "registry 逐条 provenance 回查（%d 条）" % len(records),
              nfail == 0,
              "PASS %d / FAIL %d%s" % (npass, nfail,
                                       "；" + " | ".join(fails) if fails else ""))


def backcheck_one(inp, r, snapshot):
    file_rel = r.get("file", "")
    value = str(r.get("value", ""))
    level = r.get("level", "")
    locator = r.get("locator", "") or ""
    if not value:
        return False, "空 value"

    if level in ("L1", "L2"):
        m = re.match(r"^(.*)#L(\d+)$", locator)
        if m:
            src_rel, line_no = m.group(1), int(m.group(2))
            lines = read_lines(os.path.join(inp, src_rel))
            if lines is None:
                return False, "源文件不可读 %s" % src_rel
            if line_no < 1 or line_no > len(lines):
                return False, "行号越界 L%d(共%d行)" % (line_no, len(lines))
            if value in lines[line_no - 1]:
                return True, ""
            return False, "值未出现在 %s#L%d" % (src_rel, line_no)
        m = re.match(r"^(.*)#record:(.+)$", locator)
        if m:
            src_rel, key = m.group(1), m.group(2)
            lines = read_lines(os.path.join(inp, src_rel))
            if lines is None:
                return False, "源文件不可读 %s" % src_rel
            blob = "\n".join(lines)
            if key in blob and value in blob:
                return True, ""
            return False, "record 键或值未在 %s 中出现" % src_rel
        return False, "locator 形式无法识别：%s" % locator

    if level == "L3":
        pid = r.get("pattern_id")
        pat = next((p for p in NAME_PATTERNS if p["id"] == pid), None)
        if pat is None:
            return False, "未知 pattern_id %s" % pid
        flags = re.IGNORECASE if pat.get("nocase") else 0
        if pat.get("value") is not None:
            if pat["value"] != value:
                return False, "固定值不符"
            if re.search(pat["regex"], os.path.basename(file_rel), flags):
                return True, ""
            return False, "pattern 未命中文件名"
        m = re.search(pat["regex"], os.path.basename(file_rel), flags)
        if not m:
            return False, "pattern %s 重跑未命中" % pid
        got = m.group(1) if m.groups() else m.group(0)
        if got == value:
            return True, ""
        return False, "重跑抽取值 %r != 登记值 %r" % (got, value)

    if level == "L4":
        # locator: metadata_overrides_snapshot.json#<rel>/<field>
        m = re.match(r"^metadata_overrides_snapshot\.json#(.+)/([^/]+)$", locator)
        if not m:
            return False, "L4 locator 形式错误"
        rel, field = m.group(1), m.group(2)
        entry = snapshot.get(rel)
        if not isinstance(entry, dict):
            return False, "快照中无该文件裁定"
        if str(entry.get("fields", {}).get(field, "")) != value:
            return False, "快照值与登记值不符"
        if not str(entry.get("reason", "")).strip():
            return False, "L4 裁定缺理由字符串"
        return True, ""

    return False, "未知 level %s" % level


def check_manifest_tree(out, audit):
    mp = os.path.join(out, "LIBRARY_MANIFEST.jsonl")
    lines = read_lines(mp) or []
    rows, bad = [], 0
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except ValueError:
            bad += 1
    audit.add("MAN-JSONL", "LIBRARY_MANIFEST.jsonl 全部行可解析", bad == 0,
              "坏行 %d" % bad)

    lib = os.path.join(out, "library")
    fails = []
    manifest_targets = {}
    by_file = {}
    for r in rows:
        by_file[r.get("file")] = r
        tgt = r.get("target")
        if r.get("status") in ("committed", "already_committed_identical") and tgt:
            manifest_targets[tgt] = r
            full = os.path.join(out, tgt)
            if not os.path.isfile(full):
                fails.append("缺失 %s" % tgt)
            else:
                try:
                    if sha256_file(full) != r.get("sha256"):
                        fails.append("哈希不符 %s" % tgt)
                except OSError:
                    fails.append("不可读 %s" % tgt)
        elif r.get("status") == "duplicate_of_canonical":
            canon = by_file.get(r.get("duplicate_of"))
            # canonical 可能在其后行，二次遍历再核
    audit.add("MAN-TREE-1", "manifest 目标存在且 SHA-256 重算一致", not fails,
              "；".join(fails[:10]))

    # 反向：library 中每个文件都在 manifest
    disk = []
    for root, dirs, names in os.walk(lib):
        dirs.sort()
        for n in sorted(names):
            disk.append(os.path.relpath(os.path.join(root, n), out))
    extra = [d for d in disk if d not in manifest_targets]
    audit.add("MAN-TREE-2", "library 目录树无 manifest 外文件", not extra,
              "多余 %s" % "；".join(extra[:10]))

    # 重复组：alias 指向的 canonical 目标存在且哈希与 alias 记录一致
    fails = []
    for r in rows:
        if r.get("status") == "duplicate_of_canonical":
            canon = by_file.get(r.get("duplicate_of"))
            if not canon or not canon.get("target"):
                fails.append("%s 的 canonical 无目标" % r.get("file"))
            elif canon.get("sha256") != r.get("sha256"):
                fails.append("%s 与 canonical 哈希不一致" % r.get("file"))
    audit.add("MAN-DUP", "重复别名记录与 canonical 一致", not fails,
              "；".join(fails[:10]))


def check_journal(out, audit):
    jp = os.path.join(out, "operations_journal.jsonl")
    lines = read_lines(jp)
    if lines is None:
        audit.add("JRN-EXISTS", "operations_journal.jsonl 存在", False, "缺失")
        return
    ops, bad = [], 0
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            ops.append(json.loads(ln))
        except ValueError:
            bad += 1
    audit.add("JRN-PARSE", "日志每行可解析", bad == 0, "坏行 %d" % bad)
    closed = bool(ops) and ops[-1].get("op") == "phase_end"
    audit.add("JRN-CLOSE", "日志以 phase_end 闭合", closed,
              "末行 op=%s" % (ops[-1].get("op") if ops else "无"))

    # manifest 每个文件都有对应操作
    mp = os.path.join(out, "LIBRARY_MANIFEST.jsonl")
    rows = []
    for ln in (read_lines(mp) or []):
        ln = ln.strip()
        if ln:
            try:
                rows.append(json.loads(ln))
            except ValueError:
                pass
    covered = {o.get("src") for o in ops if o.get("op") in
               ("copied", "already_committed_identical", "duplicate_recorded",
                "skipped", "copy_failed")}
    missing = [r.get("file") for r in rows if r.get("file") not in covered]
    audit.add("JRN-COVER", "manifest 每行均有对应日志操作", not missing,
              "缺 %s" % "；".join(missing[:10]))


def check_aux(out, audit):
    for name in ("conflicts.json", "coverage_report.json", "duplicates.json",
                 "version_chains.json", "skipped_and_conflicts.json",
                 "result.json"):
        p = os.path.join(out, name)
        ok = os.path.isfile(p)
        detail = ""
        if ok:
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    json.load(fh)
            except ValueError as e:
                ok, detail = False, "JSON 解析失败 %s" % e
        audit.add("AUX-" + name, "辅助交付物 %s 存在且可解析" % name, ok, detail)

    # 冲突矩阵结构：每条含 winner 与全部候选
    try:
        with open(os.path.join(out, "conflicts.json"), "r", encoding="utf-8") as fh:
            cj = json.load(fh)
        bad = [c for c in cj.get("conflicts", [])
               if not c.get("winner") or len(c.get("candidates", [])) < 2
               or len({x.get("value") for x in c.get("candidates", [])}) < 2]
        audit.add("AUX-CONFLICT-STRUCT", "冲突矩阵条目结构完整（winner+多值候选）",
                  not bad, "异常 %d 条" % len(bad))
    except (OSError, ValueError):
        audit.add("AUX-CONFLICT-STRUCT", "冲突矩阵条目结构完整", False, "不可读")


def main(argv):
    ap = argparse.ArgumentParser(description="metadata-evidence-registry 独立校验器")
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    inp, out = os.path.abspath(args.input), os.path.abspath(args.out)
    audit = Audit()
    try:
        check_registry_provenance(inp, out, audit)
        check_manifest_tree(out, audit)
        check_journal(out, audit)
        check_aux(out, audit)
    except Exception as e:  # 校验器自身异常 -> 退出码 2
        audit.add("VERIFIER-ERROR", "校验器自身异常", False,
                  "%s: %s" % (type(e).__name__, e))
        rep = audit.report()
        with open(os.path.join(out, "audit_report.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=2)
        print("audit overall=%s (verifier error)" % rep["overall"])
        return 2
    rep = audit.report()
    with open(os.path.join(out, "audit_report.json"), "w", encoding="utf-8") as fh:
        json.dump(rep, fh, ensure_ascii=False, indent=2)
    print("audit overall=%s pass=%d fail=%d"
          % (rep["overall"], rep["counts"]["pass"], rep["counts"]["fail"]))
    return 0 if rep["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
