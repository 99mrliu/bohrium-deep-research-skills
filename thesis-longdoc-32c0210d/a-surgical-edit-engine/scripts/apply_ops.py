#!/usr/bin/env python3
"""apply_ops.py — 把 ops.json 事务式应用到章节工作副本。

行为契约：
- 首次运行时把 --src 的章节复制到 --work 作为工作副本；之后每次 apply 前把当前
  工作副本快照到 --work/.snapshot/，--rollback 可恢复。
- 每个 op 逐个落改；锚点找不到 → 该 op 记入 problems 并跳过，其余 op 继续（绝不静默失败）。
- 每个 hunk 记录 file/op_id/before/after/line_range 到 change_log.json（相对文件名，无绝对路径）。
- --dry-run：只预览 hunk，不改动任何章节内容、不写快照、不写 change_log
  （若工作副本尚不存在，会先从 --src 建立副本以便试算）。

仅使用 python3 标准库；所有路径均由命令行参数传入。
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

CAPTION_RE = re.compile(r'^\s*(?:\*\*)?\s*(图|表)\s*(\d+)\s*[-–—]\s*(\d+)')
HEADING_RE = re.compile(r'^#{1,6}\s+(.+?)\s*$')

# 数字-单位空格规则的单位表（长的在前，避免前缀误匹配）
UNITS = ["mAh", "min", "kPa", "MPa", "μm", "um", "nm", "mm", "cm", "kg", "mg",
         "μL", "mL", "mol", "ms", "g", "s", "h", "A", "V", "K", "L"]
UNIT_RE = re.compile(r'(\d)(' + "|".join(UNITS) + r')(?![A-Za-z0-9])')
TEMP_RE = re.compile(r'(\d)(℃|°C)')


# ---------- 通用工具 ----------

def protected_line_mask(lines, protect_sections, protect_patterns):
    """返回与 lines 等长的布尔列表：True = 该行受保护不可改。"""
    pats = [re.compile(p) for p in protect_patterns]
    mask, in_prot = [], False
    for line in lines:
        h = HEADING_RE.match(line)
        if h:
            in_prot = any(s in h.group(1) for s in protect_sections)
        prot = in_prot or any(p.search(line) for p in pats)
        mask.append(prot)
    return mask


def group_hunks(op_id, fname, changed, old_lines, new_lines):
    """把变更行号聚成连续 hunk。"""
    hunks, i = [], 0
    while i < len(changed):
        j = i
        while j + 1 < len(changed) and changed[j + 1] == changed[j] + 1:
            j += 1
        seg = changed[i:j + 1]
        hunks.append({"file": fname, "op_id": op_id,
                      "line_range": [seg[0] + 1, seg[-1] + 1],
                      "before": [old_lines[k] for k in seg],
                      "after": [new_lines[k] for k in seg]})
        i = j + 1
    return hunks


def apply_line_op(op, path, transform, hunks, problems):
    """逐行 transform(line, protected) -> 新行；落盘并记录 hunk。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    params = op.get("params", {})
    mask = protected_line_mask(lines, params.get("protect_sections", []),
                               params.get("protect_patterns", []))
    new_lines, changed = [], []
    for idx, (line, prot) in enumerate(zip(lines, mask)):
        nl = line if prot else transform(line)
        new_lines.append(nl)
        if nl != line:
            changed.append(idx)
    if not changed:
        return False
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    hunks.extend(group_hunks(op["op_id"], path.name, changed, lines, new_lines))
    return True


# ---------- 各 op 的 transform ----------

def run_term_unify(op, work_dir, hunks, problems):
    p = op["params"]
    frm, to = p["from"], p["to"]
    any_hit = False

    def tx(line):
        nl = line.replace(frm, to)
        if p.get("sync_abbrev"):  # 缩写定义处同步：统一为全角括号 to（ABBR）
            nl = re.sub(re.escape(to) + r'\(([A-Za-z0-9-]{2,12})\)',
                        lambda m: f"{to}（{m.group(1)}）", nl)
        return nl

    for f in op["target_files"]:
        path = work_dir / f
        if not path.exists():
            problems.append({"op_id": op["op_id"], "reason": f"目标文件缺失: {f}"})
            continue
        any_hit |= apply_line_op(op, path, tx, hunks, problems)
    if not any_hit:
        problems.append({"op_id": op["op_id"],
                         "reason": f"锚点未命中：全文未出现 “{frm}”（保护区内不计）"})


