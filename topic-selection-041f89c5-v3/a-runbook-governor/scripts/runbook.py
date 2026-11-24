#!/usr/bin/env python3
"""runbook.py — 选题评估任务的运行治理器（阶段状态机 + 预算台账 + 断点校验）。

设计目标：无论运行在何时何因被中断，/app/output/result.json 永远是
契约合法的（case_id 逐字一致、output_contract 字段齐全、status 诚实）。
Agent 在每个阶段边界调用本脚本；脚本只做确定性检查，不做内容判断。

子命令：
  init        读 case.json，初始化 run_state.json，并立即写出 result.json 骨架
  enter       进入指定阶段（同一时间只能有一个阶段处于 active）
  exit        退出当前阶段，必须附一句可审计的进展说明
  tick        登记已消耗的模型请求数（Agent 自报，诚实台账）
  checkpoint  机检 result.json 契约合规性并留存带时间戳的快照
  status      打印预算健康度（用量比决定降级级别 L0/L1/L2）
  triage      预算危急时强制产出合法的 partial 结果
  finalize    收口：success 要求契约字段全部非空；partial/failed 必须给理由

退出码：0 正常；1 校验或状态违例（错误明细打印到 stdout，供 Agent 阅读）。
仅依赖 Python 3 标准库。
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

PHASES = [
    "intake",        # 输入清点 + 契约骨架
    "question",      # 研究问题结构化
    "retrieve",      # 检索与筛选留痕
    "extract",       # 证据提取与台账
    "synthesize",    # 综合四项交付（比较/创新/可行性/不确定性）
    "closeout",      # 回填 result.json 与终检
]
LEGAL_STATUS = {"success", "partial", "failed", "in_progress"}


def load_json(path, what):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail([f"{what} 不存在: {path}"])
    except json.JSONDecodeError as exc:
        fail([f"{what} 不是合法 JSON ({path}): {exc}"])


def save_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2)
                          + "\n", encoding="utf-8")


def fail(errors):
    print(json.dumps({"ok": False, "errors": errors},
                     ensure_ascii=False, indent=2))
    sys.exit(1)


def contract_fields(contract):
    """output_contract 容许三种形态：对象（键即字段名）、数组（字段名）、
    字符串（每行一个字段名，忽略空行与 # 注释）。"""
    if isinstance(contract, dict):
        return list(contract.keys())
    if isinstance(contract, list):
        return [str(x) for x in contract]
    if isinstance(contract, str):
        return [ln.strip() for ln in contract.splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
    fail(["output_contract 形态不支持（需为对象/数组/字符串）"])


def is_empty(value):
    return value is None or value == "" or value == [] or value == {}


def load_state(args):
    return load_json(args.state, "run_state.json")


def save_state(args, state):
    save_json(args.state, state)


def validate_result(result, fields, case_id, require_filled):
    errors = []
    if not isinstance(result, dict):
        return ["result.json 顶层必须是对象"]
    if result.get("case_id") != case_id:
        errors.append(
            f"case_id 不一致: result.json={result.get('case_id')!r} "
            f"case.json={case_id!r}（必须逐字一致）")
    status = result.get("status")
    if status not in LEGAL_STATUS:
        errors.append(f"status={status!r} 非法，只允许 "
                      f"{sorted(LEGAL_STATUS)}")
    for f in fields:
        if f not in result:
            errors.append(f"缺契约字段: {f}")
        elif require_filled and is_empty(result[f]):
            errors.append(f"契约字段为空（status=success 不允许）: {f}")
    return errors


def cmd_init(args):
    case = load_json(args.case, "case.json")
    case_id = case.get("case_id")
    if not case_id:
        fail(["case.json 缺少 case_id"])
    contract = case.get("output_contract")
    if contract is None:
        fail(["case.json 缺少 output_contract"])
    fields = contract_fields(contract)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "result.json"
    skeleton = {"case_id": case_id, "status": "in_progress"}
    for f in fields:
        if f not in skeleton:
            skeleton[f] = None
    skeleton["_runbook"] = {
        "note": "骨架由 runbook init 生成；只回填，不重构；"
                "交付前移除或保留本辅助字段均可（以契约为准）。",
        "created_epoch": time.time(),
    }
    save_json(result_path, skeleton)

    state = {
        "case_id": case_id,
        "contract_fields": fields,
        "phases": {p: {"entered": None, "exited": None, "note": None}
                   for p in PHASES},
        "active_phase": None,
        "budget": {
            "requests_cap": args.requests,
            "seconds_cap": args.seconds,
            "requests_used": 0,
            "started_epoch": time.time(),
        },
        "result_path": str(result_path),
        "case_path": str(Path(args.case).resolve()),
        "checkpoints": [],
        "events": [{"t": time.time(), "event": "init",
                    "detail": f"{len(fields)} 个契约字段"}],
    }
    save_state(args, state)
    print(json.dumps({"ok": True, "result_skeleton": str(result_path),
                      "contract_fields": fields}, ensure_ascii=False))


def cmd_enter(args):
    state = load_state(args)
    if args.phase not in state["phases"]:
        fail([f"未知阶段 {args.phase!r}；合法阶段: {PHASES}"])
    if state["active_phase"] is not None:
        fail([f"阶段 {state['active_phase']} 仍 active，先 exit 再 enter"])
    state["phases"][args.phase]["entered"] = time.time()
    state["active_phase"] = args.phase
    state["events"].append({"t": time.time(), "event": "enter",
                            "detail": args.phase})
    save_state(args, state)
    print(json.dumps({"ok": True, "active_phase": args.phase},
                     ensure_ascii=False))


def cmd_exit(args):
    state = load_state(args)
    if state["active_phase"] != args.phase:
        fail([f"当前 active 阶段是 {state['active_phase']!r}，"
              f"不能 exit {args.phase!r}"])
    if not args.note or len(args.note.strip()) < 8:
        fail(["exit 必须附 --note（≥8 字符的可审计进展说明）"])
    state["phases"][args.phase]["exited"] = time.time()
    state["phases"][args.phase]["note"] = args.note.strip()
    state["active_phase"] = None
    state["events"].append({"t": time.time(), "event": "exit",
                            "detail": f"{args.phase}: {args.note.strip()}"})
    save_state(args, state)
    print(json.dumps({"ok": True, "exited": args.phase},
                     ensure_ascii=False))


def cmd_tick(args):
    state = load_state(args)
    if args.n <= 0:
        fail(["--n 必须为正整数"])
    state["budget"]["requests_used"] += args.n
    state["events"].append({"t": time.time(), "event": "tick",
                            "detail": f"+{args.n} requests"})
    save_state(args, state)
    print(json.dumps({"ok": True,
                      "requests_used": state["budget"]["requests_used"]},
                     ensure_ascii=False))


def budget_health(state):
    b = state["budget"]
    elapsed = time.time() - b["started_epoch"]
    req_ratio = b["requests_used"] / max(1, b["requests_cap"])
    time_ratio = elapsed / max(1, b["seconds_cap"])
    usage = max(req_ratio, time_ratio)
    if usage < 0.6:
        level = "L0"
        advice = "正常运行"
    elif usage < 0.8:
        level = "L1"
        advice = "停止新增检索，用已收集证据进入综合"
    else:
        level = "L2"
        advice = "立即 triage 并 finalize partial，先保契约合法"
    return {
        "level": level, "advice": advice,
        "requests_used": b["requests_used"],
        "requests_cap": b["requests_cap"],
        "elapsed_seconds": round(elapsed, 1),
        "seconds_cap": b["seconds_cap"],
        "usage_ratio": round(usage, 3),
    }


def cmd_status(args):
    state = load_state(args)
    health = budget_health(state)
    health["active_phase"] = state["active_phase"]
    health["phases_done"] = [p for p, v in state["phases"].items()
                             if v["exited"] is not None]
    print(json.dumps({"ok": True, "budget": health},
                     ensure_ascii=False, indent=2))


def cmd_checkpoint(args):
    state = load_state(args)
    result = load_json(state["result_path"], "result.json")
    errors = validate_result(result, state["contract_fields"],
                             state["case_id"], require_filled=False)
    if errors:
        fail(errors)
    cp_dir = Path(args.state).parent / "checkpoints"
    cp_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    phase = state["active_phase"] or "idle"
    cp_path = cp_dir / f"result_{stamp}_{phase}.json"
    shutil.copyfile(state["result_path"], cp_path)
    state["checkpoints"].append(str(cp_path))
    state["events"].append({"t": time.time(), "event": "checkpoint",
                            "detail": cp_path.name})
    save_state(args, state)
    print(json.dumps({"ok": True, "checkpoint": str(cp_path)},
                     ensure_ascii=False))


def cmd_triage(args):
    state = load_state(args)
    result = load_json(state["result_path"], "result.json")
    for f in state["contract_fields"]:
        if f not in result:
            result[f] = None
    result["status"] = "partial"
    note = ("triage: 预算（请求数或时间）耗尽前强制收口；"
            "空字段 = 未能完成的部分，原因见本说明。")
    unc = result.get("uncertainties")
    if isinstance(unc, list):
        unc.append(note)
    elif unc is None and "uncertainties" in state["contract_fields"]:
        result["uncertainties"] = [note]
    save_json(state["result_path"], result)
    state["events"].append({"t": time.time(), "event": "triage",
                            "detail": "forced partial"})
    save_state(args, state)
    print(json.dumps({"ok": True, "status": "partial",
                      "result": state["result_path"]},
                     ensure_ascii=False))


def cmd_finalize(args):
    state = load_state(args)
    if args.status not in ("success", "partial", "failed"):
        fail(["--status 只允许 success|partial|failed"])
    if args.status in ("partial", "failed") and \
            (not args.reason or len(args.reason.strip()) < 8):
        fail([f"status={args.status} 必须附 --reason（≥8 字符，说明"
              f"缺什么、为什么）"])
    result = load_json(state["result_path"], "result.json")
    result["status"] = args.status
    save_json(state["result_path"], result)
    errors = validate_result(result, state["contract_fields"],
                             state["case_id"],
                             require_filled=(args.status == "success"))
    if errors:
        fail(errors)
    state["events"].append({"t": time.time(), "event": "finalize",
                            "detail": args.status})
    state["finalized"] = {"status": args.status,
                          "reason": args.reason, "t": time.time()}
    save_state(args, state)
    print(json.dumps({"ok": True, "final_status": args.status,
                      "result": state["result_path"]},
                     ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", required=True,
                    help="run_state.json 路径（置于 /app/work）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="初始化状态与 result.json 骨架")
    p.add_argument("--case", required=True, help="/input/case.json 路径")
    p.add_argument("--output", required=True, help="/app/output 路径")
    p.add_argument("--requests", type=int, default=64, help="模型请求预算")
    p.add_argument("--seconds", type=int, default=900, help="秒级时间预算")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("enter", help="进入阶段")
    p.add_argument("--phase", required=True, choices=PHASES)
    p.set_defaults(fn=cmd_enter)

    p = sub.add_parser("exit", help="退出阶段（附进展说明）")
    p.add_argument("--phase", required=True, choices=PHASES)
    p.add_argument("--note", required=True)
    p.set_defaults(fn=cmd_exit)

    p = sub.add_parser("tick", help="登记模型请求消耗")
    p.add_argument("--n", type=int, required=True)
    p.set_defaults(fn=cmd_tick)

    p = sub.add_parser("status", help="预算健康度")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("checkpoint", help="契约机检 + 快照")
    p.set_defaults(fn=cmd_checkpoint)

    p = sub.add_parser("triage", help="预算危急时强制合法 partial")
    p.set_defaults(fn=cmd_triage)

    p = sub.add_parser("finalize", help="收口校验")
    p.add_argument("--status", required=True,
                   choices=["success", "partial", "failed"])
    p.add_argument("--reason", default="")
    p.set_defaults(fn=cmd_finalize)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
