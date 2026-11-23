#!/usr/bin/env python3
"""export_bundle.py — 断言集合 schema 校验 + 多格式导出（纯标准库）。

输入 claims.json：
  {"case_id": ..., "source": {...}, "claims": [...]}
校验通过后导出到 --outdir：
  claims.jsonl / claims.csv / review.md / review.html / export-manifest.json
校验失败：打印全部违例并退出 1。
"""
import argparse
import csv
import hashlib
import html
import io
import json
import os
import sys

VERSION = "1.0.0"
POLARITIES = {"positive", "negative"}
MODALITIES = {"asserted", "hedged", "speculative", "proposed"}
STATUSES = {"asserted", "not_reported", "conflict", "inferred"}
CONFIDENCES = {"high", "medium", "low"}
CSV_COLUMNS = ["id", "text", "subject", "relation", "object", "qualifiers",
               "polarity", "modality", "status", "confidence_level",
               "confidence_rationale", "evidence_quote", "evidence_location",
               "evidence_kind", "source_id"]
JSONL_KEY_ORDER = ["id", "text", "subject", "relation", "object", "qualifiers",
                   "polarity", "modality", "status", "confidence", "evidence",
                   "source_id", "adjudication", "searched_scope", "conflict_with"]


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def qual_text(q):
    return str(q if isinstance(q, str) else q.get("text", ""))


def validate(payload):
    errors = []
    if not isinstance(payload, dict):
        return ["payload 不是 JSON object"]
    if not payload.get("case_id"):
        errors.append("缺 case_id")
    claims = payload.get("claims")
    if not isinstance(claims, list):
        return errors + ["缺 claims 数组"]
    seen = set()
    for i, c in enumerate(claims):
        where = f"claims[{i}]({c.get('id', '?')})"
        cid = c.get("id")
        if not cid:
            errors.append(f"{where}: 缺 id")
        elif cid in seen:
            errors.append(f"{where}: id 重复")
        else:
            seen.add(cid)
        for fld in ("text", "subject", "relation"):
            if not str(c.get(fld, "")).strip():
                errors.append(f"{where}: {fld} 为空")
        if "object" not in c or not str(c.get("object", "")).strip():
            errors.append(f"{where}: object 为空")
        if str(c.get("polarity", "positive")) not in POLARITIES:
            errors.append(f"{where}: polarity 非法 {c.get('polarity')}")
        if str(c.get("modality", "asserted")) not in MODALITIES:
            errors.append(f"{where}: modality 非法 {c.get('modality')}")
        status = str(c.get("status", "asserted"))
        if status not in STATUSES:
            errors.append(f"{where}: status 非法 {status}")
        conf = c.get("confidence", {})
        if str(conf.get("level", "")) not in CONFIDENCES:
            errors.append(f"{where}: confidence.level 非法 {conf.get('level')}")
        if not str(conf.get("rationale", "")).strip():
            errors.append(f"{where}: confidence.rationale 为空")
        ev = c.get("evidence", {}) or {}
        if status == "asserted" and not str(ev.get("quote", "")).strip():
            errors.append(f"{where}: asserted 断言缺 evidence.quote")
        if status == "not_reported" and not c.get("searched_scope"):
            errors.append(f"{where}: not_reported 缺 searched_scope")
        quals = c.get("qualifiers", [])
        if not isinstance(quals, list):
            errors.append(f"{where}: qualifiers 不是数组")
    return errors


def ordered_claim(c):
    out = {}
    for k in JSONL_KEY_ORDER:
        if k in c:
            out[k] = c[k]
    for k in c:
        if k not in out:
            out[k] = c[k]
    return out


def render_jsonl(claims):
    buf = io.StringIO()
    for c in claims:
        buf.write(json.dumps(ordered_claim(c), ensure_ascii=False) + "\n")
    return buf.getvalue()


def render_csv(claims):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, lineterminator="\n")
    w.writeheader()
    for c in claims:
        ev = c.get("evidence", {}) or {}
        conf = c.get("confidence", {}) or {}
        loc = ev.get("location", {})
        w.writerow({
            "id": c.get("id", ""), "text": c.get("text", ""),
            "subject": c.get("subject", ""), "relation": c.get("relation", ""),
            "object": str(c.get("object", "")),
            "qualifiers": "; ".join(qual_text(q) for q in c.get("qualifiers", [])),
            "polarity": c.get("polarity", ""), "modality": c.get("modality", ""),
            "status": c.get("status", ""),
            "confidence_level": conf.get("level", ""),
            "confidence_rationale": conf.get("rationale", ""),
            "evidence_quote": ev.get("quote", ""),
            "evidence_location": json.dumps(loc, ensure_ascii=False),
            "evidence_kind": ev.get("kind", ""),
            "source_id": c.get("source_id", ""),
        })
    return buf.getvalue()


