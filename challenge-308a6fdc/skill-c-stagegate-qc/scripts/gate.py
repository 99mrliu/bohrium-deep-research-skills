#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gate.py —— stagegate-qc-runner 的门禁主程序（仅 Python3 标准库）。

定位：写作"过程"的门禁系统。不验证事实、不管文体、不做渲染，
只管理流程是否被诚实执行：先交付骨架、再迭代加固、绝不空交。

子命令：
    init                 读 /input/case.json 与 task.md，生成 workplan.json，
                         并立即在输出目录写入骨架 result.json（全字段+PENDING）
                         与 deliverable 占位，保证任何时刻被杀都有诚实 partial。
    check <stage>        校验某阶段 required_artifacts 存在、非空、无占位符；
                         对比 budget_deadline_sec：超前 GO，逾期 WARN-BUT-PROCEED，
                         产物缺失 FAIL（退出码 1）。不阻塞，但全部留痕。
    selfcheck            量规自评：机器可判定项自动评分，写 selfcheck_report.md。
    deliver              出口清单 + 装配终版 result.json + delivery_manifest.json。
                         出口检查失败仍允许交付（诚实记录，退出码 2），不静默通过。

路径可用环境变量覆盖（用于本地演练与 examples/ 复现）：
    STAGEGATE_INPUT_DIR  默认 /input
    STAGEGATE_WORK_DIR   默认 /app/work
    STAGEGATE_OUTPUT_DIR 默认 /app/output
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

# ---- 路径契约（可被环境变量覆盖，便于在 examples/ 下端到端演练） ----------------
INPUT_DIR = os.environ.get("STAGEGATE_INPUT_DIR", "/input")
WORK_DIR = os.environ.get("STAGEGATE_WORK_DIR", "/app/work")
OUTPUT_DIR = os.environ.get("STAGEGATE_OUTPUT_DIR", "/app/output")

BUDGET_SEC = 900          # 总执行预算（秒）
WORKPLAN = "workplan.json"
WORKLOG = "worklog.jsonl"

# 占位符正则：命中即视为"未完成的空洞"。注意【待确认】是合法的不确定性标注，不算占位符；
# 中文"占位符"一词只在尖括号/锚括号形态下匹配，避免误伤讨论占位符本身的正常行文。
PLACEHOLDER_RE = re.compile(r"TODO|FIXME|XXX|TBD|<PLACEHOLDER>|【占位符】|<占位符>")
PENDING_TOKEN = "PENDING"
UNCERTAIN_MARK = "【待确认】"
MIN_DELIVERABLE_CHARS = 200   # selfcheck 中 deliverable 的最小字数（机器可判）

# 五阶段定义：required_artifacts 为相对 WORK_DIR 的路径；deadline 为相对 init 的秒偏移。
STAGES = {
    "intake": {
        "desc": "材料清点：列出全部输入材料、可用性与初步判断",
        "deadline_sec": 120,
        "required_artifacts": ["notes/material_inventory.md"],
    },
    "outline": {
        "desc": "章节骨架 + 证据分派表：每个章节挂哪些材料/事实",
        "deadline_sec": 300,
        "required_artifacts": ["notes/outline.md", "notes/evidence_assignment.md"],
    },
    "draft": {
        "desc": "完整初稿：允许含【待确认】标注，但不允许 TODO/XXX 等占位符",
        "deadline_sec": 600,
        "required_artifacts": ["deliverable.md"],
    },
    "audit": {
        "desc": "自查：契约字段齐、无占位符、缺口已标注",
        "deadline_sec": 780,
        "required_artifacts": ["notes/audit_report.md"],
    },
    "finalize": {
        "desc": "装配 result.json 并交付（产物由 deliver 子命令生成）",
        "deadline_sec": 860,
        "required_artifacts": [],
    },
}
STAGE_ORDER = ["intake", "outline", "draft", "audit", "finalize"]


# ---- 小工具 -------------------------------------------------------------------
def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def wpath(name):
    return os.path.join(WORK_DIR, name)


