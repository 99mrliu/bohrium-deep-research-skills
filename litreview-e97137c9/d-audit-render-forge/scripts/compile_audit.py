#!/usr/bin/env python3
"""compile_audit.py — 审计包锻造（bundle D 签名脚本 1）。

读 work/evidence_ledger.jsonl + work/review_draft.md + work/docs.jsonl + work/themes.json
（+ work/case_profile.json），产出：
  out/evidence_matrix.csv  UTF-8 带 BOM（utf-8-sig），Excel 可直接打开；
  out/coverage_map.json    文档×主题证据计数矩阵 + 未被任何主题覆盖的文档清单；
  out/audit_report.html    按 templates/audit_report.html.tmpl 渲染的自包含 HTML：
                           每个论断句 → 引用的证据行 → 逐字摘录 → 文档与页锚点；
                           未被引用证据清单；无标记实质句清单；来源 SHA-256 留痕。
仅做 {{PLACEHOLDER}} 纯字符串替换，所有动态文本经 HTML 转义。
"""
import csv
import html
import json
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "templates", "audit_report.html.tmpl")

MARK_RE = re.compile(r"\[E\d+(?:;E\d+)*\]")
EID_RE = re.compile(r"E\d+")


def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def load_json(path, default):
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    return default


def referenced_ids(draft):
    return set(EID_RE.findall(" ".join(MARK_RE.findall(draft))))


def extract_claims(draft):
    """把草稿切分为论断句：句末标点后的 [E#] 标记归并到其左侧句子。"""
    claims = []
    for line in draft.splitlines():
        s = line.strip()
        if not s or s.startswith(("#", ">", "-", "*")) or re.match(r"^\d+[.)]", s):
            continue
        # 把 "句。[E1]" 规范为 "句[E1]。"，使标记与所支撑句同段
        s = re.sub(r"([。！？!?])\s*((?:\[E\d+(?:;E\d+)*\])+)", r"\2\1", s)
        for part in re.split(r"(?<=[。！？!?])", s):
            if MARK_RE.search(part):
                text = part.strip()
                ids = EID_RE.findall(" ".join(MARK_RE.findall(text)))
                claims.append({"text": text, "evidence_ids": ids})
    for i, c in enumerate(claims, 1):
        c["claim_id"] = f"C{i}"
    return claims


def unsupported_sentences(draft, min_len=20):
    """无证据标记的实质句：长度 > min_len 且非标题/列表/引用/推断/缺口行。"""
    out = []
    for line in draft.splitlines():
        s = line.strip()
        if not s or s.startswith(("#", ">", "-", "*")) or re.match(r"^\d+[.)]", s):
            continue
        if s.startswith("[推断]") or s.startswith("[证据缺口]"):
            continue
        if MARK_RE.search(s):
            continue
        if len(s) > min_len:
            out.append(s)
    return out


def esc(s):
    return html.escape(str(s), quote=True)


def linkify_marks(sentence_escaped):
    """把已转义句子中的 [E#] 变成指向证据锚点的页内链接。"""
    def repl(m):
        inner = ";".join(
            f'<a class="mark" href="#ev-{eid}">{eid}</a>' for eid in EID_RE.findall(m.group(0)))
        return f'<span class="mark">[{inner}]</span>'
    return MARK_RE.sub(repl, sentence_escaped)


def tag(strength):
    return f'<span class="tag tag-{esc(strength)}">{esc(strength)}</span>'


