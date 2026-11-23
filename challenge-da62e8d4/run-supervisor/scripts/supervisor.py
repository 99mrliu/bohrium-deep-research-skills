#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run-supervisor：论文复现任务的过程质量控制状态机监督器（仅用 Python3 标准库）。

核心主张：900 秒预算下的复现任务，典型失败不是科学判断错，而是过程失控——
超时什么都没留下、候选崩溃被默默跳过、阶段漏做、result.json 缺字段或与过程
证据矛盾、重复执行覆盖好结果。本监督器只做过程完整性与诚实性，不做科学判断
（容差、归因、比较由 agent 完成）。

子命令：
  init      解析 case.json，建立 state.json 与"始终合法"的 result.json 骨架
  phase     登记阶段检查点（证据文件必须真实存在，否则拒绝）
  run       带超时的受控运行；候选失败/超时记为证据，绝不中断流程
  status    打印各阶段状态、预算台账、下一建议动作
  finalize  从过程证据重算总状态并做合约 lint（FAIL 退出码 1，PASS 0）

退出码约定：0 成功；1 finalize 合约 lint 未通过；2 监督器自身用法/状态错误。
注意：run 子命令在候选失败或超时时仍返回 0——失败是证据，不是中断。
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

PHASES = ["inventory", "targets", "tolerances", "run", "compare", "conclude"]
CORE_PHASES = ["inventory", "targets", "run"]
PHASE_STATUS = ("pending", "done", "failed", "skipped")
VALID_SET_STATUS = ("done", "failed", "skipped")

# result.json 中由监督器维护的过程字段（合约字段之外的记账字段）
BOOKKEEPING_KEYS = [
    "case_id", "status", "generated_by", "sources", "uncertainty",
    "change_records", "phases", "runs", "field_notes",
]


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def eprint(msg):
    print(msg, file=sys.stderr)


def die(msg, code=2):
    eprint("[run-supervisor][ERROR] %s" % msg)
    sys.exit(code)


def load_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        die("%s 不存在：%s" % (what, path))
    except json.JSONDecodeError as exc:
        die("%s 不是合法 JSON：%s（%s）" % (what, path, exc))