def opath(name):
    return os.path.join(OUTPUT_DIR, name)


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def dump_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def append_worklog(stage, verdict, notes):
    """每次门禁调用都追加一行 JSONL，finalize 时汇成 change_log。"""
    os.makedirs(WORK_DIR, exist_ok=True)
    rec = {"ts": now_iso(), "stage": stage, "verdict": verdict, "notes": notes}
    with open(wpath(WORKLOG), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def elapsed_sec(workplan):
    return int(time.time() - workplan.get("init_epoch", time.time()))


def import_assembler():
    """同目录导入 assemble_result.py（骨架与终版 result.json 的装配逻辑）。"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import assemble_result  # noqa: E402
    return assemble_result


# ---- init ---------------------------------------------------------------------
def cmd_init(_args):
    case_path = os.path.join(INPUT_DIR, "case.json")
    case = load_json(case_path)
    if case is None:
        print(f"[init][FATAL] 无法读取 {case_path}，请确认输入目录挂载正确。")
        return 1
    task_path = os.path.join(INPUT_DIR, "task.md")
    task_text = read_text(task_path)
    if not task_text.strip():
        print(f"[init][WARN] {task_path} 缺失或为空，task 要求需从 case.json 推断。")

    ar = import_assembler()
    keys = ar.contract_keys(case)
    case_id = str(case.get("case_id", "UNKNOWN"))

    os.makedirs(os.path.join(WORK_DIR, "notes"), exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 幂等：若 workplan 已存在，保留原 init 时间戳（预算时钟不重置），其余照常刷新。
    old = load_json(wpath(WORKPLAN)) or {}
    init_epoch = old.get("init_epoch", time.time())
    init_iso = old.get("init_iso", now_iso())
    reused = "init_epoch" in old

    workplan = {
        "version": 1,
        "case_id": case_id,
        "contract_keys": keys,
        "init_epoch": init_epoch,
        "init_iso": init_iso,
        "budget_sec": BUDGET_SEC,
        "paths": {"input": INPUT_DIR, "work": WORK_DIR, "output": OUTPUT_DIR},
        "stages": {name: STAGES[name] for name in STAGE_ORDER},
        "reinit_idempotent": reused,
    }
    dump_json(wpath(WORKPLAN), workplan)

    # 先交付后优化：init 立即落一版骨架 result.json（全字段 + PENDING）。
    # 幂等：若已存在非骨架版本（含真实内容），不覆盖，只在日志说明。
    result_path = opath("result.json")
    if not os.path.exists(result_path):
        ar.write_skeleton(case, result_path)
        print(f"[init] 骨架 result.json 已写入 {result_path}（全字段 + PENDING）")
    else:
        print(f"[init] {result_path} 已存在，保持不覆盖（幂等）。")

    # deliverable 占位：保证被杀时输出目录里有可解释的诚实 partial。
    deliverable_ph = opath("deliverable.md")
    if not os.path.exists(deliverable_ph):
        with open(deliverable_ph, "w", encoding="utf-8") as f:
            f.write("<!-- PENDING: 初稿尚未完成，本文件为 init 生成的诚实占位，"
                    "保证流程中断时仍有可交付的 partial。 -->\n\n"
                    f"# PENDING：{case_id} 交付物撰写中\n")
        print(f"[init] deliverable 占位已写入 {deliverable_ph}")

    append_worklog("init", "GO",
                   f"workplan 生成；契约字段 {keys}；"
                   f"{'重复 init，保留原时钟（幂等）' if reused else '首次 init'}")
    print(f"[init] workplan 已写入 {wpath(WORKPLAN)}；预算 {BUDGET_SEC}s，"
          f"阶段：{' → '.join(STAGE_ORDER)}")
    print(f"[init] 立即产出骨架完成：任何时刻中断都有诚实 partial。")
    return 0


# ---- check --------------------------------------------------------------------
def artifact_problems(rel_path):
    """返回该产物的问题列表；空列表表示通过。"""
    problems = []
    p = wpath(rel_path)
    if not os.path.exists(p):
        return [f"缺失：{rel_path}"]
    text = read_text(p)
    if not text.strip():
        problems.append(f"为空：{rel_path}")
    m = PLACEHOLDER_RE.search(text)
    if m:
        problems.append(f"含占位符 '{m.group(0)}'：{rel_path}")
    return problems


def cmd_check(args):
    stage = args.stage
    if stage not in STAGES:
        print(f"[check][FAIL] 未知阶段 '{stage}'，可选：{', '.join(STAGE_ORDER)}")
        return 1
    workplan = load_json(wpath(WORKPLAN))
    if workplan is None:
        print("[check][FAIL] workplan.json 不存在，请先运行 gate.py init。")
        return 1

    el = elapsed_sec(workplan)
    deadline = STAGES[stage]["deadline_sec"]
    problems = []
    for rel in STAGES[stage]["required_artifacts"]:
        problems.extend(artifact_problems(rel))

    print(f"[check] 阶段 {stage}（{STAGES[stage]['desc']}）")
    print(f"[check] 已用时 {el}s / 阶段截止 {deadline}s / 总预算 {BUDGET_SEC}s")

    if problems:
        verdict = "FAIL"
        for p in problems:
            print(f"[check][FAIL] {p}")
        print("[check][FAIL] 处置：补齐产物后重跑 check；若时间不足，跳到 deliver "
              "以当前最好版本诚实交付（change_log 会记录本次 FAIL）。")
        append_worklog(stage, verdict, "；".join(problems))
        return 1

    if el > deadline:
        verdict = "WARN-BUT-PROCEED"
        print(f"[check][{verdict}] 已超阶段 deadline {el - deadline}s。不阻塞："
              f"立即交付当前最好版本，后续阶段压缩时间。")
    else:
        verdict = "GO"
        print(f"[check][GO] 产物齐备且超前 deadline {deadline - el}s，进入下一阶段。")
    append_worklog(stage, verdict, f"elapsed={el}s deadline={deadline}s")
    return 0


# ---- selfcheck ----------------------------------------------------------------
# 机器可判定项 ↔ references/rubric.md 的编号映射
def cmd_selfcheck(_args):
    workplan = load_json(wpath(WORKPLAN))
    if workplan is None:
        print("[selfcheck][FAIL] workplan.json 不存在，请先运行 gate.py init。")
        return 1
    keys = workplan.get("contract_keys", [])
    result = load_json(opath("result.json")) or {}
    # deliverable 优先取工作目录初稿，其次输出目录占位
    deliverable = read_text(wpath("deliverable.md")) or read_text(opath("deliverable.md"))
    el = elapsed_sec(workplan)

    machine_items = []  # (编号, 描述, 是否通过, 说明)
    # Q5: result.json 契约字段齐全
    missing = [k for k in keys if k not in result]
    machine_items.append(("Q5", "result.json 含全部契约字段", not missing,
                          f"缺失：{missing}" if missing else f"{len(keys)} 个字段齐全"))
    # Q6: deliverable 非空且 ≥N 字、无占位符
    n_chars = len(re.sub(r"\s", "", deliverable))
    has_ph = bool(PLACEHOLDER_RE.search(deliverable))
    machine_items.append(("Q6", f"deliverable 非空且 ≥{MIN_DELIVERABLE_CHARS} 字、无占位符",
                          n_chars >= MIN_DELIVERABLE_CHARS and not has_ph,
                          f"当前 {n_chars} 字；占位符：{'有' if has_ph else '无'}"))
    # Q7: evidence_map 非空。selfcheck 运行在 deliver 之前，此时 result.json 常仍是骨架，
    # 因此同时看工作目录的 evidence_map.json 与 result.json 中的已装配值。
    em_work = load_json(wpath("evidence_map.json"))
    em_res = result.get("evidence_map")
    em_src, em = ("result.json", em_res) if isinstance(em_res, (dict, list)) and em_res \
        else ("work/evidence_map.json", em_work)
    em_ok = isinstance(em, (dict, list)) and len(em) > 0
    machine_items.append(("Q7", "evidence_map 非空", em_ok,
                          f"{em_src}：{'非空' if em_ok else '为空或不存在'}"))
    # Q9: change_log 非空。同理，deliver 前看 worklog.jsonl（deliver 会把它汇成 change_log）。
    cl_res = result.get("change_log")
    n_worklog = sum(1 for ln in read_text(wpath(WORKLOG)).splitlines() if ln.strip())
    cl_ok = (isinstance(cl_res, list) and len(cl_res) > 0) or n_worklog > 0
    machine_items.append(("Q9", "change_log 非空（worklog 已有记录）", cl_ok,
                          f"worklog {n_worklog} 条"
                          + (f"；result.json change_log {len(cl_res)} 条"
                             if isinstance(cl_res, list) else "")))
    # Q10: 【待确认】标注计数（0 为通过；>0 为 WARN，需在 uncertainty 中说明）
    n_unc = deliverable.count(UNCERTAIN_MARK)
    machine_items.append(("Q10", f"{UNCERTAIN_MARK} 标注计数", n_unc == 0,
                          f"{n_unc} 处" + ("（需在 uncertainty/change_log 说明）" if n_unc else "")))

    model_items = [  # 需模型自答（机器无法判定）
        ("Q1", "是否产出了 task.md 要求的全部交付物？"),
        ("Q2", "deliverable 是否逐条覆盖 task.md 的要求？"),
        ("Q3", "每条事实是否都能追溯到具体来源材料？"),
        ("Q4", "是否存在任何虚构、臆测或未标注的推断？"),
        ("Q8", "evidence_map 中的来源是否可定位到具体文件/段落？"),
    ]

    lines = ["# 量规自评报告（selfcheck）", "",
             f"- 生成时间：{now_iso()}；已用时 {el}s / {BUDGET_SEC}s",
             f"- case_id：{workplan.get('case_id')}", "",
             "## 机器可判定项", "",
             "| 编号 | 自查项 | 判定 | 说明 |", "|---|---|---|---|"]
    n_pass = 0
    for qid, desc, ok, note in machine_items:
        n_pass += 1 if ok else 0
        lines.append(f"| {qid} | {desc} | {'PASS' if ok else 'FAIL/WARN'} | {note} |")
    lines += ["", f"机器项通过 {n_pass}/{len(machine_items)}。",
              "", "## 需模型自答项（机器无法判定，必须逐条诚实回答）", ""]
    for qid, q in model_items:
        lines.append(f"- [ ] {qid} {q}")
    lines += ["", "若任一机器项 FAIL 或模型项答案为否：修复后重跑 selfcheck；"
                  "无法修复的在 result.json 的 uncertainty/change_log 中如实说明。"]
    report = "\n".join(lines) + "\n"
    os.makedirs(WORK_DIR, exist_ok=True)
    with open(wpath("selfcheck_report.md"), "w", encoding="utf-8") as f:
        f.write(report)

    print(report)
    append_worklog("selfcheck", "GO" if n_pass == len(machine_items) else "WARN-BUT-PROCEED",
                   f"机器项 {n_pass}/{len(machine_items)} 通过；报告见 selfcheck_report.md")
    return 0


# ---- deliver ------------------------------------------------------------------
def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def exit_checks(result, result_raw, deliverable, case):
    """出口清单：返回 (通过项列表, 失败项列表)。失败不阻塞交付，但必须诚实记录。"""
    oks, fails = [], []
    # E1: 契约字段齐全
    ar = import_assembler()
    keys = ar.contract_keys(case)
    missing = [k for k in keys if k not in result]
    (fails if missing else oks).append(
        f"E1 契约字段齐全" + (f"（缺失：{missing}）" if missing else ""))
    # E2: case_id 逐字节一致（JSON 字符串等值 + 原始字节比对双重确认）
    cid_in = str(case.get("case_id", ""))
    cid_out = str(result.get("case_id", ""))
    byte_same = json.dumps(cid_in, ensure_ascii=False) == json.dumps(cid_out, ensure_ascii=False)
    (oks if cid_in == cid_out and byte_same else fails).append(
        f"E2 case_id 与输入一致（{cid_out!r}）")
    # E3: 无 PENDING 残留；若有，每条须在 change_log 有对应说明
    n_pending = result_raw.count(PENDING_TOKEN)
    cl_text = json.dumps(result.get("change_log", []), ensure_ascii=False)
    if n_pending == 0:
        oks.append("E3 无 PENDING 残留")
    elif PENDING_TOKEN in cl_text:
        oks.append(f"E3 有 {n_pending} 处 PENDING，但 change_log 已有对应说明（诚实降级）")
    else:
        fails.append(f"E3 有 {n_pending} 处 PENDING 残留且 change_log 无说明")
    # E4: deliverable 无占位符
    m = PLACEHOLDER_RE.search(deliverable)
    (fails if m else oks).append(
        "E4 deliverable 无占位符" + (f"（命中 '{m.group(0)}'）" if m else ""))
    # E5: 锚括号【】闭合
    unbalanced = deliverable.count("【") != deliverable.count("】")
    (fails if unbalanced else oks).append(
        f"E5 锚括号闭合（【{deliverable.count('【')} 个 / 】{deliverable.count('】')} 个）")
    return oks, fails


def cmd_deliver(_args):
    workplan = load_json(wpath(WORKPLAN))
    if workplan is None:
        print("[deliver][FAIL] workplan.json 不存在，请先运行 gate.py init。")
        return 1
    case = load_json(os.path.join(INPUT_DIR, "case.json")) or {}
    ar = import_assembler()
    el = elapsed_sec(workplan)

    # 1) 把终稿与自评报告从工作目录复制到输出目录（同路径则跳过）
    for name in ("deliverable.md", "selfcheck_report.md"):
        src, dst = wpath(name), opath(name)
        if os.path.exists(src) and os.path.abspath(src) != os.path.abspath(dst):
            with open(src, "r", encoding="utf-8") as f:
                content = f.read()
            with open(dst, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[deliver] 已复制 {name} → {dst}")

    # 2) 预装配 result.json 用于出口检查（从 workplan/worklog/deliverable 及可选的
    #    preserved_facts.json / evidence_map.json）
    result_path = opath("result.json")
    result = ar.write_final(case, workplan, wpath(WORKLOG), WORK_DIR, result_path)

    # 3) 出口清单
    result_raw = read_text(result_path)
    deliverable = read_text(opath("deliverable.md"))
    oks, fails = exit_checks(result, result_raw, deliverable, case)
    for line in oks:
        print(f"[deliver][PASS] {line}")
    for line in fails:
        print(f"[deliver][FAIL] {line}")

    # 4) 先把本次 finalize 判定写入 worklog，再终装配——保证 change_log 包含
    #    本次 deliver 自己的记录（诚实闭环）
    append_worklog("finalize", "FAIL" if fails else "GO",
                   f"deliver：{len(oks)} 项通过，{len(fails)} 项失败；"
                   f"elapsed={el}s/{BUDGET_SEC}s")
    result = ar.write_final(case, workplan, wpath(WORKLOG), WORK_DIR, result_path)
    print(f"[deliver] 终版 result.json 已装配 → {result_path}")
    files = []
    for root, _dirs, names in os.walk(OUTPUT_DIR):
        for n in sorted(names):
            p = os.path.join(root, n)
            rel = os.path.relpath(p, OUTPUT_DIR)
            if rel == "delivery_manifest.json":
                continue
            files.append({"path": rel, "bytes": os.path.getsize(p),
                          "sha256": sha256_of(p)})
    manifest = {
        "generated_at": now_iso(),
        "case_id": str(case.get("case_id", "UNKNOWN")),
        "elapsed_sec": el,
        "budget_sec": BUDGET_SEC,
        "exit_check": "FAIL" if fails else "PASS",
        "exit_check_failures": fails,
        "files": files,
    }
    dump_json(opath("delivery_manifest.json"), manifest)
    print(f"[deliver] delivery_manifest.json 已写入（{len(files)} 个文件，含 sha256）")

    if fails:
        print("[deliver][FAIL] 出口清单未全过：仍交付当前最好版本，"
              "失败项已写入 manifest 与 worklog（诚实记录，不静默通过）。")
        return 2
    print(f"[deliver][GO] 出口清单全过，交付完成。总用时 {el}s / {BUDGET_SEC}s。")
    return 0


# ---- main ---------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="stagegate-qc-runner 过程门禁：init → check → selfcheck → deliver")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="生成 workplan + 骨架 result.json（先交付后优化）")
    p_check = sub.add_parser("check", help="阶段门禁检查")
    p_check.add_argument("stage", choices=STAGE_ORDER)
    sub.add_parser("selfcheck", help="量规自评（机器可判项自动评分）")
    sub.add_parser("deliver", help="出口清单 + 装配终版 + 交付清单")
    args = ap.parse_args()
    handler = {"init": cmd_init, "check": cmd_check,
               "selfcheck": cmd_selfcheck, "deliver": cmd_deliver}[args.cmd]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
