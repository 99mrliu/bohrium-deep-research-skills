#!/usr/bin/env python3
"""scaffold_result.py — 零分钟骨架（scaffold）。

开工即落一份合法的 result.json 骨架（status=in_progress、合同全部字段就位、占位 null），
并初始化填充台账 fill_ledger.json（全部字段 fill_state=pending，结构性字段 filled）。
此后每步由 fill_ledger.py 增量填充——保证任何时刻中断都有可交付物。

退出码：0=成功；2=用法/IO/内部错误；3=spec 不可用（缺 case_id 等）。
幂等：已存在的 result.json / fill_ledger.json 只做并集补全，绝不覆盖已有填充值。

仅使用 Python 标准库。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

STRUCTURAL_DEFAULTS = {
    "status": "in_progress",
    "sources": [],
    "uncertainty": [],
    "change_records": [],
}


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)  # 原子替换，避免中断留下半截文件


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成 result.json 零分钟骨架与填充台账")
    ap.add_argument("--spec", default=None, help="contract_spec.json 路径（默认 <work>/contract_spec.json）")
    ap.add_argument("--work", default="/app/work", help="中间产物目录")
    ap.add_argument("--output", default="/app/output", help="交付目录")
    ap.add_argument("--result", default=None, help="覆盖 result.json 路径")
    ap.add_argument("--ledger", default=None, help="覆盖 fill_ledger.json 路径")
    args = ap.parse_args(argv)

    try:
        spec_path = args.spec or os.path.join(args.work, "contract_spec.json")
        result_path = args.result or os.path.join(args.output, "result.json")
        ledger_path = args.ledger or os.path.join(args.work, "fill_ledger.json")

        if not os.path.isfile(spec_path):
            print(f"ERROR: spec 不存在: {spec_path}（先运行 contract_probe.py）", file=sys.stderr)
            return 3
        spec = load_json(spec_path)
        case_id = spec.get("case_id")
        if not case_id:
            print("ERROR: spec 缺 case_id，无法落骨架", file=sys.stderr)
            return 3
        contract_fields = list(spec.get("contract_fields") or [])

        # --- result.json 骨架（幂等并集） ---
        if os.path.isfile(result_path):
            result = load_json(result_path)
            created = False
        else:
            result = {}
            created = True

        result.setdefault("case_id", case_id)
        if result.get("case_id") != case_id:
            print(
                f"ERROR: 已存在 result.json 的 case_id={result.get('case_id')!r} 与 spec {case_id!r} 不一致",
                file=sys.stderr,
            )
            return 3
        for k, v in STRUCTURAL_DEFAULTS.items():
            result.setdefault(k, v)
        for f in contract_fields:
            if f in ("case_id", "status"):
                continue
            result.setdefault(f, None)  # 占位 null：fill_state=pending 见台账

        records = result.get("change_records")
        if isinstance(records, list) and not any(
            isinstance(r, dict) and r.get("change") == "skeleton_initialized" for r in records
        ):
            records.append(
                {
                    "ts": utcnow(),
                    "actor": "scaffold_result.py",
                    "change": "skeleton_initialized",
                    "detail": f"骨架{'新建' if created else '复核'}：{len(contract_fields)} 个合同字段就位，占位 null",
                }
            )
        dump_json(result_path, result)

        # --- fill_ledger.json 台账（幂等并集） ---
        if os.path.isfile(ledger_path):
            ledger = load_json(ledger_path)
        else:
            ledger = {
                "ledger_version": "1.0",
                "case_id": case_id,
                "created_at": utcnow(),
                "fields": {},
                "history": [],
            }
        ledger["case_id"] = case_id
        ledger["updated_at"] = utcnow()
        all_fields = ["case_id", "status", "sources", "uncertainty", "change_records"] + [
            f for f in contract_fields if f not in ("case_id", "status")
        ]
        for f in all_fields:
            if f not in ledger["fields"]:
                structural = f in ("case_id", "status", "sources", "uncertainty", "change_records")
                ledger["fields"][f] = {
                    "fill_state": "filled" if structural and f == "case_id" else (
                        "filled" if structural and f in ("sources", "uncertainty", "change_records") else "pending"
                    ),
                    "source_artifact": None,
                    "reason": "structural_default" if structural and f != "status" else None,
                    "updated_at": utcnow(),
                }
        if not any(h.get("event") == "ledger_initialized" for h in ledger["history"]):
            ledger["history"].append(
                {"ts": utcnow(), "actor": "scaffold_result.py", "event": "ledger_initialized"}
            )
        dump_json(ledger_path, ledger)

        print(f"OK: 骨架就位 result={result_path} ledger={ledger_path} fields={len(all_fields)}")
        return 0
    except SystemExit:
        raise
    except Exception as e:
        print(f"FATAL: scaffold_result 内部错误: {e!r}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
