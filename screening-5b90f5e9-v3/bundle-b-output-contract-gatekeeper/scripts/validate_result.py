#!/usr/bin/env python3
"""validate_result.py — 合同校验门（validate gate）。

交付前强制校验 result.json 是否合法、完整、诚实：
  V1 case_id 与输入探测一致
  V2 合同字段一个不少（不得删字段）
  V3 status 词表合法且为终态（completed/partial/failed；in_progress 不可交付）
  V4 诚实规则：completed 不允许 null_with_reason/pending 字段；
     partial 必须有非空 uncertainty（或 limits）说明；failed 必须有非空 reason
  V5 台账-结果一致性：result.json 的 null/非空 与台账 fill_state 必须吻合
  V6 result.json 与台账引用的本地产物路径必须真实存在
  V7 运行时最低保障字段就位（sources/uncertainty/change_records）

退出码：0=通过；2=用法/IO/内部错误；3=存在违规（交付被拦截）。
幂等：只读校验 + 重写校验报告，不改动 result.json 与台账。

仅使用 Python 标准库。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

FINAL_STATUSES = ("completed", "partial", "failed")
PATH_KEYS = {"path", "paths", "artifact", "artifacts", "file", "filepath",
             "file_path", "source_artifact"}
# sources/source 可能混有 DOI/标题，仅校验其中"看起来像路径"（含 / 且非 URL）的条目
LOOSE_PATH_KEYS = {"source", "sources"}


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def collect_local_paths(obj, key=None, acc=None):
    """递归收集疑似本地路径的字符串：路径语义的键，或以 /app/ /input/ ./ 开头的值。"""
    if acc is None:
        acc = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            collect_local_paths(v, key=k, acc=acc)
    elif isinstance(obj, list):
        for item in obj:
            collect_local_paths(item, key=key, acc=acc)
    elif isinstance(obj, str):
        s = obj.strip()
        if s.startswith(("http://", "https://", "doi:", "DOI:")):
            return acc
        kl = key.lower() if key else ""
        if kl in PATH_KEYS or s.startswith(("/app/", "/input/", "./")):
            acc.append((key, s))
        elif kl in LOOSE_PATH_KEYS and "/" in s:
            acc.append((key, s))
    return acc


def main(argv=None):
    ap = argparse.ArgumentParser(description="result.json 合同校验门")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--spec", default=None)
    ap.add_argument("--ledger", default=None)
    ap.add_argument("--result", default=None)
    ap.add_argument("--report", default=None, help="校验报告输出路径（默认 <output>/validation_report.json）")
    args = ap.parse_args(argv)

    try:
        spec_path = args.spec or os.path.join(args.work, "contract_spec.json")
        ledger_path = args.ledger or os.path.join(args.work, "fill_ledger.json")
        result_path = args.result or os.path.join(args.output, "result.json")
        report_path = args.report or os.path.join(args.output, "validation_report.json")

        checks = []  # (id, ok, detail)

        def check(cid, ok, detail):
            checks.append({"id": cid, "ok": bool(ok), "detail": detail})

        # --- 读取三件套 ---
        try:
            spec = load_json(spec_path)
        except Exception as e:
            spec = None
            check("V0_SPEC", False, f"contract_spec.json 不可读: {e!r}")
        try:
            result = load_json(result_path)
        except Exception as e:
            result = None
            check("V0_RESULT", False, f"result.json 不可读/非 JSON: {e!r}")
        ledger = None
        if os.path.isfile(ledger_path):
            try:
                ledger = load_json(ledger_path)
            except Exception as e:
                check("V0_LEDGER", False, f"fill_ledger.json 损坏: {e!r}")
        else:
            check("V0_LEDGER", False, f"台账缺失: {ledger_path}（禁止无台账交付）")

        if result is None or spec is None:
            return finish(checks, report_path, result_path, fatal=True)

        # --- V1 case_id 一致 ---
        check("V1_CASE_ID", result.get("case_id") == spec.get("case_id"),
              f"result.case_id={result.get('case_id')!r} vs spec.case_id={spec.get('case_id')!r}")

        # --- V2 合同字段齐全 ---
        expected = set(spec.get("contract_fields") or []) | {"case_id", "status"}
        missing = sorted(f for f in expected if f not in result)
        check("V2_FIELDS_PRESENT", not missing,
              "字段齐全" if not missing else f"缺失合同字段: {missing}")

        # --- V3 status 词表与终态 ---
        status = result.get("status")
        check("V3_STATUS_FINAL", status in FINAL_STATUSES,
              f"status={status!r}（终态词表 {FINAL_STATUSES}；in_progress 骨架不可交付）")

        # --- V5 台账-结果一致性（先做，供 V4 使用） ---
        ledger_states = {}
        if ledger is not None:
            mismatches = []
            for f, e in (ledger.get("fields") or {}).items():
                if f not in result:
                    continue
                state = e.get("fill_state")
                ledger_states[f] = state
                is_null = result.get(f) is None
                if state == "filled" and is_null:
                    mismatches.append(f"{f}: 台账=filled 但 result=null")
                elif state == "null_with_reason" and not is_null:
                    mismatches.append(f"{f}: 台账=null_with_reason 但 result 非空")
                elif state == "pending" and not is_null and f != "status":
                    mismatches.append(f"{f}: 台账=pending 但 result 已有值（忘 mark？）")
                if state == "null_with_reason" and not (e.get("reason") or "").strip():
                    mismatches.append(f"{f}: null_with_reason 缺 reason（静默空字段）")
            check("V5_LEDGER_CONSISTENT", not mismatches,
                  "台账与 result.json 一致" if not mismatches else "; ".join(mismatches))

        # --- V4 诚实规则 ---
        if status == "completed":
            bad = [f for f, s in ledger_states.items()
                   if s in ("null_with_reason", "pending") and f != "status"]
            null_untracked = [f for f in expected
                              if f not in ("case_id", "status") and f in result
                              and result.get(f) is None and ledger_states.get(f) != "filled"]
            bad = sorted(set(bad) | set(null_untracked))
            check("V4_HONESTY_COMPLETED", not bad,
                  "completed 且全部字段 filled" if not bad
                  else f"status=completed 不允许以下字段为空/pending: {bad}")
        elif status == "partial":
            unc = result.get("uncertainty")
            lim = result.get("limits")
            unc_ok = (isinstance(unc, list) and len(unc) > 0) or (isinstance(unc, str) and unc.strip())
            lim_ok = isinstance(lim, str) and lim.strip()
            check("V4_HONESTY_PARTIAL", bool(unc_ok or lim_ok),
                  "partial 且 uncertainty/limits 非空" if (unc_ok or lim_ok)
                  else "status=partial 必须有非空 uncertainty 或 limits 说明限制")
        elif status == "failed":
            reason = result.get("reason") or result.get("failure_reason")
            check("V4_HONESTY_FAILED", bool(isinstance(reason, str) and reason.strip()),
                  "failed 且 reason 非空" if reason else "status=failed 必须有非空 reason")

        # --- V6 引用路径真实存在 ---
        missing_paths = []
        for _k, p in collect_local_paths(result):
            if not os.path.exists(p):
                missing_paths.append(p)
        if ledger is not None:
            for f, e in (ledger.get("fields") or {}).items():
                src = e.get("source_artifact")
                if src and not os.path.exists(src):
                    missing_paths.append(f"{src} (ledger:{f})")
        check("V6_PATHS_EXIST", not missing_paths,
              "全部引用路径存在" if not missing_paths else f"路径不存在: {missing_paths}")

        # --- V7 运行时最低保障字段 ---
        min_missing = [f for f in ("sources", "uncertainty", "change_records") if f not in result]
        check("V7_RUNTIME_MINIMUM", not min_missing,
              "sources/uncertainty/change_records 就位" if not min_missing
              else f"缺运行时最低保障字段: {min_missing}")

        return finish(checks, report_path, result_path)
    except SystemExit:
        raise
    except Exception as e:
        print(f"FATAL: validate_result 内部错误: {e!r}", file=sys.stderr)
        return 2


def finish(checks, report_path, result_path, fatal=False):
    violations = [c for c in checks if not c["ok"]]
    report = {
        "report_version": "1.0",
        "generated_at": utcnow(),
        "generated_by": "validate_result.py",
        "result_under_test": result_path,
        "verdict": "PASS" if not violations else "FAIL",
        "checks": checks,
        "violation_count": len(violations),
    }
    os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
    tmp = report_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, report_path)
    for c in checks:
        print(f"[{'PASS' if c['ok'] else 'FAIL'}] {c['id']}: {c['detail']}")
    print(f"verdict={report['verdict']} violations={len(violations)} report={report_path}")
    return 3 if violations or fatal else 0


if __name__ == "__main__":
    sys.exit(main())
