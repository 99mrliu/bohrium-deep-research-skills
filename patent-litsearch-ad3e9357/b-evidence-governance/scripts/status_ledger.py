#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""status_ledger.py — 法律状态台账与核验协议（登记优先）。

每条状态记录（JSONL，每行一条）字段：
  entity          : 专利/申请标识（公开号、申请号等，原样照录，不做同族臆测合并）
  status_value    : 授权 / 失效 / 撤回 / 驳回 / 审中 / 未知
  source_kind     : official_register / official_gazette / aggregation_page / inference
  query_date      : 查询日期 ISO YYYY-MM-DD（必填；所有状态结论必须携带）
  effective_date  : 状态生效日期（可选，未知则省略，不得编造）
  staleness       : 滞后备注（查询日期距今较久或来源本身滞后时必填）
  as_register_basis : 布尔，是否被用作登记依据（仅 official_register/gazette 可为 true）
  leads_only      : 布尔，aggregation_page 来源必须为 true（只能作线索并标注）
  downgraded      : 布尔，inference 来源必须为 true（推断状态必须降级标注）
  review_advice   : 人工复核建议（inference / 未知 状态必填）
  statement       : 可选，拟输出的状态结论文本（用于确定性措辞检查）
  note            : 可选备注

规则引擎（validate）强制：
  R-S1  aggregation_page 不得作为登记依据（as_register_basis=true 即违规），
        且必须 leads_only=true 标注为线索；
  R-S2  status_value=未知 时，statement 不得含确定性措辞
        （"已授权/专利权有效/已失效"等），且必须给 review_advice；
  R-S3  inference 来源必须 downgraded=true 且 review_advice 非空；
  R-S4  query_date 必填且为合法 ISO 日期；距今超过 180 天而无 staleness
        备注时给出警告（warning，不阻断）；
  R-S5  status_value 非"未知"的记录，source_kind 不得为 inference 之外再无
        官方来源支撑的裸推断以外的确定性结论——即非未知状态若来源是
        aggregation_page，要求 note 中声明"待官方登记复核"。
任何违例（violation）exit 1；warning 仅提示。

CLI：append / validate / show。仅依赖标准库。
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

STATUS_VALUES = {"授权", "失效", "撤回", "驳回", "审中", "未知"}
SOURCE_KINDS = {"official_register", "official_gazette", "aggregation_page", "inference"}
STALE_DAYS = 180  # 查询日期距今超过该天数需 staleness 备注

# 未知状态下禁止出现的确定性措辞（违反"未知纪律"）
FORBIDDEN_DETERMINISTIC = [
    "已授权", "获得授权", "专利权有效", "仍然有效", "维持有效",
    "已失效", "已经失效", "已过期", "确定有效", "确认有效",
    "确定失效", "明确失效", "必然有效", "无疑有效",
]


def _parse_date(s):
    try:
        return datetime.date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def validate_record(rec, index=None, today=None):
    """返回 (violations, warnings)。"""
    today = today or datetime.date.today()
    tag = "记录[%s]" % (index if index is not None else "?")
    violations, warnings = [], []
    if not isinstance(rec, dict):
        return ["%s: 不是 JSON 对象" % tag], []

    entity = rec.get("entity")
    if not isinstance(entity, str) or not entity.strip():
        violations.append("%s: entity 缺失或为空" % tag)
    sv = rec.get("status_value")
    if sv not in STATUS_VALUES:
        violations.append("%s: status_value=%r 非法，必须为 %s 之一"
                          % (tag, sv, sorted(STATUS_VALUES)))
    sk = rec.get("source_kind")
    if sk not in SOURCE_KINDS:
        violations.append("%s: source_kind=%r 非法，必须为 %s 之一"
                          % (tag, sk, sorted(SOURCE_KINDS)))

    qd = rec.get("query_date")
    qdate = _parse_date(qd)
    if qdate is None:
        violations.append("%s: query_date=%r 缺失或不是合法 ISO 日期（所有状态结论必须标查询日期）"
                          % (tag, qd))
    else:
        age = (today - qdate).days
        if age > STALE_DAYS and not (rec.get("staleness") or "").strip():
            warnings.append("%s: query_date 距今 %d 天（>%d 天），建议补 staleness 滞后备注"
                            % (tag, age, STALE_DAYS))
    ed = rec.get("effective_date")
    if ed is not None and _parse_date(ed) is None:
        violations.append("%s: effective_date=%r 不是合法 ISO 日期" % (tag, ed))

    # R-S1 聚合页纪律
    if sk == "aggregation_page":
        if rec.get("as_register_basis"):
            violations.append("%s: [R-S1] aggregation_page 不得作为登记依据"
                              "（聚合页只能作线索并标注）" % tag)
        if not rec.get("leads_only"):
            violations.append("%s: [R-S1] aggregation_page 来源必须 leads_only=true 标注为线索" % tag)
        if sv != "未知" and "待官方登记复核" not in (rec.get("note") or ""):
            warnings.append("%s: [R-S5] 聚合页给出的非未知状态，建议在 note 声明"
                            "'待官方登记复核'" % tag)
    elif rec.get("as_register_basis") and sk not in ("official_register", "official_gazette"):
        violations.append("%s: [R-S1] 仅 official_register/official_gazette 可作登记依据，"
                          "实际 source_kind=%s" % (tag, sk))

    # R-S2 未知纪律
    if sv == "未知":
        stmt = rec.get("statement") or ""
        for phrase in FORBIDDEN_DETERMINISTIC:
            if phrase in stmt:
                violations.append("%s: [R-S2] 状态为未知，statement 含确定性措辞 %r，"
                                  "必须改为不确定表述" % (tag, phrase))
        if not (rec.get("review_advice") or "").strip():
            violations.append("%s: [R-S2] 状态为未知时必须给出 review_advice"
                              "（如：到官方登记簿复核并记录查询日期）" % tag)

    # R-S3 推断降级
    if sk == "inference":
        if not rec.get("downgraded"):
            violations.append("%s: [R-S3] inference 来源必须 downgraded=true（降级标注）" % tag)
        if not (rec.get("review_advice") or "").strip():
            violations.append("%s: [R-S3] inference 来源必须给出 review_advice 人工复核建议" % tag)
    return violations, warnings


