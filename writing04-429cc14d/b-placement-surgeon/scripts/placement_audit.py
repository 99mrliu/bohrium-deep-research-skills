#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""placement_audit.py — placement-surgeon 阶段 2：引用位置审计（规则 P1–P6）。

仅使用 Python 标准库；确定性；无网络访问。

输入：
    --sentences FILE    claim_scan.py 生成的 sentences.jsonl
    --markers   FILE    claim_scan.py 生成的 markers.jsonl
    --intent    FILE    （可选）intent.jsonl：台账声明 {"marker": "[2]",
                        "supports": ["S005", ...]}，用于 P2；缺省时跳过 P2 并注明
    --out       DIR     输出目录，写出 placement_report.json 与 placement_report.md

规则速览（精确定义见 references/placement_rules.md）：
    P1 段末漂移      段内 ≥2 个不同事实论断（锚点集不相交）而唯一标记在段末
    P2 错挂邻句      标记所在句与台账声明的支撑句不一致（需 --intent）
    P3 图表注误挂    标记出现在图注/表注/脚注区
    P4 未覆盖论断    body 区 needs_support 句无标记且全段无任何标记
    P5 超距覆盖      一个标记覆盖句数 >3（标记句之后 ≥3 句）且中间出现新事实
    P6 标记先于命题  标记所在句无事实线索而同段下一句是事实句（倒装嫌疑）

优先级约定：P1 命中的段落不再重复报 P4（段内覆盖问题由 P1 统一报告）。

