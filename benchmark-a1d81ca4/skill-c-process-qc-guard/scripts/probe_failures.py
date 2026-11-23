#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_failures.py — process-qc-guard 失败探针。

对 --work-dir 与 --output-dir 运行 12 类失败探针（定义见 references/failure_taxonomy.md）。
每命中一条写结构化失败样例：{probe_id, 题目/字段, 原始输出摘录, 原因, 建议修法, 可否机修}。
产物：probes_report.json + failure_samples.md（均写入 --work-dir）。
退出码 = min(命中总数, 100)；绝不因命中或畸形输入而崩溃。
"""
import argparse
import hashlib
import json
import os
import re
import sys

SCHEMA = "process-qc-guard/probe_failures@1"

HONESTY_RE = re.compile(r"未报告|未提及|无法判断|无法确定|未知|无数据|N/?A", re.I)
NUMBER_UNIT_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:°C|℃|K|MPa|GPa|%|wt|小时|分钟|h|min|s)\b")
PLACEHOLDER_RE = re.compile(r"TODO|FIXME|XXX|占位|待填|placeholder|示例答案|<填", re.I)
LOCATOR_RES = [re.compile(p) for p in
               (r"第\s*\d+\s*段", r"段\s*\d+", r"[pP]\.?\s*\d+", r"表\s*\d+",
                r"[Tt]able\s*\d+", r"行\s*\d+", r"para(?:graph)?\s*\d+", r"全文")]
QUESTION_RE = re.compile(r"^\s*(?:\d+\s*[.、)）]|Q\d+|问题\s*\d+)", re.M)


def sha256_file(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as exc:
        return None, "%s: %s" % (type(exc).__name__, exc)


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def excerpt(text, limit=120):
    text = str(text).replace("\n", " ")
    return text[:limit] + ("…" if len(text) > limit else "")


def hit(probe_id, target, raw, reason, suggestion, machine_fixable, severity):
    return {"probe_id": probe_id, "target": target, "excerpt": excerpt(raw),
            "reason": reason, "suggestion": suggestion,
            "machine_fixable": bool(machine_fixable), "severity": severity}


def extract_contract_fields(case_obj):
    if not isinstance(case_obj, dict):
        return []
    contract = case_obj.get("output_contract")
    if isinstance(contract, dict):
        for key in ("required_fields", "fields", "properties"):
            val = contract.get(key)
            if isinstance(val, list):
                return [str(x) for x in val]
            if isinstance(val, dict):
                return sorted(str(k) for k in val)
    if isinstance(contract, list):
        return [str(x) for x in contract]
    return []


def build_ctx(args):
    ctx = {"input_dir": args.input_dir, "work_dir": args.work_dir,
           "output_dir": args.output_dir}
    case, _ = read_json(os.path.join(args.input_dir, "case.json"))
    ctx["case"] = case
    ctx["contract_fields"] = extract_contract_fields(case)
    ctx["task_text"] = read_text(os.path.join(args.input_dir, "task.md"))
    ctx["answers"], ctx["answers_name"] = None, None
    for name in ("answers.json", "items.json"):
        doc, err = read_json(os.path.join(args.work_dir, name))
        if doc is not None:
            ctx["answers"], ctx["answers_name"] = doc, name
        elif err and os.path.exists(os.path.join(args.work_dir, name)):
            ctx.setdefault("malformed", []).append((name, err))
    ctx["result"], ctx["result_err"] = read_json(
        os.path.join(args.output_dir, "result.json"))
    ctx["items"] = []
    if isinstance(ctx["answers"], dict) and isinstance(ctx["answers"].get("items"), list):
        ctx["items"] = [it for it in ctx["answers"]["items"] if isinstance(it, dict)]
    return ctx


# ---------- 12 类探针 ----------

def p01_empty_answer(ctx):
    return [hit("P01", "空答案:%s" % it.get("id", "?"), it.get("answer"),
                "answer 为空或 null，构成未作答。",
                "补答；确实无法回答时填诚实标记（如'未报告'）并写 uncertainty。",
                False, "high")
            for it in ctx["items"] if it.get("answer") in (None, "")]


def p02_overlong_output(ctx):
    hits = []
    for it in ctx["items"]:
        ans = it.get("answer")
        if isinstance(ans, str) and len(ans) > 4000:
            hits.append(hit("P02", "超长输出:%s" % it.get("id"), ans,
                            "单字段超过 4000 字符，存在截断与跑题风险。",
                            "压缩为结论 + 证据锚点；长摘录移入 sources。", False, "medium"))
    for d in (ctx["work_dir"], ctx["output_dir"]):
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fn in files:
                p = os.path.join(root, fn)
                try:
                    if os.path.getsize(p) > 500 * 1024:
                        hits.append(hit("P02", "超大文件:%s" % p, "",
                                        "文件超过 500KB。", "拆分或精简产物。", True, "medium"))
                except OSError:
                    pass
    return hits


def p03_json_malformed(ctx):
    hits = [hit("P03", "JSON 畸形:%s" % name, err,
                "工作文件不是合法 JSON，下游无法解析。",
                "用 json.tool 定位并修复；或由 checkpoint 恢复上一版本。", True, "high")
            for name, err in ctx.get("malformed", [])]
    if ctx.get("result_err") and ctx["result"] is None:
        hits.append(hit("P03", "JSON 畸形:result.json", ctx["result_err"],
                        "result.json 不是合法 JSON。",
                        "重跑 init_run 重建骨架，再 export。", True, "high"))
    return hits


def p04_missing_evidence(ctx):
    return [hit("P04", "缺证据锚点:%s" % it.get("id", "?"), it.get("evidence"),
                "evidence 为空，答案无法追溯到材料位置。",
                "补证据锚点（如'第N段'/'表N'/'p.N'）；全文未见时填'全文检索未见'。",
                False, "medium")
            for it in ctx["items"] if it.get("evidence") in (None, "")]


def p05_honesty_value_mix(ctx):
    hits = []
    for it in ctx["items"]:
        ans = it.get("answer")
        if isinstance(ans, str) and HONESTY_RE.search(ans) and NUMBER_UNIT_RE.search(ans):
            hits.append(hit("P05", "诚实标记与数值混存:%s" % it.get("id"), ans,
                            "同一答案同时含诚实标记与具体数值，语义矛盾。",
                            "拆分：数值结论与'未报告'说明分字段或分句表达。", False, "low"))
    return hits


def p06_subquestion_missing(ctx):
    questions = set(QUESTION_RE.findall(ctx["task_text"] or ""))
    if questions and len(ctx["items"]) < len(questions):
        return [hit("P06", "子问漏答", "task 含 %d 问，items 仅 %d 条" % (len(questions), len(ctx["items"])),
                    "子问数量不足。",
                    "逐问核对 task.md 编号，补齐缺失子问的条目。", False, "medium")]
    return []


def p07_contract_missing_field(ctx):
    result = ctx["result"]
    if not isinstance(result, dict) or result.get("skeleton"):
        return []  # 骨架阶段豁免：export 后再校验
    hits = []
    for f in ctx["contract_fields"]:
        if f not in result or result.get(f) in (None, ""):
            hits.append(hit("P07", "契约缺字段:%s" % f, result.get(f),
                            "output_contract 要求的字段缺失或为 null。",
                            "补答；确实无法作答须保留 null 并在 uncertainty 说明。", False, "high"))
    return hits


def p08_status_contradiction(ctx):
    result = ctx["result"]
    if not isinstance(result, dict) or result.get("skeleton"):
        return []
    status = result.get("status", "")
    values = [result.get(f) for f in ctx["contract_fields"]]
    filled = [v for v in values if v not in (None, "")]
    if status == "成功" and len(filled) < len(values):
        return [hit("P08", "status 与内容矛盾", status,
                    "声明'成功'但存在空契约字段。",
                    "降级为'部分完成'并写明 status_reason；或补齐字段。", True, "high")]
    if status in ("无法判断", "拒答") and filled:
        return [hit("P08", "status 与内容矛盾", status,
                    "声明'%s'但已填具体答案。" % status,
                    "修正 status 或清空矛盾字段。", False, "high")]
    return []


def p09_locator_format(ctx):
    hits = []
    for it in ctx["items"]:
        ev = it.get("evidence")
        if isinstance(ev, str) and ev and not any(r.search(ev) for r in LOCATOR_RES):
            hits.append(hit("P09", "定位格式非法:%s" % it.get("id"), ev,
                            "证据锚点不匹配任何受支持定位格式（第N段/表N/p.N/行N/全文）。",
                            "改写为标准定位格式。", False, "low"))
    return hits


def p10_empty_citation(ctx):
    result = ctx["result"]
    if (isinstance(result, dict) and not result.get("skeleton")
            and result.get("status") == "成功"
            and not result.get("sources")):
        return [hit("P10", "引文为空:sources", "",
                    "status 为'成功'但 sources 为空。",
                    "回填 sources（材料文件名 + 定位）。", False, "low")]
    return []


def p11_placeholder(ctx):
    hits = []
    for it in ctx["items"]:
        ans = it.get("answer")
        if isinstance(ans, str) and PLACEHOLDER_RE.search(ans):
            hits.append(hit("P11", "疑似抄题漏改占位符:%s" % it.get("id"), ans,
                            "答案含 TODO/占位/示例答案 等占位痕迹。",
                            "替换为真实作答；T2 题卡须清空模板占位符。", False, "medium"))
    return hits


def p12_checkpoint_stale(ctx):
    hits = []
    d = os.path.join(ctx["work_dir"], "checkpoints")
    if not os.path.isdir(d):
        return hits
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        doc, err = read_json(os.path.join(d, fn))
        if not isinstance(doc, dict):
            continue
        for dep in doc.get("deps", []):
            p = dep.get("path")
            now = sha256_file(p) if p else None
            if now is None or (dep.get("sha256") and now != dep["sha256"]):
                hits.append(hit("P12", "检查点 STALE 未处理:%s" % doc.get("stage", fn),
                                "%s recorded=%s current=%s" % (p, dep.get("sha256"), now),
                                "依赖哈希已变化，产物可能基于过期输入。",
                                "重跑该阶段并 checkpoint save 刷新；再交付。", False, "medium"))
    return hits


PROBES = [p01_empty_answer, p02_overlong_output, p03_json_malformed,
          p04_missing_evidence, p05_honesty_value_mix, p06_subquestion_missing,
          p07_contract_missing_field, p08_status_contradiction,
          p09_locator_format, p10_empty_citation, p11_placeholder,
          p12_checkpoint_stale]


def write_reports(work_dir, hits):
    sev = {"high": 0, "medium": 0, "low": 0}
    for h in hits:
        sev[h["severity"]] = sev.get(h["severity"], 0) + 1
    report = {"schema": SCHEMA,
              "summary": {"total_hits": len(hits), "high": sev.get("high", 0),
                          "medium": sev.get("medium", 0), "low": sev.get("low", 0)},
              "hits": hits}
    tmp = os.path.join(work_dir, "probes_report.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, os.path.join(work_dir, "probes_report.json"))

    lines = ["# 失败样例报告", "",
             "- 命中总数：%d（high %d / medium %d / low %d）" % (
                 len(hits), sev.get("high", 0), sev.get("medium", 0), sev.get("low", 0)), ""]
    for h in hits:
        lines.append("## [%s] %s（%s）" % (h["probe_id"], h["target"], h["severity"]))
        lines.append("- 原始输出摘录：%s" % (h["excerpt"] or "（空）"))
        lines.append("- 原因：%s" % h["reason"])
        lines.append("- 建议修法：%s" % h["suggestion"])
        lines.append("- 可否机修：%s" % ("是" if h["machine_fixable"] else "否"))
        lines.append("")
    tmp = os.path.join(work_dir, "failure_samples.md.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    os.replace(tmp, os.path.join(work_dir, "failure_samples.md"))
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description="process-qc-guard 失败探针（12 类）。")
    ap.add_argument("--input-dir", default="/input", help="输入目录（默认 /input）")
    ap.add_argument("--work-dir", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--output-dir", default="/app/output", help="交付目录（默认 /app/output）")
    args = ap.parse_args(argv)

    hits = []
    try:
        os.makedirs(args.work_dir, exist_ok=True)
        ctx = build_ctx(args)
        for probe in PROBES:
            try:
                hits.extend(probe(ctx))
            except Exception as exc:
                hits.append(hit("P00", "探针内部异常:%s" % probe.__name__, str(exc),
                                "探针自身异常，已隔离。",
                                "检查对应输入文件格式。", False, "low"))
        report = write_reports(args.work_dir, hits)
        print(json.dumps({"ok": True, "summary": report["summary"],
                          "report": os.path.join(args.work_dir, "probes_report.json")},
                         ensure_ascii=False, indent=2))
    except Exception as exc:  # 绝不崩溃
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)},
                         ensure_ascii=False))
        return 0
    return min(len(hits), 100)


if __name__ == "__main__":
    sys.exit(main())
