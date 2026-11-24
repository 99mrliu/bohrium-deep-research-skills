#!/usr/bin/env python3
"""build_matrix.py — 由 claims + spans + audit_report 生成人类可读制品：

  evidence_matrix.csv  claim_id × record_id 覆盖矩阵（单元格=该记录下有效证据条数）
  coverage.md          按综述小节组织的论断-证据对照表（span 定位 + quote 摘要）
  conflict_matrix.md   冲突证据矩阵（来自 audit_report 中 registered 的冲突对）

这些制品对应 result.json 的 evidence_matrix / product 附件。
退出码：0=成功；2=输入缺失或无法解析；3=校验失败。
"""
import argparse
import csv
import json
import os
import re
import sys

STRENGTH_LABEL = {"fact": "事实", "inference": "推断", "uncertain": "不确定"}


def normalize_ws(s):
    return re.sub(r"\s+", " ", s).strip()


def fail_input(msg):
    print(f"[E-INPUT] {msg}", file=sys.stderr)
    sys.exit(2)


def load_json(path, what):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        fail_input(f"无法读取{what} {path}：{e}")
    except json.JSONDecodeError as e:
        fail_input(f"{what}不是合法 JSON：{path}：{e}")


def load_claims(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for ln, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    fail_input(f"claims.jsonl 第 {ln} 行不是合法 JSON：{e}")
    except OSError as e:
        fail_input(f"无法读取 claims.jsonl {path}：{e}")
    if not rows:
        fail_input(f"claims.jsonl 为空（{path}）。")
    return rows


def short(text, limit=60):
    t = normalize_ws(text)
    return t if len(t) <= limit else t[: limit - 1] + "…"


def main():
    ap = argparse.ArgumentParser(
        description="生成 evidence_matrix.csv / coverage.md / conflict_matrix.md。")
    ap.add_argument("--claims", required=True, help="claims.jsonl 路径")
    ap.add_argument("--spans", required=True, help="spans.json 路径")
    ap.add_argument("--audit", required=True, help="audit_claims.py 输出的 audit_report.json")
    ap.add_argument("--out-dir", required=True, help="制品输出目录")
    args = ap.parse_args()

    claims = load_claims(args.claims)
    spans_doc = load_json(args.spans, "spans.json")
    spans = {k: v for k, v in spans_doc.items() if not k.startswith("__")}
    audit = load_json(args.audit, "audit_report.json")
    if not isinstance(audit, dict) or "claims" not in audit:
        fail_input("audit_report.json 结构不完整（缺少 claims 字段）。")
    audit_by_id = {c.get("claim_id"): c for c in audit.get("claims", [])}

    os.makedirs(args.out_dir, exist_ok=True)

    # ---------- evidence_matrix.csv ----------
    record_ids = sorted({
        ev.get("record_id", "")
        for c in claims if isinstance(c, dict)
        for ev in c.get("evidence", []) if isinstance(ev, dict)
    } - {""})
    csv_path = os.path.join(args.out_dir, "evidence_matrix.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["claim_id", "strength", "section"] + record_ids)
        for c in claims:
            if not isinstance(c, dict):
                continue
            counts = {r: 0 for r in record_ids}
            for ev in c.get("evidence", []):
                rid = ev.get("record_id", "")
                sid = ev.get("span_id", "")
                # 只统计字面核验通过的证据（与 audit C2 同规则重算）
                if rid in counts and sid in spans and \
                        normalize_ws(ev.get("quote", "")) in normalize_ws(spans[sid].get("text", "")):
                    counts[rid] += 1
            w.writerow([c.get("claim_id", ""), c.get("strength", ""),
                        c.get("section", "")] + [counts[r] for r in record_ids])

    # ---------- coverage.md ----------
    sections = {}
    for c in claims:
        if isinstance(c, dict):
            sections.setdefault(c.get("section") or "（未分节）", []).append(c)
    lines = [
        "# 论断-证据对照表（coverage）",
        "",
        "> 由 build_matrix.py 依据 claims.jsonl × spans.json 生成；"
        "每条论断的 span 定位与 quote 摘要可回到原文复核。",
        "",
    ]
    for sec in sorted(sections):
        lines.append(f"## {sec}")
        lines.append("")
        for c in sections[sec]:
            cid = c.get("claim_id", "")
            st = c.get("strength", "")
            a = audit_by_id.get(cid, {})
            v = a.get("evidence_valid", 0)
            t = a.get("evidence_total", 0)
            lines.append(f"### {cid}（{STRENGTH_LABEL.get(st, st)}；有效证据 {v}/{t}）")
            lines.append("")
            lines.append(f"- 论断：{c.get('text', '')}")
            if c.get("note"):
                lines.append(f"- 备注：{c['note']}")
            if not c.get("evidence"):
                lines.append("- 证据：无（仅 uncertain 论断允许）")
            for ev in c.get("evidence", []):
                sid = ev.get("span_id", "")
                loc = spans.get(sid, {}).get("locator", "?")
                src = spans.get(sid, {}).get("source", "?")
                ok = sid in spans and normalize_ws(ev.get("quote", "")) in \
                    normalize_ws(spans[sid].get("text", ""))
                mark = "✓" if ok else "✗（回链失败）"
                lines.append(f"- 证据 {mark}：{ev.get('record_id', '')} | {sid} "
                             f"（{src} {loc}）")
                lines.append(f"  - quote：{short(ev.get('quote', ''))}")
            lines.append("")
    cov_path = os.path.join(args.out_dir, "coverage.md")
    with open(cov_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # ---------- conflict_matrix.md ----------
    conflicts = [c for c in audit.get("conflicts", []) if c.get("status") == "registered"]
    rejected = [c for c in audit.get("conflicts", []) if c.get("status") == "rejected"]
    cm = ["# 冲突证据矩阵", ""]
    if not conflicts:
        cm.append("本次审计未登记冲突证据对（双方均有回链证据的冲突才会登记）。")
    else:
        cm += ["| 主题 | 论断 A | 论断 B | 冲突性质 |",
               "|---|---|---|---|"]
        for c in conflicts:
            cm.append(f"| {c.get('topic', '')} | {c.get('claim_id_a', '')} | "
                      f"{c.get('claim_id_b', '')} | {c.get('nature', '')} |")
        cm.append("")
        cm.append("处置原则：冲突双方均保留并呈现，不擅自取舍；"
                  "可能的解释（人群、剂量、随访期等差异）由模型在综述中讨论。")
    if rejected:
        cm += ["", "## 未登记的冲突记录（缺证据，退回补充）", ""]
        for c in rejected:
            cm.append(f"- {c.get('topic', '')}：{c.get('reason', '')}")
    cm.append("")
    cm_path = os.path.join(args.out_dir, "conflict_matrix.md")
    with open(cm_path, "w", encoding="utf-8") as f:
        f.write("\n".join(cm))

    print(f"已生成制品：{csv_path}、{cov_path}、{cm_path}。")
    print(f"覆盖矩阵：{len(claims)} 条论断 × {len(record_ids)} 条记录；"
          f"冲突登记 {len(conflicts)} 对。")
    sys.exit(0)


if __name__ == "__main__":
    main()
