#!/usr/bin/env python3
"""failure_classify.py — 故障分类器（离线，仅标准库）。

职责：读取一份固化的源响应材料（本地 JSON 文件），判断本次拉取是否成功；
若失败，归入六类故障之一，并给出处置策略与确定性退避计划。

故障分类（详见 references/failure-taxonomy.md）：
  rate_limit       限流           -> retry（可恢复重试）
  timeout          超时/材料不可读 -> retry（可恢复重试）
  parse_error      响应体损坏/截断 -> retry，重试耗尽后 skip+degrade
  source_revision  源快照结构漂移  -> block（阻断，需人工确认）
  missing_field    记录缺必要字段  -> skip_degrade（记录级跳过）
  empty_window     窗口内零条目    -> skip_degrade（非错误，完成但记 0 条）

离线模拟约定：材料 JSON 顶层若含 "_simulate_error": "<class>"，则视为
该次拉取真实发生了对应故障（用于演练 rate_limit/timeout 等无法在离线
环境自然发生的故障）。

CLI:
  python3 failure_classify.py <material.json>
输出：分类裁决 JSON（stdout）。
"""
import json
import os
import sys

# 确定性退避计划表（秒）。离线环境不真的 sleep，只把计划写进 retry_journal。
BACKOFF_SCHEDULE = {
    "rate_limit": [5, 30, 120],
    "timeout": [5, 30, 120],
    "parse_error": [5, 30, 120],
    "source_revision": [0],
    "missing_field": [0],
    "empty_window": [0],
}

# 处置策略：retry=可恢复重试；skip_degrade=跳过并降级；block=阻断待人工
STRATEGY = {
    "rate_limit": "retry",
    "timeout": "retry",
    "parse_error": "retry",
    "source_revision": "block",
    "missing_field": "skip_degrade",
    "empty_window": "skip_degrade",
}

MAX_ATTEMPTS = 3  # retry 类故障的最大尝试次数（含首次）

# 记录级必要字段（取 DOI/doi 任一、title 任一形式）
REQUIRED_FIELDS = ["doi", "title"]

SIMULATED_CLASSES = {"rate_limit", "timeout"}


def _verdict(ok, failure_class, detail, items=None, items_pointer=None,
             record_issues=None):
    return {
        "ok": ok,
        "failure_class": failure_class,
        "strategy": STRATEGY.get(failure_class),
        "backoff_schedule": BACKOFF_SCHEDULE.get(failure_class),
        "detail": detail,
        "items": items or [],
        # items 在源 JSON 中的指针前缀，用于拼 locator
        "items_pointer": items_pointer,
        # 记录级问题：[{"index": i, "failure_class": "missing_field",
        #              "missing": [...], "locator": "..."}]
        "record_issues": record_issues or [],
    }


def _extract_items(doc):
    """识别三种已知快照结构，返回 (items, items_pointer) 或 None。

    1) Crossref 风格: {"message": {"items": [...]}}
    2) Europe PMC 风格: {"resultList": {"result": [...]}}
    3) 简单风格: {"items": [...]} 或顶层 [...]
    """
    if isinstance(doc, list):
        return doc, ""
    if not isinstance(doc, dict):
        return None
    msg = doc.get("message")
    if isinstance(msg, dict) and isinstance(msg.get("items"), list):
        return msg["items"], "/message/items"
    rl = doc.get("resultList")
    if isinstance(rl, dict) and isinstance(rl.get("result"), list):
        return rl["result"], "/resultList/result"
    if isinstance(doc.get("items"), list):
        return doc["items"], "/items"
    return None


def _record_missing(rec):
    """返回该记录缺失的必要字段名列表（空列表 = 完整）。"""
    if not isinstance(rec, dict):
        return ["doi", "title"]
    missing = []
    doi = rec.get("DOI") or rec.get("doi")
    if not doi:
        missing.append("doi")
    title = rec.get("title") or rec.get("title_text")
    if isinstance(title, list):
        title = " ".join(str(t) for t in title if t)
    if not title:
        missing.append("title")
    return missing


def load_and_classify(path):
    """读取材料文件并分类。返回裁决 dict（见 _verdict）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        return _verdict(False, "timeout",
                        "material unreadable, treated as fetch timeout: %s" % e)

    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        return _verdict(False, "parse_error",
                        "JSON decode failed at line %d col %d: %s"
                        % (e.lineno, e.colno, e.msg))

    # 离线故障模拟钩子
    if isinstance(doc, dict) and doc.get("_simulate_error") in SIMULATED_CLASSES:
        sim = doc["_simulate_error"]
        return _verdict(False, sim, "simulated %s (offline hook)" % sim)

    extracted = _extract_items(doc)
    if extracted is None:
        keys = sorted(doc.keys()) if isinstance(doc, dict) else type(doc).__name__
        return _verdict(False, "source_revision",
                        "snapshot structure drifted; none of the known shapes "
                        "(message.items / resultList.result / items) found; "
                        "top-level keys: %s" % keys)

    items, pointer = extracted
    if len(items) == 0:
        return _verdict(True, "empty_window",
                        "window returned zero records (not an error)",
                        items=[], items_pointer=pointer)

    record_issues = []
    for i, rec in enumerate(items):
        missing = _record_missing(rec)
        if missing:
            record_issues.append({
                "index": i,
                "failure_class": "missing_field",
                "missing": missing,
                "locator": "%s/%d" % (pointer, i),
            })
    return _verdict(True, None, "ok", items=items, items_pointer=pointer,
                    record_issues=record_issues)


def main(argv):
    if len(argv) != 2:
        sys.stderr.write("usage: failure_classify.py <material.json>\n")
        return 2
    verdict = load_and_classify(argv[1])
    # items 可能很大，CLI 输出时截断，只留计数
    out = dict(verdict)
    out["item_count"] = len(out.pop("items"))
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
