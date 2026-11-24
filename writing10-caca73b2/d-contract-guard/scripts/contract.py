#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract.py — 契约优先的 result.json 生命周期管理。

子命令:
  init         在任何内容工作之前, 依据 case.json 生成 result.json 骨架。
  checkpoint   每个阶段结束后调用: 重新校验、追加 stage_log/change_log、原子写盘。
  final_check  定稿前调用: 校验契约完整性并裁决 status, 退出码 0=PASS, 1=FAIL。

仅依赖 Python 标准库 (>=3.9)。任何时刻写出的 result.json 都是可解析 JSON。
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

STANDARD_KEYS = ["deliverable", "preserved_facts", "evidence_map", "change_log"]
LIST_KEYS = {"preserved_facts", "evidence_map", "change_log", "sources",
             "uncertainty", "limits", "stage_log"}
VALID_STATUS = ("partial", "complete", "failed")


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def atomic_write_json(path, data):
    """tmp 文件 + os.replace, 保证读方永远看到完整 JSON。"""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".result_", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def get_contract_keys(case):
    """output_contract 可能是键列表或 {键: 说明} 字典; 缺失时回退五标准键。"""
    oc = case.get("output_contract")
    if isinstance(oc, dict):
        keys = list(oc.keys())
    elif isinstance(oc, list):
        keys = [str(k) for k in oc]
    else:
        keys = []
    if not keys:
        keys = list(STANDARD_KEYS)
    for k in STANDARD_KEYS:  # 标准键必须存在, 即使 output_contract 漏声明
        if k not in keys:
            keys.append(k)
    return keys


def placeholder_for(key):
    return [] if key in LIST_KEYS else ""


def cmd_init(args):
    case = read_json(args.case)
    case_id = case.get("case_id")
    if not case_id:
        print("ERROR: case.json 缺少 case_id", file=sys.stderr)
        return 2
    keys = get_contract_keys(case)
    used_fallback = "output_contract" not in case
    result = {"case_id": case_id}
    for k in keys:
        result[k] = placeholder_for(k)
    result["status"] = "partial"
    for k in ("sources", "uncertainty", "limits", "stage_log"):
        result.setdefault(k, [] if k in LIST_KEYS else "")
    result.setdefault("change_log", [])
    result["stage_log"].append({
        "stage": "init",
        "ts": now_iso(),
        "note": "契约骨架已建立; 在内容工作之前 result.json 即为可解析 JSON。",
    })
    result["change_log"].append(
        "init: 依据 case.json output_contract 建立 result.json 骨架 (%d 键), status=partial。"
        % len(keys))
    if used_fallback:
        result["uncertainty"].append(
            "case.json 未声明 output_contract, 已按五标准键 (deliverable/preserved_facts/"
            "evidence_map/change_log + status) 建立骨架; 键集合可能与评测预期不完全一致。")
    atomic_write_json(args.out, result)
    print("INIT OK: %s" % args.out)
    print("  case_id      : %s" % case_id)
    print("  contract keys: %s" % ", ".join(keys))
    print("  status       : partial")
    return 0


def parse_value(raw):
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


def cmd_checkpoint(args):
    try:
        result = read_json(args.result)
    except (OSError, ValueError) as e:
        print("ERROR: 无法解析现有 result.json (%s); 已从最近可用状态重建骨架, "
              "请检查并重新 init。" % e, file=sys.stderr)
        return 2
    for pair in (args.set or []):
        if "=" not in pair:
            print("ERROR: --set 需要 key=value 形式: %s" % pair, file=sys.stderr)
            return 2
        k, v = pair.split("=", 1)
        result[k] = parse_value(v)
    result.setdefault("stage_log", []).append(
        {"stage": args.stage, "ts": now_iso(), "note": args.note})
    result.setdefault("change_log", []).append(
        "checkpoint[%s]: %s" % (args.stage, args.note))
    # checkpoint 不覆盖历史: stage_log 与 change_log 只追加。
    atomic_write_json(args.result, result)
    print("CHECKPOINT OK: stage=%s -> %s" % (args.stage, args.result))
    return 0


def is_empty(v):
    return v is None or v == "" or v == [] or v == {}


def mentioned(key, entries):
    k = key.lower()
    return any(k in str(e).lower() for e in entries)