def load_ledger(path):
    records, errors = [], []
    p = Path(path)
    if not p.exists():
        return [], ["台账文件不存在: %s" % path]
    for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append((lineno, json.loads(line)))
        except json.JSONDecodeError as e:
            errors.append("第 %d 行: JSON 解析失败: %s" % (lineno, e))
    return records, errors


def cmd_validate(args):
    records, parse_errors = load_ledger(args.ledger)
    violations, warnings = list(parse_errors), []
    for lineno, rec in records:
        v, w = validate_record(rec, index=lineno)
        violations.extend(v)
        warnings.extend(w)
    for w in warnings:
        print("WARNING: " + w)
    if violations:
        print("法律状态台账核验失败，共 %d 处违规：" % len(violations))
        for v in violations:
            print("  - " + v)
        return 1
    print("法律状态台账核验通过：%d 条记录合规（%d 条警告）。"
          % (len(records), len(warnings)))
    return 0


def cmd_append(args):
    rec = {
        "entity": args.entity,
        "status_value": args.status_value,
        "source_kind": args.source_kind,
        "query_date": args.query_date,
        "as_register_basis": bool(args.as_register_basis),
        "leads_only": bool(args.leads_only),
        "downgraded": bool(args.downgraded),
    }
    if args.effective_date:
        rec["effective_date"] = args.effective_date
    if args.staleness:
        rec["staleness"] = args.staleness
    if args.review_advice:
        rec["review_advice"] = args.review_advice
    if args.statement:
        rec["statement"] = args.statement
    if args.note:
        rec["note"] = args.note
    violations, warnings = validate_record(rec)
    for w in warnings:
        print("WARNING: " + w)
    if violations:
        for v in violations:
            print("ERROR: " + v, file=sys.stderr)
        return 1
    with open(args.ledger, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("OK: 已追加状态记录 entity=%s status=%s source=%s query_date=%s"
          % (rec["entity"], rec["status_value"], rec["source_kind"], rec["query_date"]))
    return 0


def cmd_show(args):
    records, parse_errors = load_ledger(args.ledger)
    for e in parse_errors:
        print("PARSE-ERROR: " + e, file=sys.stderr)
    print("台账: %s（%d 条）" % (args.ledger, len(records)))
    for lineno, rec in records:
        print("  [行%d] %s | %s | %s | query_date=%s" % (
            lineno, rec.get("entity"), rec.get("status_value"),
            rec.get("source_kind"), rec.get("query_date")))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="法律状态台账与核验协议（登记优先）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_a = sub.add_parser("append", help="追加一条状态记录（先过规则引擎）")
    ap_a.add_argument("--ledger", required=True)
    ap_a.add_argument("--entity", required=True)
    ap_a.add_argument("--status-value", required=True, choices=sorted(STATUS_VALUES))
    ap_a.add_argument("--source-kind", required=True, choices=sorted(SOURCE_KINDS))
    ap_a.add_argument("--query-date", required=True, help="ISO YYYY-MM-DD")
    ap_a.add_argument("--effective-date", default=None)
    ap_a.add_argument("--staleness", default=None)
    ap_a.add_argument("--as-register-basis", action="store_true")
    ap_a.add_argument("--leads-only", action="store_true")
    ap_a.add_argument("--downgraded", action="store_true")
    ap_a.add_argument("--review-advice", default=None)
    ap_a.add_argument("--statement", default=None)
    ap_a.add_argument("--note", default=None)
    ap_a.set_defaults(func=cmd_append)

    ap_v = sub.add_parser("validate", help="规则引擎核验台账")
    ap_v.add_argument("--ledger", required=True)
    ap_v.set_defaults(func=cmd_validate)

    ap_s = sub.add_parser("show", help="打印台账概要")
    ap_s.add_argument("--ledger", required=True)
    ap_s.set_defaults(func=cmd_show)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