退出码：0 无 violation；1 存在 violation；2 参数/读文件错误。
"""

import argparse
import json
import os
import re
import sys

YEAR_RE = re.compile(r"(?:19|20)\d{2}")
PROPER_RE = re.compile(r"[A-Z][A-Za-z0-9-]{1,}")
NUMERIC_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|％|℃|°C|mg|μg|µg|kg|g|mL|ml|L|mmol|mol|mm|cm|km|"
    r"Hz|kDa|μM|mM|h|min|例|名|份|篇|种|个|家|项|株|剂|倍|周|天|岁|分|"
    r"万人次|万人|亿人|亿|万)|(?:19|20)\d{2}"
)

P5_MAX_TRAILING = 3  # 标记句之后允许自然延续的最大句数；超过即“跨 >3 句”


def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def anchors_of(text):
    """论断锚点：年份 + 拉丁专有名词。用于区分“不同事实论断”。"""
    return set(YEAR_RE.findall(text)) | set(PROPER_RE.findall(text))


def numbers_of(text):
    return set(m.group(0) for m in NUMERIC_RE.finditer(text))


def excerpt(text, limit=80):
    t = re.sub(r"\s+", " ", text).strip()
    return t if len(t) <= limit else t[: limit - 1] + "…"


def audit(sentences, markers, intent=None):
    by_id = {s["id"]: s for s in sentences}
    paragraphs = {}
    for s in sentences:
        paragraphs.setdefault(s["paragraph"], []).append(s)
    for pid in paragraphs:
        paragraphs[pid].sort(key=lambda s: s["char_start"])

    markers_by_sentence = {}
    for m in markers:
        markers_by_sentence.setdefault(m["sentence"], []).append(m)

    violations = []
    skipped = []
    p1_paragraphs = set()

    # ---- P1 段末漂移 -------------------------------------------------------
    for pid, sents in paragraphs.items():
        if sents[0]["zone"] != "body":
            continue
        factual = [s for s in sents if s["needs_support"]]
        if len(factual) < 2:
            continue
        para_markers = [m for s in sents for m in markers_by_sentence.get(s["id"], [])]
        if not para_markers:
            continue
        last_sid = sents[-1]["id"]
        if not all(m["sentence"] == last_sid for m in para_markers):
            continue
        # “不同事实论断”：存在两个锚点集非空且不相交的事实句
        anchor_sets = [(s, anchors_of(s["text"])) for s in factual]
        distinct = any(
            a1 and a2 and a1.isdisjoint(a2)
            for i, (s1, a1) in enumerate(anchor_sets)
            for (s2, a2) in anchor_sets[i + 1:]
        )
        if not distinct:
            continue  # 单一来源连续论述（如“该试验……”回指），段末标记合理
        p1_paragraphs.add(pid)
        mk = para_markers[0]
        violations.append({
            "rule": "P1",
            "severity": "major",
            "paragraph": pid,
            "sentences": [s["id"] for s in factual],
            "marker": mk["raw"],
            "location": {"line": mk["line"], "col": mk["col"]},
            "evidence": "；".join(excerpt(s["text"], 50) for s in factual),
            "suggestion": {
                "action": "split",
                "detail": "段末唯一标记 %s 无法同时锚定 %d 个不同论断；为每个独立"
                          "论断分别挂已核验来源，或把标记移到它真正支撑的那句。"
                          % (mk["raw"], len(factual)),
            },
        })

    # ---- P2 错挂邻句（需台账） ---------------------------------------------
    if intent is None:
        skipped.append({"rule": "P2", "reason": "未提供 intent.jsonl 台账，跳过 P2"})
    else:
        for entry in intent:
            raw = entry.get("marker")
            supports = set(entry.get("supports", []))
            hit = [m for m in markers if m["raw"] == raw]
            if not hit:
                violations.append({
                    "rule": "P2",
                    "severity": "minor",
                    "paragraph": None,
                    "sentences": [],
                    "marker": raw,
                    "location": None,
                    "evidence": "台账声明的标记 %s 在稿件中未找到" % raw,
                    "suggestion": {"action": "remove",
                                   "detail": "核对台账或删除该声明"},
                })
                continue
            for m in hit:
                if m["sentence"] not in supports:
                    violations.append({
                        "rule": "P2",
                        "severity": "major",
                        "paragraph": m["paragraph"],
                        "sentences": [m["sentence"]] + sorted(supports),
                        "marker": raw,
                        "location": {"line": m["line"], "col": m["col"]},
                        "evidence": "标记 %s 挂在 %s，台账声明支撑 %s"
                                    % (raw, m["sentence"], "、".join(sorted(supports))),
                        "suggestion": {"action": "move",
                                       "detail": "把标记移到台账声明的支撑句"},
                    })

    # ---- P3 图表注误挂 ------------------------------------------------------
    for m in markers:
        if m["zone"] in ("caption", "footnote"):
            violations.append({
                "rule": "P3",
                "severity": "major",
                "paragraph": m["paragraph"],
                "sentences": [m["sentence"]],
                "marker": m["raw"],
                "location": {"line": m["line"], "col": m["col"]},
                "evidence": "标记 %s 出现在%s区（第 %d 行）"
                            % (m["raw"], "图表注" if m["zone"] == "caption" else "脚注",
                               m["line"]),
                "suggestion": {
                    "action": "move",
                    "detail": "支撑正文论断的标记应挂回正文对应论断句；若该标记仅"
                              "服务于图注自身且正文已有等价引用，可移除",
                },
            })

    # ---- P4 未覆盖论断 ------------------------------------------------------
    for pid, sents in paragraphs.items():
        if sents[0]["zone"] != "body" or pid in p1_paragraphs:
            continue
        para_has_marker = any(
            markers_by_sentence.get(s["id"]) for s in sents
        )
        if para_has_marker:
            continue  # 段内已有标记：覆盖问题归 P1/P5 处理
        for s in sents:
            if s["needs_support"]:
                violations.append({
                    "rule": "P4",
                    "severity": "major",
                    "paragraph": pid,
                    "sentences": [s["id"]],
                    "marker": None,
                    "location": {"line": s["line_start"], "col": 1},
                    "evidence": "事实句无任何标记（线索：%s）：%s"
                                % ("/".join(s["cues"]), excerpt(s["text"])),
                    "suggestion": {
                        "action": "insert_mark",
                        "detail": "若文献表中存在对应的已核验来源则补挂；否则只在"
                                  "审计报告标注 [缺来源]，禁止为占位而虚构引用",
                    },
                })

    # ---- P5 超距覆盖 --------------------------------------------------------
    for pid, sents in paragraphs.items():
        if sents[0]["zone"] != "body":
            continue
        for idx, s in enumerate(sents):
            sms = markers_by_sentence.get(s["id"])
            if not sms:
                continue
            run = []
            for t in sents[idx + 1:]:
                if markers_by_sentence.get(t["id"]):
                    break
                run.append(t)
            if len(run) < P5_MAX_TRAILING:
                continue
            base_nums = numbers_of(s["text"])
            new_fact = None
            for t in run:
                if t["needs_support"] and numbers_of(t["text"]) - base_nums:
                    new_fact = t
                    break
            if new_fact is None:
                continue
            mk = sms[0]
            violations.append({
                "rule": "P5",
                "severity": "major",
                "paragraph": pid,
                "sentences": [s["id"]] + [t["id"] for t in run],
                "marker": mk["raw"],
                "location": {"line": mk["line"], "col": mk["col"]},
                "evidence": "标记 %s 之后连续 %d 句无新标记，且 %s 出现新事实：%s"
                            % (mk["raw"], len(run), new_fact["id"],
                               excerpt(new_fact["text"], 50)),
                "suggestion": {
                    "action": "split",
                    "detail": "单一标记覆盖 >3 句且中间出现新事实；为出现新数据/新"
                              "结论的论断句分别补挂对应来源",
                },
            })

    # ---- P6 标记先于命题 ----------------------------------------------------
    for pid, sents in paragraphs.items():
        if sents[0]["zone"] != "body":
            continue
        for idx, s in enumerate(sents[:-1]):
            sms = markers_by_sentence.get(s["id"])
            if not sms:
                continue
            nxt = sents[idx + 1]
            if (not s["needs_support"]) and nxt["needs_support"]:
                mk = sms[0]
                violations.append({
                    "rule": "P6",
                    "severity": "minor",
                    "paragraph": pid,
                    "sentences": [s["id"], nxt["id"]],
                    "marker": mk["raw"],
                    "location": {"line": mk["line"], "col": mk["col"]},
                    "evidence": "标记 %s 所在句无事实线索，同段下一句才是事实句：%s"
                                % (mk["raw"], excerpt(nxt["text"], 50)),
                    "suggestion": {
                        "action": "move",
                        "detail": "倒装嫌疑：标记可能先于其支撑的命题；人工确认后"
                                  "移到事实句末",
                    },
                })

    rule_order = {"P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5, "P6": 6}
    violations.sort(key=lambda v: (rule_order[v["rule"]],
                                   v["location"]["line"] if v["location"] else 0))
    return violations, skipped


def render_md(report):
    lines = []
    lines.append("# 引用位置审计报告（placement-surgeon）")
    lines.append("")
    st = report["stats"]
    lines.append("- 句子总数：%d（body %d / caption %d / footnote %d）"
                 % (st["sentences"], st["body"], st["caption"], st["footnote"]))
    lines.append("- 标记总数：%d" % st["markers"])
    lines.append("- 违规总数：%d" % len(report["violations"]))
    if report["skipped_rules"]:
        for sk in report["skipped_rules"]:
            lines.append("- 跳过规则：%s（%s）" % (sk["rule"], sk["reason"]))
    lines.append("")
    if report["violations"]:
        lines.append("| # | 规则 | 段落 | 句 | 标记 | 位置(行) | 证据摘录 | 建议动作 |")
        lines.append("|---|------|------|----|------|----------|----------|----------|")
        for i, v in enumerate(report["violations"], start=1):
            loc = str(v["location"]["line"]) if v["location"] else "-"
            lines.append("| %d | %s | %s | %s | %s | %s | %s | %s |" % (
                i, v["rule"], v["paragraph"] or "-",
                "、".join(v["sentences"]) or "-",
                v["marker"] or "-", loc,
                v["evidence"].replace("|", "\\|"),
                v["suggestion"]["action"],
            ))
    else:
        lines.append("未发现位置违规。")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="引用位置审计（placement-surgeon 阶段 2）")
    ap.add_argument("--sentences", required=True)
    ap.add_argument("--markers", required=True)
    ap.add_argument("--intent", default=None, help="可选 intent.jsonl 台账（用于 P2）")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    for p in (args.sentences, args.markers):
        if not os.path.isfile(p):
            print("错误：文件不存在：%s" % p, file=sys.stderr)
            return 2
    sentences = load_jsonl(args.sentences)
    markers = load_jsonl(args.markers)
    intent = None
    if args.intent:
        if not os.path.isfile(args.intent):
            print("错误：台账不存在：%s" % args.intent, file=sys.stderr)
            return 2
        intent = load_jsonl(args.intent)

    violations, skipped = audit(sentences, markers, intent)
    report = {
        "tool": "placement_audit.py",
        "stats": {
            "sentences": len(sentences),
            "body": sum(1 for s in sentences if s["zone"] == "body"),
            "caption": sum(1 for s in sentences if s["zone"] == "caption"),
            "footnote": sum(1 for s in sentences if s["zone"] == "footnote"),
            "markers": len(markers),
        },
        "skipped_rules": skipped,
        "violations": violations,
    }
    os.makedirs(args.out, exist_ok=True)
    jp = os.path.join(args.out, "placement_report.json")
    mp = os.path.join(args.out, "placement_report.md")
    with open(jp, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    with open(mp, "w", encoding="utf-8") as fh:
        fh.write(render_md(report))
    print(json.dumps({"report_json": jp, "report_md": mp,
                      "violations": len(violations)}, ensure_ascii=False))
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