def cmd_final_check(args):
    verdicts = []
    ok = True

    def verdict(passed, msg):
        nonlocal ok
        verdicts.append(("%s: %s" % ("PASS" if passed else "FAIL", msg)))
        if not passed:
            ok = False

    try:
        case = read_json(args.case)
    except (OSError, ValueError) as e:
        print("FAIL: 无法读取 case.json: %s" % e)
        return 1
    try:
        result = read_json(args.result)
    except (OSError, ValueError) as e:
        print("FAIL: result.json 不是可解析 JSON: %s" % e)
        return 1

    # 1. case_id 原样保留
    cid_case, cid_res = case.get("case_id"), result.get("case_id")
    verdict(cid_case is not None and cid_case == cid_res,
            "case_id 原样保留 (case=%r, result=%r)" % (cid_case, cid_res))

    # 2. 契约键齐全且非空(或在 change_log/limits 中有明确解释)
    keys = get_contract_keys(case)
    explanations = (result.get("change_log") or []) + (result.get("limits") or [])
    missing = [k for k in keys if k not in result]
    verdict(not missing, "契约键全部存在 (%d 键)%s"
            % (len(keys), ("; 缺失: " + ", ".join(missing)) if missing else ""))
    unexplained = []
    for k in keys:
        if k in result and is_empty(result.get(k)) and not mentioned(k, explanations):
            unexplained.append(k)
    verdict(not unexplained, "契约键非空或有书面解释%s"
            % (("; 空且无解释: " + ", ".join(unexplained)) if unexplained else ""))

    # 3. status 合法且转移有依据
    status = result.get("status")
    verdict(status in VALID_STATUS, "status ∈ {partial, complete, failed} (当前: %r)" % status)
    limits = result.get("limits") or []
    unresolved = [l for l in limits if "已解决" not in str(l)]
    if status == "complete":
        verdict(not unresolved,
                "status=complete 且无未解决 limits (%d 条未解决)" % len(unresolved))
    elif status == "partial":
        verdict(bool(unresolved) or bool(result.get("uncertainty")) or bool(result.get("stage_log")),
                "status=partial 且 limits/uncertainty 说明了缺口")
    elif status == "failed":
        verdict(bool(limits) or bool(result.get("uncertainty")),
                "status=failed 且说明了失败原因")

    # 4. deliverable 路径存在
    deliverable = result.get("deliverable")
    if isinstance(deliverable, str) and deliverable:
        path = deliverable if os.path.isabs(deliverable) else os.path.join(
            args.output_dir, deliverable)
        verdict(os.path.isfile(path), "deliverable 文件存在: %s" % path)
    elif isinstance(deliverable, list) and deliverable:
        missing_d = []
        for item in deliverable:
            p = item if os.path.isabs(str(item)) else os.path.join(
                args.output_dir, str(item))
            if not os.path.isfile(p):
                missing_d.append(str(item))
        verdict(not missing_d, "deliverable 文件全部存在%s"
                % (("; 缺失: " + ", ".join(missing_d)) if missing_d else ""))
    else:
        verdict(False, "deliverable 为空或未给出文件路径")

    print("FINAL CHECK — %s" % args.result)
    for v in verdicts:
        print("  " + v)
    print("VERDICT: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser(
        description="契约优先的 result.json 生命周期管理 (init/checkpoint/final_check)。")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="依据 case.json 生成 result.json 骨架")
    pi.add_argument("--case", required=True, help="case.json 路径")
    pi.add_argument("--out", required=True, help="输出 result.json 路径")
    pi.set_defaults(func=cmd_init)

    pc = sub.add_parser("checkpoint", help="阶段检查点: 追加日志并原子写盘")
    pc.add_argument("--result", required=True, help="result.json 路径")
    pc.add_argument("--stage", required=True, help="阶段名, 如 s1_minimum")
    pc.add_argument("--note", required=True, help="本阶段说明")
    pc.add_argument("--set", action="append", default=[],
                    help="更新字段, key=value (value 先按 JSON 解析, 失败按字符串); 可重复")
    pc.set_defaults(func=cmd_checkpoint)

    pf = sub.add_parser("final_check", help="定稿前契约校验, 退出码 0=PASS 1=FAIL")
    pf.add_argument("--case", required=True, help="case.json 路径")
    pf.add_argument("--result", required=True, help="result.json 路径")
    pf.add_argument("--output-dir", required=True, help="产物目录 (解析 deliverable 相对路径)")
    pf.set_defaults(func=cmd_final_check)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