def run_float_ref_fix(op, work_dir, hunks, problems):
    fixes = op["params"].get("fixes", [])
    if not fixes and not op["params"].get("unresolved"):
        problems.append({"op_id": op["op_id"], "reason": "未发现悬空图表引用，无需修复"})
        return
    for u in op["params"].get("unresolved", []):
        problems.append({"op_id": op["op_id"],
                         "reason": f"候选题注不唯一需模型判断: "
                                   f"{u['file']}:{u['line']} {u['kind']}{u['num']}"})
    for fix in fixes:
        path = work_dir / fix["file"]
        if not path.exists():
            problems.append({"op_id": op["op_id"], "reason": f"目标文件缺失: {fix['file']}"})
            continue
        a, b = fix["old_num"].split("-")
        pat = re.compile(r'(?<![0-9-])' + re.escape(fix["kind"]) +
                         rf'\s*{a}\s*[-–—]\s*{b}(?![0-9])')
        lines = path.read_text(encoding="utf-8").splitlines()
        new_lines, changed = [], []
        for idx, line in enumerate(lines):
            if CAPTION_RE.match(line):  # 题注行不改
                new_lines.append(line)
                continue
            nl = pat.sub(f'{fix["kind"]}{fix["new_num"]}', line)
            new_lines.append(nl)
            if nl != line:
                changed.append(idx)
        if changed:
            path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            hunks.extend(group_hunks(op["op_id"], path.name, changed, lines, new_lines))
        else:
            problems.append({"op_id": op["op_id"],
                             "reason": f"锚点未命中：{fix['file']} 中未找到 "
                                       f"{fix['kind']}{fix['old_num']}"})


def run_replace(op, work_dir, hunks, problems):
    old, new = op["params"]["old"], op["params"]["new"]
    count = op["params"].get("count", "all")
    any_hit = False
    for f in op["target_files"]:
        path = work_dir / f
        if not path.exists():
            problems.append({"op_id": op["op_id"], "reason": f"目标文件缺失: {f}"})
            continue
        def tx(line, _n=[0]):
            if old in line and (count == "all" or _n[0] == 0):
                _n[0] += 1
                return line.replace(old, new, 1 if count == "first" else -1)
            return line
        any_hit |= apply_line_op(op, path, tx, hunks, problems)
    if not any_hit:
        problems.append({"op_id": op["op_id"], "reason": f"锚点未命中：未找到旧文 “{old[:40]}…”"})


def run_delete(op, work_dir, hunks, problems):
    text = op["params"]["text"]
    any_hit = False
    for f in op["target_files"]:
        path = work_dir / f
        if not path.exists():
            problems.append({"op_id": op["op_id"], "reason": f"目标文件缺失: {f}"})
            continue
        any_hit |= apply_line_op(op, path, lambda line: line.replace(text, ""),
                                 hunks, problems)
    if not any_hit:
        problems.append({"op_id": op["op_id"], "reason": f"锚点未命中：未找到待删除文本 “{text[:40]}…”"})


def run_format_normalize(op, work_dir, hunks, problems):
    rule = op["params"].get("rule")
    if rule != "number_unit_space":
        problems.append({"op_id": op["op_id"], "reason": f"未知 format_normalize 规则: {rule}"})
        return
    for f in op["target_files"]:
        path = work_dir / f
        if not path.exists():
            problems.append({"op_id": op["op_id"], "reason": f"目标文件缺失: {f}"})
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        new_lines, changed, in_code = [], [], False
        for idx, line in enumerate(lines):
            if line.strip().startswith("```"):
                in_code = not in_code
                new_lines.append(line)
                continue
            if in_code:
                new_lines.append(line)
                continue
            nl = TEMP_RE.sub(r'\1 \2', UNIT_RE.sub(r'\1 \2', line))
            new_lines.append(nl)
            if nl != line:
                changed.append(idx)
        if changed:
            path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            hunks.extend(group_hunks(op["op_id"], path.name, changed, lines, new_lines))


HANDLERS = {"term_unify": run_term_unify,
            "float_ref_fix": run_float_ref_fix,
            "replace": run_replace,
            "delete": run_delete,
            "format_normalize": run_format_normalize}


# ---------- 主流程 ----------

def ensure_workdir(src, work):
    work.mkdir(parents=True, exist_ok=True)
    copied = []
    for p in sorted(Path(src).glob("*.md")):
        dst = work / p.name
        if not dst.exists():
            shutil.copyfile(p, dst)
            copied.append(p.name)
    return copied