def build_html(work, out, profile, docs, ledger, themes, claims, unused, unsupported, coverage):
    ev_by_id = {r.get("evidence_id"): r for r in ledger}
    doc_by_id = {d["doc_id"]: d for d in docs}

    claim_blocks = []
    for c in claims:
        rows = []
        for eid in c["evidence_ids"]:
            r = ev_by_id.get(eid)
            if not r:
                rows.append(f'<tr><td><span class="mark">{esc(eid)}</span></td>'
                            f'<td colspan="6" class="zero">证据行不存在（link_check 将判失败）</td></tr>')
                continue
            rows.append(
                f'<tr><td><a class="mark" href="#ev-{esc(eid)}">{esc(eid)}</a></td>'
                f'<td>{esc(r.get("doc_id", ""))}</td>'
                f'<td class="anchor-loc">{esc(r.get("locator", ""))}</td>'
                f'<td><span class="quote">{esc(r.get("verbatim_quote", ""))}</span></td>'
                f'<td>{esc(r.get("supports", ""))}</td>'
                f'<td>{esc(r.get("theme", ""))}</td>'
                f'<td>{tag(r.get("strength", ""))}</td></tr>')
        claim_blocks.append(
            f'<section class="claim" id="{c["claim_id"]}">'
            f'<p class="sentence"><b>{c["claim_id"]}.</b> {linkify_marks(esc(c["text"]))}</p>'
            f'<table><tr><th>证据</th><th>文档</th><th>页锚点</th><th>逐字摘录</th>'
            f'<th>支撑论断</th><th>主题</th><th>强度</th></tr>{"".join(rows)}</table></section>')
    claim_html = "\n".join(claim_blocks) if claim_blocks else '<p class="warn">草稿中未检出带 [E#] 标记的论断句。</p>'

    ev_rows = []
    for r in ledger:
        eid = r.get("evidence_id", "?")
        ev_rows.append(
            f'<tr id="ev-{esc(eid)}"><td><b>{esc(eid)}</b></td><td>{esc(r.get("doc_id", ""))}</td>'
            f'<td class="anchor-loc">{esc(r.get("locator", ""))}</td>'
            f'<td><span class="quote">{esc(r.get("verbatim_quote", ""))}</span></td>'
            f'<td>{esc(r.get("supports", ""))}</td><td>{esc(r.get("theme", ""))}</td>'
            f'<td>{tag(r.get("strength", ""))}</td></tr>')
    evidence_html = ('<table><tr><th>证据</th><th>文档</th><th>页锚点</th><th>逐字摘录</th>'
                     '<th>支撑论断</th><th>主题</th><th>强度</th></tr>' + "".join(ev_rows) + "</table>") \
        if ev_rows else '<p class="warn">证据表为空。</p>'

    theme_ids = [t.get("theme") for t in themes]
    cov_rows = []
    for d in coverage["documents"]:
        cells = []
        for tid in theme_ids:
            n = coverage["matrix"].get(d, {}).get(tid, 0)
            cells.append(f'<td class="zero">{n}</td>' if n == 0 else f"<td>{n}</td>")
        title = esc((doc_by_id.get(d) or {}).get("title_hint", ""))[:60]
        cov_rows.append(f"<tr><td>{esc(d)}</td><td>{title}</td>{''.join(cells)}</tr>")
    cov_head = "".join(f"<th>{esc(t)}</th>" for t in theme_ids)
    cov_html = (f"<table><tr><th>文档</th><th>标题线索</th>{cov_head}</tr>{''.join(cov_rows)}</table>")
    uncov = coverage["uncovered_documents"]
    cov_html += ('<p class="warn">未被任何主题覆盖的文档：' + esc(", ".join(uncov)) + "</p>") \
        if uncov else '<p class="ok">全部文档均被至少一个主题覆盖。</p>'

    if unused:
        orph = ["<table><tr><th>证据</th><th>文档</th><th>页锚点</th><th>逐字摘录</th></tr>"]
        for r in unused:
            orph.append(f'<tr><td>{esc(r.get("evidence_id", "?"))}</td><td>{esc(r.get("doc_id", ""))}</td>'
                        f'<td class="anchor-loc">{esc(r.get("locator", ""))}</td>'
                        f'<td><span class="quote">{esc(r.get("verbatim_quote", ""))}</span></td></tr>')
        orphan_html = '<p class="warn">以下证据行存在但未被草稿引用（保留公示，由评审裁决）：</p>' + "".join(orph) + "</table>"
    else:
        orphan_html = '<p class="ok">全部证据行均被草稿引用。</p>'

    if unsupported:
        items = "".join(f"<li>{esc(s)}</li>" for s in unsupported)
        unsup_html = ('<p class="warn">以下实质句（长度 &gt; 20 字符，非标题/列表/推断/缺口）'
                      f"没有证据标记：</p><ul>{items}</ul>")
    else:
        unsup_html = '<p class="ok">未发现无证据标记的实质句。</p>'

    src_rows = []
    for d in docs:
        sha = (d.get("sha256") or "—")
        src_rows.append(f"<tr><td>{esc(d['doc_id'])}</td><td>{esc(str(d.get('ref')))}</td>"
                        f"<td>{esc(d.get('tier', ''))}</td><td>{d.get('words', 0)}</td>"
                        f"<td>{esc(d.get('extract_method', ''))}</td>"
                        f'<td class="anchor-loc">{esc(sha[:16])}…</td></tr>')
    source_html = ("<table><tr><th>文档</th><th>来源</th><th>分级</th><th>词数</th>"
                   "<th>抽取方法</th><th>SHA-256（前16位）</th></tr>" + "".join(src_rows) + "</table>")

    with open(TEMPLATE, encoding="utf-8") as f:
        tmpl = f.read()
    mapping = {
        "{{CASE_ID}}": esc(profile.get("case_id", "unknown_case")),
        "{{GENERATED_AT}}": esc(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")),
        "{{STATUS_HINT}}": "render 阶段产物（finalize 后见 result.json）",
        "{{RESEARCH_QUESTION}}": esc(profile.get("research_question", "")),
        "{{DOC_COUNT}}": str(len(docs)),
        "{{EVIDENCE_COUNT}}": str(len(ledger)),
        "{{CLAIM_COUNT}}": str(len(claims)),
        "{{ORPHAN_COUNT}}": str(len(unused)),
        "{{UNSUPPORTED_COUNT}}": str(len(unsupported)),
        "{{CLAIM_ROWS}}": claim_html,
        "{{EVIDENCE_SECTION}}": evidence_html,
        "{{COVERAGE_SECTION}}": cov_html,
        "{{ORPHAN_SECTION}}": orphan_html,
        "{{UNSUPPORTED_SECTION}}": unsup_html,
        "{{SOURCE_ROWS}}": source_html,
    }
    for k, v in mapping.items():
        tmpl = tmpl.replace(k, v)
    leftover = re.findall(r"\{\{[A-Z_]+\}\}", tmpl)
    if leftover:
        print(f"[compile_audit] 警告：模板存在未替换占位符 {sorted(set(leftover))}", file=sys.stderr)
    html_path = os.path.join(out, "audit_report.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(tmpl)
    return html_path


def run(work, out):
    os.makedirs(out, exist_ok=True)
    profile = load_json(os.path.join(work, "case_profile.json"), {})
    docs = load_jsonl(os.path.join(work, "docs.jsonl"))
    ledger = load_jsonl(os.path.join(work, "evidence_ledger.jsonl"))
    themes = load_json(os.path.join(work, "themes.json"), [])
    draft_path = os.path.join(work, "review_draft.md")
    draft = open(draft_path, encoding="utf-8").read() if os.path.exists(draft_path) else ""

    ref_ids = referenced_ids(draft)
    claims = extract_claims(draft)
    unsupported = unsupported_sentences(draft)
    unused = [r for r in ledger if r.get("evidence_id") not in ref_ids]

    # 1) evidence_matrix.csv（UTF-8 带 BOM，Excel 可直接打开）
    csv_path = os.path.join(out, "evidence_matrix.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["evidence_id", "doc_id", "locator", "verbatim_quote",
                    "supports", "theme", "strength", "referenced_in_draft"])
        for r in ledger:
            w.writerow([r.get("evidence_id", ""), r.get("doc_id", ""), r.get("locator", ""),
                        r.get("verbatim_quote", ""), r.get("supports", ""), r.get("theme", ""),
                        r.get("strength", ""),
                        "yes" if r.get("evidence_id") in ref_ids else "no"])

    # 2) coverage_map.json（文档×主题矩阵 + 未覆盖文档）
    theme_docs = set()
    for t in themes:
        theme_docs.update(t.get("docs", []))
    matrix = {}
    for d in docs:
        did = d["doc_id"]
        matrix[did] = {}
        for t in themes:
            tid = t.get("theme")
            matrix[did][tid] = sum(1 for r in ledger
                                   if r.get("doc_id") == did and r.get("theme") == tid)
    uncovered = [d["doc_id"] for d in docs
                 if d["doc_id"] not in theme_docs
                 and d.get("tier") in ("fulltext", "abstract_only")]
    coverage = {
        "documents": [d["doc_id"] for d in docs],
        "themes": [{"theme": t.get("theme"), "label": t.get("label"),
                    "docs": t.get("docs", [])} for t in themes],
        "matrix": matrix,
        "uncovered_documents": uncovered,
    }
    cov_path = os.path.join(out, "coverage_map.json")
    with open(cov_path, "w", encoding="utf-8") as f:
        json.dump(coverage, f, ensure_ascii=False, indent=2)

    # 3) audit_report.html
    html_path = build_html(work, out, profile, docs, ledger, themes,
                           claims, unused, unsupported, coverage)

    stats = {"claims": len(claims), "evidence": len(ledger),
             "unused_evidence": len(unused), "unsupported_sentences": len(unsupported),
             "uncovered_documents": len(uncovered),
             "html_bytes": os.path.getsize(html_path)}
    print(json.dumps(stats, ensure_ascii=False))
    return stats


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    run(args.work, args.out)


if __name__ == "__main__":
    main(sys.argv[1:])