def render_md(payload):
    claims = payload["claims"]
    src = payload.get("source", {}) or {}
    lines = ["# 人工复核单（claims review）", "",
             f"- case_id: `{payload.get('case_id')}`",
             f"- 来源: {src.get('title', 'unavailable')}"
             f"（{src.get('identifier', 'unavailable')}）",
             f"- 断言总数: {len(claims)}；逐条勾核后可回填 verdict 列。", ""]
    by_status = {}
    for c in claims:
        by_status.setdefault(c.get("status", "asserted"), []).append(c)
    for status in sorted(by_status):
        lines.append(f"## status = {status}（{len(by_status[status])} 条）")
        lines.append("")
        for c in by_status[status]:
            ev = c.get("evidence", {}) or {}
            conf = c.get("confidence", {}) or {}
            quals = [qual_text(q) for q in c.get("qualifiers", [])]
            lines.append(f"### {c['id']}  {c.get('text', '')}")
            lines.append("")
            lines.append(f"- 三元组: ({c.get('subject')}) —[{c.get('relation')}]→ "
                         f"({c.get('object')})；polarity={c.get('polarity')}；"
                         f"modality={c.get('modality')}")
            if quals:
                lines.append(f"- 限定: {'；'.join(quals)}")
            quote = str(ev.get("quote", "")).replace("\n", "⏎")
            lines.append(f"- 证据（{ev.get('kind', 'direct')}）: 「{quote}」"
                         f" @ {json.dumps(ev.get('location', {}), ensure_ascii=False)}")
            lines.append(f"- 置信度: {conf.get('level')} — {conf.get('rationale')}")
            if c.get("searched_scope"):
                lines.append(f"- 检索范围: {c['searched_scope']}")
            if c.get("conflict_with"):
                lines.append(f"- 冲突对象: {c['conflict_with']}")
            lines.append("- 复核: [ ] 接受  [ ] 修改  [ ] 删除    签字/日期: ______")
            lines.append("")
    return "\n".join(lines) + "\n"


def render_html(payload):
    claims = payload["claims"]
    rows = []
    for c in claims:
        ev = c.get("evidence", {}) or {}
        conf = c.get("confidence", {}) or {}
        quals = "; ".join(qual_text(q) for q in c.get("qualifiers", []))
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(c.get('id')))}</td>"
            f"<td>{html.escape(str(c.get('text', '')))}</td>"
            f"<td>{html.escape(str(c.get('subject')))} "
            f"<b>{html.escape(str(c.get('relation')))}</b> "
            f"{html.escape(str(c.get('object')))}</td>"
            f"<td>{html.escape(quals)}</td>"
            f"<td>{html.escape(str(c.get('polarity')))}/{html.escape(str(c.get('modality')))}</td>"
            f"<td class='{html.escape(str(c.get('status')))}'>"
            f"{html.escape(str(c.get('status')))}</td>"
            f"<td>{html.escape(str(conf.get('level')))}</td>"
            f"<td>{html.escape(str(ev.get('quote', '')))}</td>"
            f"<td>{html.escape(json.dumps(ev.get('location', {}), ensure_ascii=False))}</td>"
            "</tr>")
    doc = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>claims review - {html.escape(str(payload.get('case_id')))}</title>
<style>
body{{font-family:-apple-system,'Helvetica Neue',Arial,sans-serif;margin:24px;color:#222}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{border:1px solid #ccc;padding:6px 8px;vertical-align:top;text-align:left}}
th{{background:#f2f4f7;position:sticky;top:0}}
tr:nth-child(even){{background:#fafbfc}}
td.not_reported{{color:#9a6700;font-weight:600}}
td.conflict{{color:#b42318;font-weight:600}}
td.inferred{{color:#175cd3;font-weight:600}}
</style></head><body>
<h1>claims review — {html.escape(str(payload.get('case_id')))}</h1>
<p>来源: {html.escape(str(payload.get('source', {}).get('title', 'unavailable')))} ·
断言 {len(claims)} 条 · 由 export_bundle.py v{VERSION} 生成（合成示例标注见输入文件）。</p>
<table><thead><tr><th>id</th><th>断言</th><th>三元组</th><th>限定</th>
<th>极性/模态</th><th>状态</th><th>置信度</th><th>证据引文</th><th>定位</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></body></html>
"""
    return doc


def main():
    ap = argparse.ArgumentParser(description="断言集合校验与多格式导出")
    ap.add_argument("--claims", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    with open(args.claims, encoding="utf-8") as fh:
        payload = json.load(fh)
    errors = validate(payload)
    if errors:
        print(json.dumps({"gate": "fail", "violations": errors},
                         ensure_ascii=False, indent=2))
        return 1

    os.makedirs(args.outdir, exist_ok=True)
    outputs = {
        "claims.jsonl": render_jsonl(payload["claims"]),
        "claims.csv": render_csv(payload["claims"]),
        "review.md": render_md(payload),
        "review.html": render_html(payload),
    }
    manifest = {"tool": "export_bundle", "version": VERSION,
                "case_id": payload.get("case_id"),
                "claims": len(payload["claims"]),
                "csv_columns": CSV_COLUMNS, "files": {}}
    for name, text in outputs.items():
        data = text.encode("utf-8")
        path = os.path.join(args.outdir, name)
        with open(path, "wb") as fh:
            fh.write(data)
        manifest["files"][name] = {"sha256": sha256_bytes(data), "bytes": len(data)}
    mpath = os.path.join(args.outdir, "export-manifest.json")
    with open(mpath, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(json.dumps({"gate": "pass", "claims": len(payload["claims"]),
                      "outdir": os.path.abspath(args.outdir)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