def snapshot(work):
    snap = work / ".snapshot"
    if snap.exists():
        shutil.rmtree(snap)
    snap.mkdir()
    for p in work.glob("*.md"):
        shutil.copyfile(p, snap / p.name)


def cmd_apply(args):
    ops_doc = json.loads(Path(args.ops).read_text(encoding="utf-8"))
    work = Path(args.work)
    dry = args.dry_run
    if not dry:
        ensure_workdir(args.src, work)
        snapshot(work)
    else:
        if not work.exists():
            ensure_workdir(args.src, work)

    hunks, problems, manual_ops, applied = [], [], [], 0
    for op in ops_doc.get("ops", []):
        if op["type"] == "manual":
            manual_ops.append({"op_id": op["op_id"], "item_id": op.get("item_id"),
                               "action": op.get("action", ""),
                               "reason": op.get("reason", "")})
            continue
        handler = HANDLERS.get(op["type"])
        if handler is None:
            problems.append({"op_id": op["op_id"], "reason": f"未知 op 类型: {op['type']}"})
            continue
        before = len(hunks)
        if dry:
            # dry-run：在内存副本上试算 hunk，不落盘
            tmp_hunks, tmp_probs = [], []
            _dry_apply_op(op, work, handler, tmp_hunks, tmp_probs)
            hunks.extend(tmp_hunks)
            problems.extend(tmp_probs)
        else:
            handler(op, work, hunks, problems)
        if len(hunks) > before:
            applied += 1

    log = {"schema": "surgical-edit-changelog/v1",
           "case_id": ops_doc.get("case_id", "UNKNOWN"),
           "mode": "dry-run" if dry else "apply",
           "ops_total": len(ops_doc.get("ops", [])),
           "ops_applied": applied,
           "ops_manual": len(manual_ops),
           "problems": problems,
           "manual_ops": manual_ops,
           "hunks": hunks}
    if ops_doc.get("note"):
        log["note"] = ops_doc["note"]

    if dry:
        print(json.dumps(log, ensure_ascii=False, indent=2))
        print(f"[apply:dry-run] {len(hunks)} hunks, {len(problems)} problems — 未写盘",
              file=sys.stderr)
        return 0

    Path(args.change_log).parent.mkdir(parents=True, exist_ok=True)
    Path(args.change_log).write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
    print(f"[apply] ops={log['ops_total']} applied={applied} "
          f"hunks={len(hunks)} problems={len(problems)} manual={len(manual_ops)}")
    for p in problems:
        print(f"  PROBLEM {p['op_id']}: {p['reason']}", file=sys.stderr)
    for m in manual_ops:
        print(f"  MANUAL  {m['op_id']}: {m['reason']}", file=sys.stderr)
    return 0


def _dry_apply_op(op, work, handler, hunks, problems):
    """dry-run 试算：把目标文件复制到内存效果——通过临时目录实现，避免污染工作副本。"""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        for f in op.get("target_files", []):
            srcf = work / f
            if srcf.exists():
                shutil.copyfile(srcf, tdir / f)
        op2 = dict(op)
        handler(op2, tdir, hunks, problems)


def cmd_rollback(args):
    work = Path(args.work)
    snap = work / ".snapshot"
    if not snap.is_dir():
        print("[rollback] 无快照可恢复（.snapshot 不存在）", file=sys.stderr)
        return 2
    restored = []
    for p in sorted(snap.glob("*.md")):
        shutil.copyfile(p, work / p.name)
        restored.append(p.name)
    log = {"schema": "surgical-edit-changelog/v1",
           "mode": "rollback",
           "restored_files": restored,
           "problems": [], "manual_ops": [], "hunks": []}
    Path(args.change_log).write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
    print(f"[rollback] 已从快照恢复 {len(restored)} 个文件: {', '.join(restored)}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="把 ops.json 事务式应用到章节工作副本")
    ap.add_argument("--ops", required=True)
    ap.add_argument("--src", required=True, help="原始章节目录（pristine 来源）")
    ap.add_argument("--work", required=True, help="章节工作副本目录")
    ap.add_argument("--change-log", required=True)
    ap.add_argument("--dry-run", action="store_true", help="只预览 hunk，不写盘")
    ap.add_argument("--rollback", action="store_true", help="从最近快照恢复工作副本")
    args = ap.parse_args()
    if args.rollback:
        return cmd_rollback(args)
    return cmd_apply(args)


if __name__ == "__main__":
    sys.exit(main())
