#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""metric_registry.py -- 响应指标口径注册表构建与历史数据一致性校验。

从 case.json（可选）与历史实验 CSV 构建 metric_registry.json。每个响应指标登记：
  name / unit / method / direction(maximize|minimize|target) / acceptable_fluctuation

校验规则（发现任何问题都不崩溃，写入 uncertainties 与 checks）：
  - 指标列在历史 CSV 中缺失            -> check fail + uncertainty
  - 单位缺失或为空                     -> check fail + uncertainty（禁止猜单位）
  - direction 非法或缺失               -> 缺省 "maximize" 并记 uncertainty
  - acceptable_fluctuation 缺失        -> uncertainty（后续区间不得据此缩窄）
  - 历史数据中非数值单元格             -> 统计并记 uncertainty

仅用 Python 3 标准库，无网络。任何输入不得 traceback。

用法：
  python3 metric_registry.py --case case.json --csv history.csv \
      --factors temp_C,time_h --out metric_registry.json
  python3 metric_registry.py --csv history.csv --spec metrics.json --out out.json

指标规格优先级：--spec JSON 文件 > case.json 中的 "response_metrics" 字段 > 从 CSV 推断
（推断时把不在 --factors 列表里的数值列视为响应指标，单位记 unknown 并给出 uncertainty）。
"""
import argparse
import csv
import json
import os
import sys

DIRECTIONS = ("maximize", "minimize", "target")
MISSING = ("", "-", "na", "n/a", "nan", "none", "null", "?")


def load_json_safe(path):
    """读取 JSON；失败返回 (None, error_str)。"""
    if not path:
        return None, "未提供路径"
    if not os.path.isfile(path):
        return None, "文件不存在: %s" % path
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh), None
    except Exception as exc:  # noqa: BLE001 - 任何解析失败都要降级
        return None, "JSON 解析失败 %s: %s" % (path, exc)


def read_csv_safe(path):
    """读取 CSV，返回 (header, rows, error)。rows 为 dict 列表。"""
    if not path or not os.path.isfile(path):
        return None, None, "CSV 文件不存在: %s" % path
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            sample = fh.read(4096)
            fh.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample) if sample.strip() else csv.excel
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(fh, dialect=dialect)
            rows = [dict(r) for r in reader]
            header = reader.fieldnames or []
        return header, rows, None
    except Exception as exc:  # noqa: BLE001
        return None, None, "CSV 读取失败 %s: %s" % (path, exc)


def is_number(text):
    try:
        float(str(text).strip())
        return True
    except (TypeError, ValueError):
        return False


def normalize_metric(raw, defaults_source):
    """把一份指标规格规范化为注册表条目；返回 (entry, problems)。"""
    problems = []
    entry = {
        "name": None,
        "unit": None,
        "method": None,
        "direction": "maximize",
        "acceptable_fluctuation": None,
        "spec_source": defaults_source,
    }
    if not isinstance(raw, dict):
        problems.append("指标规格不是对象: %r" % (raw,))
        return entry, problems
    name = str(raw.get("name") or "").strip()
    if not name:
        problems.append("指标缺少 name 字段")
    entry["name"] = name or None
    unit = str(raw.get("unit") or "").strip()
    if not unit:
        problems.append("指标 %s 单位缺失；禁止猜测单位，相关数值比较不可信" % (name or "<unnamed>",))
        entry["unit"] = None
    else:
        entry["unit"] = unit
    method = str(raw.get("method") or "").strip()
    if not method:
        problems.append("指标 %s 测量方法未声明" % (name or "<unnamed>",))
        entry["method"] = None
    else:
        entry["method"] = method
    direction = str(raw.get("direction") or "").strip().lower()
    if direction not in DIRECTIONS:
        if direction:
            problems.append("指标 %s direction=%r 非法，缺省按 maximize 处理" % (name, direction))
        else:
            problems.append("指标 %s direction 缺失，缺省按 maximize 处理" % (name,))
    else:
        entry["direction"] = direction
    af = raw.get("acceptable_fluctuation")
    if af is None or (isinstance(af, str) and not af.strip()):
        problems.append("指标 %s 未声明 acceptable_fluctuation；波动是否异常将无法判定" % (name,))
        entry["acceptable_fluctuation"] = None
    else:
        if isinstance(af, (int, float)):
            entry["acceptable_fluctuation"] = {"type": "absolute", "value": af}
        elif isinstance(af, dict):
            entry["acceptable_fluctuation"] = af
        else:
            entry["acceptable_fluctuation"] = {"type": "text", "value": str(af)}
    if raw.get("target") is not None and entry["direction"] == "target":
        entry["target"] = raw.get("target")
    elif raw.get("target") is not None:
        entry["target"] = raw.get("target")
        problems.append("指标 %s 给了 target 但 direction 不是 target" % (name,))
    return entry, problems


def infer_metrics_from_csv(header, rows, factors):
    """无显式规格时，把非因子且整体可解析为数值的列当作响应指标。"""
    metrics = []
    for col in header:
        if col in factors:
            continue
        vals = [r.get(col, "") for r in rows]
        numeric = [v for v in vals if is_number(v)]
        if numeric and len(numeric) >= max(1, len(vals) // 2):
            metrics.append({"name": col, "unit": "", "method": "", "direction": "maximize"})
    return metrics


def build_registry(case, spec, header, rows, factors):
    checks = []
    uncertainties = []
    metrics = []

    source = None
    if spec:
        source = "--spec"
        raw_metrics = spec.get("response_metrics", spec if isinstance(spec, list) else [])
    elif isinstance(case, dict) and case.get("response_metrics"):
        source = "case.json:response_metrics"
        raw_metrics = case["response_metrics"]
    else:
        source = "inferred-from-csv"
        raw_metrics = infer_metrics_from_csv(header or [], rows or [], factors)
        uncertainties.append(
            "未提供显式指标规格，响应指标从 CSV 列推断；单位/方法/波动限均未知，"
            "任何跨实验数值比较都必须先人工确认口径"
        )
    if not isinstance(raw_metrics, list):
        raw_metrics = []
        uncertainties.append("指标规格不是列表，按空注册表处理")
    if not raw_metrics:
        uncertainties.append("注册表为空：未能识别任何响应指标")

    for raw in raw_metrics:
        entry, problems = normalize_metric(raw, source)
        metrics.append(entry)
        for p in problems:
            checks.append({"check": "spec", "metric": entry.get("name"), "status": "fail", "detail": p})
            uncertainties.append(p)
        if not problems:
            checks.append({"check": "spec", "metric": entry.get("name"), "status": "pass",
                           "detail": "单位/方法/方向/波动限齐全"})

    if header is None:
        uncertainties.append("历史 CSV 不可读，无法做列一致性校验")
        checks.append({"check": "csv_readable", "status": "fail", "detail": "历史 CSV 不可读"})
    else:
        checks.append({"check": "csv_readable", "status": "pass",
                       "detail": "读取 %d 行, 列: %s" % (len(rows), ", ".join(header))})
        for entry in metrics:
            name = entry.get("name")
            if not name:
                continue
            if name not in header:
                checks.append({"check": "column_present", "metric": name, "status": "fail",
                               "detail": "历史数据中缺少指标列 %s" % name})
                uncertainties.append("历史数据缺少指标列 %s；该指标暂无证据来源" % name)
                continue
            checks.append({"check": "column_present", "metric": name, "status": "pass",
                           "detail": "列 %s 存在" % name})
            bad = sum(1 for r in rows
                      if str(r.get(name, "")).strip().lower() in MISSING
                      or not is_number(r.get(name)))
            if bad:
                checks.append({"check": "numeric", "metric": name, "status": "fail",
                               "detail": "%d/%d 个单元格非数值或缺失" % (bad, len(rows))})
                uncertainties.append("指标 %s 有 %d 个非数值/缺失单元格" % (name, bad))
            else:
                checks.append({"check": "numeric", "metric": name, "status": "pass",
                               "detail": "%d 行全部为数值" % len(rows)})
        for f in factors:
            if f not in header:
                checks.append({"check": "factor_present", "factor": f, "status": "fail",
                               "detail": "历史数据缺少因子列 %s" % f})
                uncertainties.append("声明的因子 %s 不在历史数据中；代理模型无法使用该因子" % f)

    failed = sum(1 for c in checks if c.get("status") == "fail")
    status = "ok" if failed == 0 else ("degraded" if metrics else "empty")
    return {
        "schema_version": "1.0",
        "generated_by": "metric_registry.py",
        "spec_source": source,
        "factors": factors,
        "metrics": metrics,
        "validation": {
            "status": status,
            "n_checks": len(checks),
            "n_failed": failed,
            "checks": checks,
            "uncertainties": uncertainties,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="构建响应指标注册表并校验历史数据一致性")
    parser.add_argument("--case", help="case.json 路径（可选）")
    parser.add_argument("--csv", dest="csv_path", help="历史实验 CSV 路径（可选但强烈建议）")
    parser.add_argument("--spec", help="指标规格 JSON 文件（可选，优先级最高）")
    parser.add_argument("--factors", default="", help="逗号分隔的因子列名，用于从 CSV 推断响应指标")
    parser.add_argument("--out", default="metric_registry.json", help="输出路径")
    args = parser.parse_args(argv)

    out_path = args.out
    try:
        case, case_err = (load_json_safe(args.case) if args.case else (None, None))
        spec, spec_err = (load_json_safe(args.spec) if args.spec else (None, None))
        header, rows, csv_err = read_csv_safe(args.csv_path) if args.csv_path else (None, None, None)
        factors = [f.strip() for f in args.factors.split(",") if f.strip()]
        if not factors and isinstance(case, dict):
            raw_f = case.get("factors") or []
            factors = [str(f.get("name") if isinstance(f, dict) else f) for f in raw_f]

        registry = build_registry(case, spec, header, rows, factors)
        for err in (case_err, spec_err, csv_err):
            if err:
                registry["validation"]["uncertainties"].append(err)
        if registry["validation"]["uncertainties"] and registry["validation"]["status"] == "ok":
            registry["validation"]["status"] = "degraded"
    except Exception as exc:  # noqa: BLE001 - 最后一道防线：绝不 traceback
        registry = {
            "schema_version": "1.0",
            "generated_by": "metric_registry.py",
            "metrics": [],
            "validation": {"status": "error", "n_checks": 0, "n_failed": 0, "checks": [],
                           "uncertainties": ["脚本内部异常（已降级为空注册表）: %r" % (exc,)]},
        }

    try:
        out_dir = os.path.dirname(os.path.abspath(out_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(registry, fh, ensure_ascii=False, indent=2)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("写出 %s 失败: %s\n" % (out_path, exc))
        print(json.dumps(registry, ensure_ascii=False))
        return 2
    status = registry["validation"]["status"]
    sys.stderr.write("metric_registry: status=%s, metrics=%d, uncertainties=%d -> %s\n"
                     % (status, len(registry["metrics"]),
                        len(registry["validation"]["uncertainties"]), out_path))
    return 0 if status in ("ok", "degraded") else 1


if __name__ == "__main__":
    sys.exit(main())