def dump_json(path, obj):
    """原子写：先写临时文件再替换，保证任意时刻磁盘上的 JSON 都完整可解析。"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def parse_contract(case_path):
    """从 case.json 提取 case_id 与 output_contract 字段名清单（兼容 list/dict）。
    缺字段即报错退出——这是评测契约的硬要求，init 阶段就发现。"""
    case = load_json(case_path, "case.json")
    if not isinstance(case, dict):
        die("case.json 顶层必须是对象：%s" % case_path)
    case_id = case.get("case_id")
    if not case_id or not isinstance(case_id, str):
        die("case.json 缺少有效的 case_id 字段：%s" % case_path)
    oc = case.get("output_contract")
    if oc is None:
        die("case.json 缺少 output_contract 字段：%s" % case_path)
    fields = []
    if isinstance(oc, dict):
        fields = list(oc.keys())
    elif isinstance(oc, list):
        for i, item in enumerate(oc):
            if isinstance(item, str):
                fields.append(item)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("field") or item.get("key")
                if not name:
                    die("output_contract 第 %d 项缺少 name/field/key：%r" % (i, item))
                fields.append(name)
            else:
                die("output_contract 第 %d 项类型无法识别：%r" % (i, item))
    else:
        die("output_contract 必须是 list 或 dict，实际为 %s" % type(oc).__name__)
    if not fields:
        die("output_contract 为空，无法建立合约字段清单")
    dup = sorted({f for f in fields if fields.count(f) > 1})
    if dup:
        die("output_contract 存在重复字段名：%s" % ", ".join(dup))
    clash = [f for f in fields if f in BOOKKEEPING_KEYS]
    if clash:
        die("output_contract 字段与监督器记账字段冲突：%s（请人工处理）" % ", ".join(clash))
    return case_id, fields


def state_path(work):
    return os.path.join(work, "state.json")


def load_state(work):
    sp = state_path(work)
    if not os.path.exists(sp):
        die("未找到 state.json（尚未 init？）：%s" % sp)
    return load_json(sp, "state.json")


def save_state(work, state):
    dump_json(state_path(work), state)


def blank_result(case_id, fields):
    """构造"始终合法"的 result.json 骨架：含 case_id 与全部合约字段（置 null）、
    诚实 status=partial、init 变更记录。"""
    result = {
        "case_id": case_id,
        "status": "partial",
        "generated_by": "run-supervisor",
        "sources": {},
        "uncertainty": [
            "init：尚未执行任何阶段，全部合约字段为占位 null，结论待定。"
        ],
        "change_records": [],
        "phases": {p: {"status": "pending", "ts": None, "evidence": [], "note": ""}
                   for p in PHASES},
        "runs": [],
        "field_notes": {},
    }
    for f in fields:
        result[f] = None
    return result


def sync_result(work, state, mutate=None):
    """把 state 中的阶段/运行证据同步进 result.json，可选地对 result 做额外修改。
    每次同步都是一次原子落盘：任意时刻 result.json 都合法且与证据一致。"""
    result_path = state["result_path"]
    result = load_json(result_path, "result.json")
    result["case_id"] = state["case_id"]
    result["phases"] = state["phases"]
    result["runs"] = [
        {
            "name": r["name"],
            "exit_code": r["exit_code"],
            "timeout": r["timeout"],
            "wall_seconds": r["wall_seconds"],
            "log_dir": r["log_dir"],
        }
        for r in state["runs"]
    ]
    result["change_records"] = state["change_records"]
    if mutate is not None:
        mutate(result)
    dump_json(result_path, result)
    return result


def add_change_record(state, action, detail):
    state["change_records"].append(
        {"ts": now_iso(), "actor": "run-supervisor", "action": action, "detail": detail}
    )


# ---------------------------------------------------------------- init

def cmd_init(args):
    case_id, fields = parse_contract(args.case)
    work = os.path.abspath(args.work)
    output = os.path.abspath(args.output)
    os.makedirs(work, exist_ok=True)
    os.makedirs(output, exist_ok=True)
    sp = state_path(work)
    result_path = os.path.join(output, "result.json")

    if os.path.exists(sp) and not args.force:
        # 幂等：重复 init 不覆盖已有状态与结果
        print("[run-supervisor] 已存在 state.json，init 跳过（不覆盖）。"
              "如需重建请使用 --force。state=%s" % sp)
        return 0

    state = {
        "version": 1,
        "case_id": case_id,
        "contract_fields": fields,
        "case_path": os.path.abspath(args.case),
        "work_dir": work,
        "output_dir": output,
        "result_path": result_path,
        "budget_seconds": args.budget_seconds,
        "start_epoch": time.time(),
        "start_iso": now_iso(),
        "phases": {p: {"status": "pending", "ts": None, "evidence": [], "note": ""}
                   for p in PHASES},
        "runs": [],
        "change_records": [],
    }
    add_change_record(
        state, "init",
        "初始化：case_id=%s，合约字段 %d 个，预算 %d 秒；建立六阶段 pending 状态机。"
        % (case_id, len(fields), args.budget_seconds),
    )
    save_state(work, state)

    if os.path.exists(result_path) and not args.force:
        eprint("[run-supervisor][WARN] result.json 已存在而 state.json 不存在/被强制重建，"
               "旧 result.json 将被骨架覆盖：%s" % result_path)
    result = blank_result(case_id, fields)
    result["change_records"] = state["change_records"]
    dump_json(result_path, result)

    print("[run-supervisor] init 完成：case_id=%s，合约字段=%s" % (case_id, fields))
    print("[run-supervisor] state=%s result=%s" % (sp, result_path))
    return 0


# ---------------------------------------------------------------- phase

def resolve_evidence(work, ev):
    """证据路径解析：绝对路径直接用；相对路径先相对 work 再相对 cwd。"""
    candidates = [ev] if os.path.isabs(ev) else [
        os.path.join(work, ev), os.path.abspath(ev)]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)
    return None


def cmd_phase(args):
    if args.name not in PHASES:
        die("未知阶段 %r，合法阶段：%s" % (args.name, ", ".join(PHASES)))
    if args.status not in VALID_SET_STATUS:
        die("未知阶段状态 %r，合法值：%s" % (args.status, ", ".join(VALID_SET_STATUS)))
    work = os.path.abspath(args.work)
    state = load_state(work)

    evidence = []
    for ev in args.evidence or []:
        real = resolve_evidence(work, ev)
        if real is None:
            die("证据文件不存在，拒绝登记阶段 %s：%s" % (args.name, ev))
        evidence.append(real)
    if args.status == "done" and not evidence:
        die("阶段 %s 标记 done 必须提供至少一个真实存在的证据文件（--evidence）" % args.name)
    if args.status in ("failed", "skipped") and not evidence and not args.note:
        die("阶段 %s 标记 %s 需至少一个证据文件或一条 --note 说明原因"
            % (args.name, args.status))

    prev = state["phases"][args.name]
    if prev["status"] != "pending":
        # 幂等复跑：重复登记不静默覆盖，发出警告并记变更记录
        eprint("[run-supervisor][WARN] 阶段 %s 重复登记：原状态 %s（%s）将被覆盖为 %s"
               % (args.name, prev["status"], prev["ts"], args.status))
        add_change_record(
            state, "phase-duplicate",
            "阶段 %s 重复登记：%s -> %s；原证据=%s"
            % (args.name, prev["status"], args.status, prev["evidence"]),
        )

    state["phases"][args.name] = {
        "status": args.status,
        "ts": now_iso(),
        "evidence": evidence,
        "note": args.note or "",
    }
    add_change_record(
        state, "phase",
        "阶段 %s 登记为 %s；证据 %d 个；备注：%s"
        % (args.name, args.status, len(evidence), args.note or "（无）"),
    )
    save_state(work, state)
    sync_result(work, state)
    print("[run-supervisor] 阶段 %s -> %s（证据 %d 个）" % (args.name, args.status, len(evidence)))
    return 0


# ---------------------------------------------------------------- run

def cmd_run(args):
    work = os.path.abspath(args.work)
    state = load_state(work)
    name = args.name
    if not name or os.sep in name or name in (".", ".."):
        die("候选名 %r 不合法（需为简单目录名）" % name)
    cmd = list(args.command)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        die("run 需要实际命令：... run --work W --name N --timeout 秒 -- 命令")

    run_dir = os.path.join(work, "runs", name)
    os.makedirs(run_dir, exist_ok=True)
    stdout_path = os.path.join(run_dir, "stdout.txt")
    stderr_path = os.path.join(run_dir, "stderr.txt")
    meta_path = os.path.join(run_dir, "meta.json")

    if os.path.exists(meta_path):
        # 防止"重复执行覆盖好结果"：警告并留下变更记录，允许显式重跑
        eprint("[run-supervisor][WARN] 候选 %s 已有运行记录，本次运行将覆盖其日志：%s"
               % (name, run_dir))
        add_change_record(state, "run-rerun",
                          "候选 %s 被重复执行，旧日志被覆盖（%s）" % (name, run_dir))

    started = now_iso()
    t0 = time.time()
    timeout_hit = False
    exit_code = None
    try:
        with open(stdout_path, "w", encoding="utf-8", errors="replace") as out, \
             open(stderr_path, "w", encoding="utf-8", errors="replace") as err:
            proc = subprocess.run(cmd, stdout=out, stderr=err, timeout=args.timeout)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        timeout_hit = True
        with open(stderr_path, "a", encoding="utf-8", errors="replace") as err:
            err.write("\n[run-supervisor] TIMEOUT：超过 %s 秒，进程被终止。\n" % args.timeout)
    except OSError as exc:
        exit_code = 127
        with open(stderr_path, "a", encoding="utf-8", errors="replace") as err:
            err.write("\n[run-supervisor] 无法启动命令：%s\n" % exc)
    wall = time.time() - t0

    meta = {
        "name": name,
        "cmd": cmd,
        "exit_code": exit_code,
        "timeout": timeout_hit,
        "timeout_seconds": args.timeout,
        "wall_seconds": round(wall, 3),
        "started": started,
        "ended": now_iso(),
        "log_dir": os.path.abspath(run_dir),
    }
    dump_json(meta_path, meta)

    # 写入 runs 索引（同名替换），失败/超时也是证据，不中断流程
    state["runs"] = [r for r in state["runs"] if r["name"] != name]
    state["runs"].append(meta)
    ok = (exit_code == 0 and not timeout_hit)
    add_change_record(
        state, "run",
        "候选 %s 运行结束：exit_code=%s timeout=%s 墙钟 %.1fs（%s）"
        % (name, exit_code, timeout_hit, wall,
           "成功" if ok else "失败——记为证据，流程继续"),
    )
    save_state(work, state)
    sync_result(work, state)

    if ok:
        print("[run-supervisor] 候选 %s 成功（exit 0，%.1fs），日志：%s" % (name, wall, run_dir))
    else:
        print("[run-supervisor] 候选 %s 失败/超时（exit=%s timeout=%s，%.1fs）——已记为证据，"
              "请继续其他候选。日志：%s" % (name, exit_code, timeout_hit, wall, run_dir))
    return 0


# ---------------------------------------------------------------- status

def budget_snapshot(state):
    used = time.time() - state["start_epoch"]
    total = state["budget_seconds"]
    remaining = max(0.0, total - used)
    return used, remaining, (used / total if total > 0 else 1.0)


def next_action(state):
    for p in PHASES:
        if state["phases"][p]["status"] == "pending":
            return "完成阶段 %s 并用 phase 子命令登记证据" % p
    bad = [p for p in PHASES if state["phases"][p]["status"] in ("failed", "skipped")]
    if bad:
        return ("阶段 %s 为 failed/skipped：确认其证据与备注完整，然后填写合约字段并 finalize"
                % ",".join(bad))
    return "填写合约字段（含 field_notes）后运行 finalize"


def cmd_status(args):
    work = os.path.abspath(args.work)
    state = load_state(work)
    used, remaining, frac = budget_snapshot(state)
    report = {
        "case_id": state["case_id"],
        "budget_seconds": state["budget_seconds"],
        "used_seconds": round(used, 1),
        "remaining_seconds": round(remaining, 1),
        "budget_fraction": round(frac, 3),
        "budget_over_half": frac > 0.5,
        "phases": {p: state["phases"][p]["status"] for p in PHASES},
        "runs": [
            {"name": r["name"], "exit_code": r["exit_code"],
             "timeout": r["timeout"], "wall_seconds": r["wall_seconds"]}
            for r in state["runs"]
        ],
        "next_action": next_action(state),
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print("=== run-supervisor 状态台账 ===")
    print("case_id: %s" % report["case_id"])
    print("预算: 已用 %.0fs / %ds（%.0f%%），剩余 %.0fs"
          % (used, state["budget_seconds"], frac * 100, remaining))
    if frac > 0.5:
        print("!! 预算过半：停止开展新实验，先保存诚实的部分结果，再增量改进。")
    print("阶段:")
    for p in PHASES:
        ph = state["phases"][p]
        print("  %-10s %-7s %s %s" % (p, ph["status"], ph["ts"] or "", ph["note"]))
    print("运行:")
    if state["runs"]:
        for r in state["runs"]:
            print("  %-16s exit=%s timeout=%s %.1fs"
                  % (r["name"], r["exit_code"], r["timeout"], r["wall_seconds"]))
    else:
        print("  （尚无运行记录）")
    print("下一建议动作: %s" % report["next_action"])
    return 0


# ---------------------------------------------------------------- finalize

def recompute_status(state):
    """从过程证据重算总状态，不信任任何记忆/旧值：
    - 核心阶段（inventory/targets/run）全部未 done -> unable
    - 六阶段全 done 且无任何失败（阶段 failed/skipped、候选失败/超时） -> success
    - 其余（有 done 也有 failed/skipped，或有候选失败） -> partial
    """
    ph = state["phases"]
    core_done = any(ph[p]["status"] == "done" for p in CORE_PHASES)
    if not core_done:
        return "unable"
    all_done = all(ph[p]["status"] == "done" for p in PHASES)
    phase_bad = any(ph[p]["status"] in ("failed", "skipped") for p in PHASES)
    run_bad = any(r["timeout"] or r["exit_code"] != 0 for r in state["runs"])
    if all_done and not phase_bad and not run_bad:
        return "success"
    return "partial"


def lint_contract(result, fields, case_id):
    """合约 lint 规则（同时写入文档）：
    1. case_id 必须与 case.json 一致；
    2. output_contract 每个字段必须存在且非 null；
    3. 字段值为空占位（""、[]、{}）时，必须在 field_notes 中有该字段的非空说明，
       解释为何为空（例如"作者仓库缺失，无法获取原始数据"）；
    4. change_records 必须非空（全程变更可追溯）。
    """
    problems = []
    if result.get("case_id") != case_id:
        problems.append("case_id 不一致：result.json=%r，case.json=%r"
                        % (result.get("case_id"), case_id))
    notes = result.get("field_notes") or {}
    for f in fields:
        if f not in result:
            problems.append("合约字段缺失：%s" % f)
            continue
        v = result[f]
        if v is None:
            problems.append("合约字段仍为占位 null：%s（请填写诚实内容；确实无内容时"
                            "填空值并在 field_notes 中说明原因）" % f)
        elif v == "" or v == [] or v == {}:
            note = notes.get(f)
            if not (isinstance(note, str) and note.strip()):
                problems.append("合约字段为空值但缺少 field_notes 说明：%s" % f)
    if not result.get("change_records"):
        problems.append("change_records 为空：过程变更记录缺失")
    return problems


def cmd_finalize(args):
    case_id, fields = parse_contract(args.case)
    work = os.path.abspath(args.work)
    state = load_state(work)
    if state["case_id"] != case_id:
        eprint("[run-supervisor][WARN] state.json 的 case_id=%r 与 case.json=%r 不一致"
               % (state["case_id"], case_id))

    status = recompute_status(state)

    # 汇总不确定性：来自失败/跳过阶段与失败/超时候选的诚实声明
    uncertainties = []
    for p in PHASES:
        ph = state["phases"][p]
        if ph["status"] in ("failed", "skipped"):
            uncertainties.append("阶段 %s 为 %s：%s" % (p, ph["status"], ph["note"] or "无备注"))
        elif ph["status"] == "pending":
            uncertainties.append("阶段 %s 未完成（pending），对应结论缺失" % p)
    for r in state["runs"]:
        if r["timeout"]:
            uncertainties.append("候选 %s 运行超时（>%ss），其指标不可用" % (r["name"], r["timeout_seconds"]))
        elif r["exit_code"] != 0:
            uncertainties.append("候选 %s 运行失败（exit=%s），其指标不可用；stderr 见 %s"
                                 % (r["name"], r["exit_code"], r["log_dir"]))
    if not uncertainties:
        uncertainties.append("所有阶段完成、所有候选成功；剩余不确定性以 agent 在合约字段中的声明为准。")

    def mutate(result):
        result["status"] = status
        result["uncertainty"] = uncertainties

    add_change_record(
        state, "finalize",
        "finalize：从证据重算总状态=%s（核心阶段 done=%s；候选失败/超时=%s）"
        % (status,
           [p for p in CORE_PHASES if state["phases"][p]["status"] == "done"],
           [r["name"] for r in state["runs"] if r["timeout"] or r["exit_code"] != 0]),
    )
    save_state(work, state)
    result = sync_result(work, state, mutate=mutate)

    problems = lint_contract(result, fields, case_id)
    if problems:
        eprint("[run-supervisor][FAIL] 合约 lint 未通过，缺失/问题清单：")
        for p in problems:
            eprint("  - %s" % p)
        eprint("[run-supervisor] result.json 已按重算状态落盘（status=%s），"
               "修复上述问题后重新 finalize。" % status)
        return 1
    print("[run-supervisor] finalize PASS：status=%s，result=%s"
          % (status, state["result_path"]))
    return 0


# ---------------------------------------------------------------- main

def build_parser():
    ap = argparse.ArgumentParser(
        prog="supervisor.py",
        description="run-supervisor：复现任务过程质量控制状态机监督器（仅标准库）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="初始化状态机与合法 result.json 骨架")
    p.add_argument("--case", required=True, help="case.json 路径（如 /input/case.json）")
    p.add_argument("--work", required=True, help="工作目录（如 /app/work）")
    p.add_argument("--output", required=True, help="输出目录（如 /app/output）")
    p.add_argument("--budget-seconds", type=int, default=900, help="墙钟预算，默认 900 秒")
    p.add_argument("--force", action="store_true", help="覆盖已存在的 state.json/result.json")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("phase", help="登记阶段检查点（证据必须真实存在）")
    p.add_argument("--work", required=True)
    p.add_argument("--name", required=True, help="阶段名：" + "/".join(PHASES))
    p.add_argument("--status", required=True, help="done|failed|skipped")
    p.add_argument("--evidence", action="append", default=[],
                   help="证据文件路径（可重复；相对路径相对 work 解析）")
    p.add_argument("--note", default="", help="备注说明")
    p.set_defaults(func=cmd_phase)

    p = sub.add_parser("run", help="带超时的受控运行（失败/超时记为证据，不中断）")
    p.add_argument("--work", required=True)
    p.add_argument("--name", required=True, help="候选名（作为 runs/<name>/ 目录名）")
    p.add_argument("--timeout", type=int, required=True, help="单次运行超时秒数")
    p.add_argument("command", nargs=argparse.REMAINDER, help="-- 之后的实际命令")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("status", help="打印阶段状态、预算台账与下一建议动作")
    p.add_argument("--work", required=True)
    p.add_argument("--json", action="store_true", help="以 JSON 输出")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("finalize", help="从证据重算总状态并做合约 lint")
    p.add_argument("--case", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--output", required=True, help="用于校验 result.json 位置的一致性")
    p.set_defaults(func=cmd_finalize)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.cmd == "finalize":
        expected = os.path.join(os.path.abspath(args.output), "result.json")
        state = load_state(os.path.abspath(args.work))
        if os.path.abspath(state["result_path"]) != os.path.abspath(expected):
            eprint("[run-supervisor][WARN] --output 与 init 时的输出目录不一致：%s vs %s"
                   % (expected, state["result_path"]))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
