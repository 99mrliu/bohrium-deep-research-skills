#!/usr/bin/env python3
"""build_review.py — 复核交付物构建器（e-review-studio 的核心）。

检索结果只有被人能复核才算交付。本脚本从 /input 的有限快照出发，内置一个自写的
轻量筛查（从简、确定性、可复算），然后把全部结果渲染成一整套**人工复核交付物**：

  ledger.csv    逐条台账，UTF-8-SIG 编码（Excel 双击打开不乱码）
  report.md     结构化报告：概要/筛查条款/候选/排除理由分布/清单核验/不确定性
  review.html   自包含零依赖单文件复核台：状态着色 + 可勾选复核位 + 一键生成 overrides
  flow.svg      PRISMA 式计数流程图（纯文本生成的 SVG，无绘图库）
  manifest.json 每个交付物的 sha256 与字节数（防篡改、供 check_exports.py 回核）
  result.json   按 output_contract 动态装配的最终结果

用法:
  python3 build_review.py --case /input/case.json --input-dir /input \
      --work /app/work --out /app/output [--overrides /app/work/overrides.json]

overrides.json（人工在 review.html 勾选后回写，可选）:
  [{"rid": "R03", "decision": "include|exclude", "note": "人工复核理由"}]

退出码: 0 = 构建成功（complete 或 partial）；2 = blocked（无记录/案例损坏，仍交付诚实产物）；
        1 = 交付物写盘失败等意外错误。
纪律: 仅标准库、零网络；有限快照之外的世界不存在，禁止补造文献；
      夹具标记（synthetic_duplicate/conflict_opinion 等）是输入事实，如实登记不裁决。
"""
import argparse, csv, hashlib, html, json, os, re, sys, time

RECORD_KEYS = ("records", "results", "items", "entries", "hits")
REFLIST_KEYS = ("attributed_papers", "reference_list", "references", "refs", "paper_list")
FIXTURE_KEYS = ("synthetic_duplicate", "duplicate_of", "conflict_opinion",
                "is_fixture", "fixture", "label")
EXCLUDE_DOCTYPES = ("review", "editorial", "news", "perspective")
STOPWORDS = set("""the a an and or of in on for to with by from at as is are was were
be been we our this that these those it its their between among via new study studies
using based approach results show""".split())

# 轻量筛查用的小型跨语词表（声明式；仅当 RQ 中真实出现左侧概念才扩展右侧术语）。
# 筛查刻意从简——本技能的重器在下游交付物，不在这里。
LEXICON = [
    ("钠离子", ["sodium-ion", "sodium", "na-ion"]),
    ("电池", ["battery", "batteries"]),
    ("层状氧化物", ["layered oxide"]),
    ("正极", ["cathode"]),
    ("负极", ["anode"]),
    ("循环", ["cycling", "cycle"]),
    ("稳定性", ["stability", "stable"]),
    ("钙钛矿", ["perovskite"]),
    ("太阳能", ["solar", "photovoltaic"]),
    ("催化", ["catalysis", "catalyst"]),
    ("机器学习", ["machine learning"]),
    ("基因", ["gene", "genomic"]),
]

DECISION_LABEL = {"include": "纳入", "borderline": "待复核",
                  "exclude": "排除", "duplicate": "重复"}


# ---------- 基础工具 ----------
def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_text(path, text, encoding="utf-8"):
    with open(path, "w", encoding=encoding, newline="") as fh:
        fh.write(text)


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def contract_fields(case):
    """动态读取 output_contract，禁止硬编码字段名。"""
    c = case.get("output_contract")
    if isinstance(c, list):
        return [str(x) for x in c]
    if isinstance(c, dict):
        for k in ("fields", "required"):
            if isinstance(c.get(k), list):
                return [str(x) for x in c[k]]
        return sorted(c.keys())
    return []


# ---------- 1) 读取快照（轻量：JSON/JSONL/CSV/TSV） ----------
def normalize(raw, rid, src_file, src_row):
    r = raw if isinstance(raw, dict) else {"value": raw}
    authors = r.get("authors") or r.get("author") or []
    if isinstance(authors, str):
        authors = [a.strip() for a in re.split(r";| and ", authors) if a.strip()]
    ym = re.search(r"(19|20)\d{2}", str(r.get("year") or r.get("publication_year")
                                       or r.get("date") or ""))
    return {
        "rid": rid, "title": r.get("title") or "",
        "authors": authors,
        "year": int(ym.group(0)) if ym else None,
        "doi": (r.get("doi") or "").strip().lower() or None,
        "venue": r.get("venue") or r.get("journal") or r.get("source") or "",
        "type": str(r.get("type") or r.get("doctype") or "").lower(),
        "abstract": r.get("abstract") or "",
        "fixture": {k: r[k] for k in FIXTURE_KEYS if k in r},
        "src_file": src_file, "src_row": src_row,
    }


def load_snapshot(input_dir):
    """返回 (records, file_report, failures)。只认明确的记录列表键，
    署名清单键（attributed_papers 等）不当作记录来源，避免自匹配。"""
    records, file_report, failures = [], [], []
    seq = 0
    for root, _dirs, names in os.walk(input_dir):
        for name in sorted(names):
            path = os.path.join(root, name)
            rel = os.path.relpath(path, input_dir)
            ext = os.path.splitext(name)[1].lower()
            try:
                rows = []
                if ext == ".jsonl":
                    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
                elif ext == ".json":
                    obj = json.load(open(path, encoding="utf-8"))
                    if isinstance(obj, list):
                        rows = obj
                    elif isinstance(obj, dict):
                        for k in RECORD_KEYS:
                            if isinstance(obj.get(k), list):
                                rows = obj[k]
                                break
                elif ext in (".csv", ".tsv"):
                    with open(path, encoding="utf-8-sig", newline="") as fh:
                        rows = list(csv.DictReader(
                            fh, delimiter="\t" if ext == ".tsv" else ","))
                else:
                    file_report.append({"path": rel, "kind": ext.lstrip(".") or "none",
                                        "records": 0})
                    continue
                for i, raw in enumerate(rows):
                    seq += 1
                    records.append(normalize(raw, "R%02d" % seq, rel, i + 1))
                file_report.append({"path": rel, "kind": ext.lstrip("."),
                                    "records": len(rows)})
            except Exception as e:
                failures.append({"path": rel, "error": str(e)})
    return records, file_report, failures


# ---------- 2) 轻量筛查（计分制，从简、确定性） ----------
def derive_criteria(rq):
    rq = rq or ""
    years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", rq)]
    window = [min(years), max(years)] if len(years) >= 2 else (
        [years[0], years[0]] if years else None)
    terms = set(w for w in re.findall(r"[a-z0-9]+", rq.lower())
                if w not in STOPWORDS and len(w) > 2)
    expanded = []
    for concept, en_terms in LEXICON:
        if concept in rq:
            terms.update(en_terms)
            expanded.append({"concept": concept, "terms": en_terms})
    for run in re.findall(r"[一-鿿]+", rq):
        terms.update(run[i:i + 2] for i in range(len(run) - 1))
    return {"year_window": window, "terms": sorted(terms),
            "crosslingual_expansion": expanded,
            "scoring": "score=2*标题命中术语数+1*仅摘要命中术语数; >=4 纳入, 1-3 待复核, 0 排除"}


def norm_title(t):
    return re.sub(r"[^0-9a-z一-鿿]+", "", (t or "").lower())


def dedupe_and_screen(records, criteria, overrides):
    """一遍完成：DOI/归一化标题去重（decision=duplicate），其余计分筛查。
    与范例 bundle 的多级相似度管线不同：这里刻意只做精确级去重，逻辑从简。"""
    ov = {str(o.get("rid")): o for o in (overrides or []) if isinstance(o, dict)}
    seen_doi, seen_title, ledger = {}, {}, []
    counts = {"include": 0, "borderline": 0, "exclude": 0, "duplicate": 0}
    excl_reasons = {}
    for r in records:
        entry = {"rid": r["rid"], "decision": None, "reason": "",
                 "title": r["title"], "authors": r["authors"], "year": r["year"],
                 "doi": r["doi"], "venue": r["venue"], "type": r["type"],
                 "matched_terms": [], "src_file": r["src_file"],
                 "src_row": r["src_row"], "fixture": r["fixture"], "note": ""}
        dup_of = None
        if r["doi"] and r["doi"] in seen_doi:
            dup_of = seen_doi[r["doi"]]
        elif norm_title(r["title"]) and norm_title(r["title"]) in seen_title:
            dup_of = seen_title[norm_title(r["title"])]
        if dup_of:
            entry["decision"] = "duplicate"
            entry["reason"] = "duplicate_of:%s" % dup_of
            if r["fixture"]:
                entry["note"] = "输入夹具标记（%s），如实登记" % ",".join(sorted(r["fixture"]))
        else:
            if r["doi"]:
                seen_doi[r["doi"]] = r["rid"]
            if norm_title(r["title"]):
                seen_title[norm_title(r["title"])] = r["rid"]
            window = criteria["year_window"]
            title_l, abs_l = r["title"].lower(), r["abstract"].lower()
            t_hits = [t for t in criteria["terms"] if t in title_l]
            a_hits = [t for t in criteria["terms"] if t not in t_hits and t in abs_l]
            score = 2 * len(t_hits) + len(a_hits)
            entry["matched_terms"] = t_hits + a_hits
            if window and r["year"] and not (window[0] <= r["year"] <= window[1]):
                entry["decision"] = "exclude"
                entry["reason"] = "year_out_of_window:%s!in:%s" % (r["year"], window)
            elif r["type"] in EXCLUDE_DOCTYPES:
                entry["decision"] = "exclude"
                entry["reason"] = "doctype_excluded:%s" % r["type"]
            elif score >= 4:
                entry["decision"] = "include"
                entry["reason"] = "term_score:%d>=4" % score
            elif score >= 1:
                entry["decision"] = "borderline"
                entry["reason"] = "weak_term_score:%d<4" % score
            else:
                entry["decision"] = "exclude"
                entry["reason"] = "no_term_match"
            if r["fixture"]:
                entry["note"] = "输入夹具标记（%s），如实登记，不做学术裁决" \
                                % ",".join(sorted(r["fixture"]))
            if entry["decision"] == "exclude":
                key = entry["reason"].split(":")[0]
                excl_reasons[key] = excl_reasons.get(key, 0) + 1
        if r["rid"] in ov and entry["decision"] != "duplicate":
            new = str(ov[r["rid"]].get("decision", "")).strip()
            if new in ("include", "exclude", "borderline"):
                entry["reason"] += "+manual_override(was:%s)" % entry["decision"]
                if entry["decision"] == "exclude":
                    key = entry["reason"].split(":")[0]
                    excl_reasons[key] = max(0, excl_reasons.get(key, 1) - 1)
                entry["decision"] = new
                entry["note"] = (entry["note"] + " " if entry["note"] else "") + \
                                "人工复核: %s" % (ov[r["rid"]].get("note") or "（无理由）")
        counts[entry["decision"]] += 1
        ledger.append(entry)
    return ledger, counts, excl_reasons


# ---------- 3) 署名清单核验（轻量） ----------
def check_attribution(records, ledger, case, input_dir):
    refs = None
    for key in REFLIST_KEYS:
        if isinstance(case.get(key), list) and case[key]:
            refs = case[key]
            break
    if refs is None:
        for root, _d, names in os.walk(input_dir):
            for n in sorted(names):
                if not n.endswith(".json"):
                    continue
                try:
                    obj = json.load(open(os.path.join(root, n), encoding="utf-8"))
                except Exception:
                    continue
                if isinstance(obj, dict):
                    for key in REFLIST_KEYS:
                        if isinstance(obj.get(key), list) and obj[key]:
                            refs = obj[key]
                            break
                if refs:
                    break
            if refs:
                break
    if not refs:
        return {"status": "no_reference_list",
                "note": "输入中未找到署名文献清单；清单核验未执行", "papers": []}
    by_rid = {e["rid"]: e for e in ledger}
    papers = []
    for i, ref in enumerate(refs):
        ref = ref if isinstance(ref, dict) else {"title": str(ref)}
        entry = {"ref_id": ref.get("ref_id") or ref.get("id") or "ref-%d" % (i + 1),
                 "title": ref.get("title"), "doi": ref.get("doi") or None}
        rdoi = (ref.get("doi") or "").strip().lower()
        rt = norm_title(ref.get("title", ""))
        hit = next((r for r in records if rdoi and r["doi"] == rdoi), None) or \
              next((r for r in records if rt and norm_title(r["title"]) == rt), None)
        if hit:
            entry["status"] = "matched"
            entry["record_rid"] = hit["rid"]
            entry["in_candidates"] = by_rid.get(hit["rid"], {}).get("decision") == "include"
        else:
            entry["status"] = "missing"
        papers.append(entry)
    return {"status": "ok", "total": len(refs),
            "matched": sum(1 for p in papers if p["status"] == "matched"),
            "missing": sum(1 for p in papers if p["status"] == "missing"),
            "papers": papers}


# ---------- 4) 交付物渲染 ----------
def render_ledger_csv(path, ledger):
    cols = ["review", "rid", "decision", "decision_cn", "reason", "title",
            "authors", "year", "venue", "doi", "matched_terms", "src_file",
            "src_row", "note"]
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:  # UTF-8-SIG: Excel 友好
        w = csv.writer(fh)
        w.writerow(cols)
        for e in ledger:
            w.writerow(["✓人工" if "manual_override" in e["reason"] else "",
                        e["rid"], e["decision"], DECISION_LABEL[e["decision"]],
                        e["reason"], e["title"], "; ".join(e["authors"]),
                        e["year"] or "", e["venue"], e["doi"] or "",
                        "|".join(e["matched_terms"]), e["src_file"],
                        e["src_row"], e["note"]])


def render_report_md(case, ledger, counts, excl_reasons, criteria, attrib,
                     uncertainty, status, deliverable_hashes):
    L = []
    L.append("# 复核交付报告 — %s" % (case.get("case_id") or "（无 case_id）"))
    L.append("")
    L.append("- 研究问题: %s" % (case.get("research_question") or "（缺失）"))
    L.append("- 生成时间: %s" % time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    L.append("- 结果状态: **%s**（三值诚实状态：complete/partial/blocked）" % status)
    L.append("")
    L.append("## 一、概要")
    L.append("")
    L.append("| 环节 | 数量 |")
    L.append("|-|-|")
    L.append("| 识别记录 | %d |" % len(ledger))
    L.append("| 重复移除 | %d |" % counts["duplicate"])
    L.append("| 去重后筛查 | %d |" % (len(ledger) - counts["duplicate"]))
    L.append("| 纳入候选 | %d |" % counts["include"])
    L.append("| 待人工复核 | %d |" % counts["borderline"])
    L.append("| 排除 | %d |" % counts["exclude"])
    L.append("")
    L.append("## 二、筛查条款（轻量、确定性、可复算）")
    L.append("")
    L.append("- 年份窗: %s" % (criteria["year_window"] or "未设定"))
    L.append("- 决策规则: %s" % criteria["scoring"])
    L.append("- 硬性排除: 文献类型 ∈ {%s}" % ", ".join(EXCLUDE_DOCTYPES))
    L.append("- 跨语扩展: %s" % ("; ".join("%s→%s" % (x["concept"], "/".join(x["terms"]))
                                          for x in criteria["crosslingual_expansion"]) or "无"))
    L.append("- 术语数: %d（完整清单见 result.json criteria.terms）" % len(criteria["terms"]))
    L.append("")
    L.append("## 三、候选清单（纳入 %d 条）" % counts["include"])
    L.append("")
    inc = [e for e in ledger if e["decision"] == "include"]
    if inc:
        L.append("| rid | 标题 | 年份 | 理由 |")
        L.append("|-|-|-|-|")
        for e in inc:
            L.append("| %s | %s | %s | %s |"
                     % (e["rid"], e["title"].replace("|", "\\|"),
                        e["year"] or "?", e["reason"]))
    else:
        L.append("（本次运行零纳入——如实报告，不补造文献。）")
    L.append("")
    L.append("## 四、排除理由分布（排除 %d 条）" % counts["exclude"])
    L.append("")
    if excl_reasons:
        L.append("| 理由码 | 条数 |")
        L.append("|-|-|")
        for k in sorted(excl_reasons):
            if excl_reasons[k]:
                L.append("| %s | %d |" % (k, excl_reasons[k]))
    else:
        L.append("（无排除记录。）")
    L.append("")
    L.append("## 五、署名清单核验")
    L.append("")
    if attrib.get("status") == "no_reference_list":
        L.append("- %s" % attrib["note"])
    else:
        L.append("| ref_id | 标题 | 状态 | 对应记录 | 已纳入 |")
        L.append("|-|-|-|-|-|")
        for p in attrib.get("papers", []):
            L.append("| %s | %s | %s | %s | %s |"
                     % (p["ref_id"], (p.get("title") or "").replace("|", "\\|"),
                        p["status"], p.get("record_rid", "—"),
                        "是" if p.get("in_candidates") else "否"))
    L.append("")
    L.append("## 六、不确定性与保留项")
    L.append("")
    if uncertainty:
        for u in uncertainty:
            L.append("- %s" % u)
    else:
        L.append("（无保留项——状态为 complete。）")
    L.append("")
    L.append("## 七、交付物清单与哈希（防篡改，供 check_exports.py 回核）")
    L.append("")
    L.append("| 文件 | sha256（前 16 位） | 字节数 |")
    L.append("|-|-|-|")
    for name in sorted(deliverable_hashes):
        d = deliverable_hashes[name]
        L.append("| %s | `%s…` | %d |" % (name, d["sha256"][:16], d["bytes"]))
    L.append("| report.md | （本文件，哈希见 manifest.json） | — |")
    L.append("| result.json | （哈希见 manifest.json） | — |")
    L.append("")
    L.append("---")
    L.append("本报告由 build_review.py 自动生成；人工复核请使用 review.html，"
             "勾核结果回写 overrides.json 后重跑本脚本。")
    return "\n".join(L) + "\n"


def render_review_html(case, ledger, counts, status):
    """自包含零依赖单文件复核台：状态着色 + 每行复核勾选位 +
    一键把勾核结果生成 overrides.json（人工复制回写后重跑 build_review.py）。"""
    rows = []
    for e in ledger:
        dup = e["decision"] == "duplicate"
        cb = ('<input type="checkbox" class="ov" data-rid="%s" data-decision="%s">'
              % (esc(e["rid"]), esc(e["decision"]))) if not dup else \
             '<span class="na">锁定</span>'
        rows.append(
            '<tr class="d-%s"><td class="c">%s</td><td>%s</td>'
            '<td><span class="badge b-%s">%s</span></td>'
            '<td class="t">%s%s</td><td>%s</td><td class="r">%s</td>'
            '<td class="m">%s</td></tr>'
            % (e["decision"], cb, esc(e["rid"]), e["decision"],
               DECISION_LABEL[e["decision"]], esc(e["title"]),
               (' <span class="fx">夹具</span>' if e["fixture"] else ""),
               e["year"] or "?", esc(e["reason"]),
               esc(", ".join(e["matched_terms"][:6]))))
    return """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>人工复核台 — %(cid)s</title>
<style>
body{font-family:-apple-system,"PingFang SC","Helvetica Neue",sans-serif;margin:2em;color:#222}
h1{font-size:1.4em} .meta{color:#666;font-size:.9em}
table{border-collapse:collapse;width:100%%;font-size:.92em}
th,td{border:1px solid #ccc;padding:6px 8px;vertical-align:top;text-align:left}
th{background:#f0f2f5;position:sticky;top:0}
td.c{text-align:center} td.t{max-width:34em} td.r,td.m{font-size:.85em;color:#555}
.badge{display:inline-block;padding:1px 8px;border-radius:9px;font-size:.85em;color:#fff}
.b-include{background:#2e7d32}.b-borderline{background:#ef6c00}
.b-exclude{background:#9e9e9e}.b-duplicate{background:#6a1b9a}
tr.d-include{background:#f1f8f2}tr.d-borderline{background:#fff8ec}
tr.d-exclude{background:#fafafa;color:#666}tr.d-duplicate{background:#f7f0f9;color:#666}
.fx{background:#c62828;color:#fff;border-radius:3px;padding:0 4px;font-size:.75em}
.na{color:#aaa;font-size:.8em}
#ov{width:100%%;height:9em;font-family:monospace}
button{padding:.4em 1.2em;font-size:1em;cursor:pointer}
.stat span{margin-right:1.2em}
</style></head><body>
<h1>人工复核台 — %(cid)s</h1>
<p class="meta">研究问题: %(rq)s<br>
生成时间: %(ts)s ｜ 结果状态: <b>%(st)s</b> ｜ 本页为自包含静态文件，零外部依赖，可离线打开。</p>
<p class="stat"><span>识别 %(n_all)d</span><span>纳入 %(n_inc)d</span>
<span>待复核 %(n_bor)d</span><span>排除 %(n_exc)d</span><span>重复 %(n_dup)d</span></p>
<h2>第一步：逐条目检</h2>
<table><thead><tr><th>复核</th><th>rid</th><th>处置</th><th>标题</th><th>年份</th>
<th>机器理由</th><th>命中术语</th></tr></thead>
<tbody>
%(rows)s
</tbody></table>
<h2>第二步：勾选需要翻转处置的记录</h2>
<p>勾选语义：include→exclude，exclude→include，borderline→include；duplicate 行锁定不可改
（重复是输入事实，如需恢复请处理源数据）。点击按钮生成 JSON，保存为
<code>/app/work/overrides.json</code> 后重跑 <code>build_review.py --overrides</code>。
判不准的记录请保持 borderline 并在 uncertainty 中说明——<b>不确定是合法结果，臆造不是</b>。</p>
<button onclick="gen()">生成 overrides.json</button>
<textarea id="ov" readonly placeholder="勾核结果 JSON 会出现在这里"></textarea>
<script>
function gen(){
  var flip={include:'exclude',exclude:'include',borderline:'include'};
  var out=[];
  document.querySelectorAll('input.ov:checked').forEach(function(cb){
    out.push({rid:cb.dataset.rid,decision:flip[cb.dataset.decision]||'include',
              note:'人工复核翻转（请在保存前补充具体理由）'});
  });
  document.getElementById('ov').value=JSON.stringify(out,null,2);
}
</script>
</body></html>
""" % {"cid": esc(case.get("case_id") or "（无 case_id）"),
       "rq": esc(case.get("research_question") or "（缺失）"),
       "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "st": esc(status),
       "n_all": len(ledger), "n_inc": counts["include"], "n_bor": counts["borderline"],
       "n_exc": counts["exclude"], "n_dup": counts["duplicate"],
       "rows": "\n".join(rows)}


def _svg_box(x, y, w, h, sid, label, count, fill, extra_lines=None):
    """一个 stage 盒子：<g id="stage-..."> 内含 'n = N'，供 check_exports.py 回核。"""
    parts = ['<g id="stage-%s">' % sid,
             '<rect x="%d" y="%d" width="%d" height="%d" rx="6" fill="%s" stroke="#445" stroke-width="1.2"/>'
             % (x, y, w, h, fill),
             '<text x="%d" y="%d" font-size="13" font-weight="bold" fill="#223">%s</text>'
             % (x + 12, y + 22, esc(label)),
             '<text x="%d" y="%d" font-size="12" fill="#223">n = %d</text>'
             % (x + 12, y + 42, count)]
    for i, line in enumerate(extra_lines or []):
        parts.append('<text x="%d" y="%d" font-size="10.5" fill="#556">%s</text>'
                     % (x + 12, y + 58 + i * 14, esc(line)))
    parts.append("</g>")
    return "\n".join(parts)


def _svg_arrow(x1, y1, x2, y2):
    return ('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#445" stroke-width="1.4" '
            'marker-end="url(#arr)"/>' % (x1, y1, x2, y2))


def render_flow_svg(ledger, counts, excl_reasons):
    """PRISMA 式计数流程图，纯文本生成（零绘图库）。零纳入/零记录时同样正确渲染。"""
    n_all = len(ledger)
    n_screened = n_all - counts["duplicate"]
    excl_lines = ["%s: %d" % (k, v) for k, v in sorted(excl_reasons.items()) if v]
    h_exc = max(70, 58 + 14 * len(excl_lines))
    bottom = 252 + max(70, h_exc)
    W, H = 760, bottom + 24
    boxes = [
        _svg_box(40, 24, 330, 70, "identified", "识别记录（快照解析）", n_all, "#eef4ff"),
        _svg_box(470, 24, 250, 70, "duplicates", "去重移除", counts["duplicate"],
                 "#f7f0f9", ["含夹具标注合成重复" if any(
                     e["decision"] == "duplicate" and e["fixture"] for e in ledger)
                     else "无夹具标注重复"]),
        _svg_box(40, 138, 330, 70, "screened", "去重后进入筛查", n_screened, "#eef4ff"),
        _svg_box(470, 138, 250, h_exc, "excluded", "排除（理由分布）", counts["exclude"],
                 "#fdeaee", excl_lines),
        _svg_box(40, 252, 330, 70, "included", "纳入候选", counts["include"], "#e9f9ee"),
        _svg_box(470, 252, 250, 70, "borderline", "待人工复核", counts["borderline"],
                 "#fff7e0", ["见 review.html 勾选位"]),
    ]
    arrows = [_svg_arrow(205, 94, 205, 138), _svg_arrow(370, 59, 470, 59),
              _svg_arrow(205, 208, 205, 252), _svg_arrow(370, 173, 470, 173),
              _svg_arrow(370, 287, 470, 287)]
    return """<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" font-family="sans-serif">
<defs><marker id="arr" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
<path d="M0,0 L7,3 L0,6 z" fill="#445"/></marker></defs>
<text x="40" y="16" font-size="13" fill="#667">PRISMA 式筛查计数流程（自动生成，可文本核验）</text>
%s
%s
</svg>
""" % (W, H, W, H, "\n".join(boxes), "\n".join(arrows))


# ---------- 5) result.json 与 manifest ----------
def build_result(case, ledger, counts, criteria, attrib, uncertainty, status,
                 file_report, deliverable_hashes):
    cands = [{"rid": e["rid"], "title": e["title"], "year": e["year"],
              "doi": e["doi"], "matched_terms": e["matched_terms"],
              "source": e["src_file"]} for e in ledger if e["decision"] == "include"]
    result = {
        "case_id": case.get("case_id"),
        "summary": ("识别 %d 条记录；去重移除 %d 条；纳入 %d / 待复核 %d / 排除 %d；"
                    "署名清单 %s（匹配 %s / 缺失 %s）；复核交付物 5 件已生成并登记哈希"
                    % (len(ledger), counts["duplicate"], counts["include"],
                       counts["borderline"], counts["exclude"],
                       ("%d 篇" % attrib["total"]) if attrib.get("status") == "ok" else "无",
                       attrib.get("matched", "-"), attrib.get("missing", "-"))),
        "candidates": cands,
        "screening_log": ledger,
        "attribution": attrib.get("papers", []),
        "deliverables": [{"name": n, "sha256": d["sha256"], "bytes": d["bytes"]}
                         for n, d in sorted(deliverable_hashes.items())],
        "criteria": criteria,
        "omissions": list(uncertainty),
        "sources": ([{"kind": "file", "path": f["path"]}
                     for f in file_report if f.get("records")] +
                    [{"kind": "artifact", "path": n}
                     for n in ("ledger.csv", "report.md", "review.html",
                               "flow.svg", "manifest.json", "export-check.json")]),
        "status": status,
        "uncertainty": uncertainty,
        "method": "e-review-studio: load→light-screen→render(ledger/report/html/svg)→manifest→check_exports",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    for f in contract_fields(case):
        if f not in result:
            result[f] = []
            uncertainty.append("output_contract 字段 %s 无对应产物，留空待补" % f)
    notes = {}
    for f in contract_fields(case):
        if result.get(f) in ([], "", {}):
            notes[f] = ("本字段为空的原因已在 uncertainty 中说明"
                        if any(f in u for u in uncertainty) else
                        "本次运行无此类条目（如实留空，非遗漏）")
    result["field_notes"] = notes
    return result


def main():
    ap = argparse.ArgumentParser(
        description="构建人工复核交付物（ledger.csv/report.md/review.html/flow.svg/manifest.json + result.json）")
    ap.add_argument("--case", required=True, help="/input/case.json 路径")
    ap.add_argument("--input-dir", required=True, help="快照输入目录")
    ap.add_argument("--work", required=True, help="中间产物目录")
    ap.add_argument("--out", required=True, help="交付物输出目录")
    ap.add_argument("--overrides", help="人工勾核回写 JSON（可选）")
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)

    case, case_problems = {}, []
    if not os.path.isfile(args.case):
        case_problems.append("case.json 不存在: %s" % args.case)
    else:
        try:
            case = json.load(open(args.case, encoding="utf-8"))
            if not isinstance(case, dict):
                case_problems.append("case.json 顶层不是对象")
                case = {}
        except Exception as e:
            case_problems.append("case.json 解析失败: %s" % e)
            case = {}

    overrides = []
    if args.overrides:
        if os.path.isfile(args.overrides):
            try:
                overrides = json.load(open(args.overrides, encoding="utf-8"))
            except Exception as e:
                case_problems.append("overrides 解析失败（已忽略）: %s" % e)
        else:
            case_problems.append("overrides 文件不存在（已忽略）: %s" % args.overrides)

    records, file_report, failures = load_snapshot(args.input_dir) \
        if os.path.isdir(args.input_dir) else ([], [], [{"path": args.input_dir,
                                                         "error": "输入目录不存在"}])
    criteria = derive_criteria(case.get("research_question"))
    ledger, counts, excl_reasons = dedupe_and_screen(records, criteria, overrides)
    attrib = check_attribution(records, ledger, case,
                               args.input_dir if os.path.isdir(args.input_dir) else ".")

    # ---- 诚实状态与不确定性 ----
    uncertainty = list(case_problems)
    uncertainty += ["%s 解析失败: %s" % (f["path"], f["error"]) for f in failures]
    for e in ledger:
        if e["fixture"].get("conflict_opinion"):
            uncertainty.append("冲突意见夹具记录 %s 已登记为争议证据，本技能不做学术裁决" % e["rid"])
    if attrib.get("status") == "no_reference_list":
        uncertainty.append(attrib["note"])
    for p in attrib.get("papers", []):
        if p["status"] == "missing":
            uncertainty.append("清单文献 %s 在快照中未找到匹配记录" % p["ref_id"])
    if counts["borderline"]:
        uncertainty.append("%d 条记录为 borderline，需在 review.html 中人工勾核"
                           % counts["borderline"])
    if records and counts["include"] == 0:
        uncertainty.append("筛查后零纳入：无记录同时满足年份窗与术语条款"
                           "（如实报告，不放宽条款、不补造文献）")
    if not records:
        status = "blocked"
        uncertainty.append("快照解析后零记录：无法筛查，不补造文献")
    elif uncertainty:
        status = "partial"
    else:
        status = "complete"

    # ---- 渲染交付物（顺序：csv/md/html/svg → result.json → manifest） ----
    paths = {n: os.path.join(args.out, n) for n in
             ("ledger.csv", "report.md", "review.html", "flow.svg")}
    try:
        render_ledger_csv(paths["ledger.csv"], ledger)
        write_text(paths["review.html"], render_review_html(case, ledger, counts, status))
        write_text(paths["flow.svg"], render_flow_svg(ledger, counts, excl_reasons))
        dh = {n: {"sha256": sha256_of(paths[n]), "bytes": os.path.getsize(paths[n])}
              for n in ("ledger.csv", "review.html", "flow.svg")}
        write_text(paths["report.md"], render_report_md(
            case, ledger, counts, excl_reasons, criteria, attrib,
            uncertainty, status, dh))
        dh["report.md"] = {"sha256": sha256_of(paths["report.md"]),
                           "bytes": os.path.getsize(paths["report.md"])}
        result = build_result(case, ledger, counts, criteria, attrib, uncertainty,
                              status, file_report, dh)
        write_text(os.path.join(args.out, "result.json"),
                   json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        dh["result.json"] = {"sha256": sha256_of(os.path.join(args.out, "result.json")),
                             "bytes": os.path.getsize(os.path.join(args.out, "result.json"))}
        write_text(os.path.join(args.out, "manifest.json"),
                   json.dumps({"case_id": case.get("case_id"),
                               "generated_at": result["generated_at"],
                               "deliverables": dh},
                              ensure_ascii=False, indent=2) + "\n")
    except OSError as e:
        print(json.dumps({"ok": False, "error": "交付物写盘失败: %s" % e},
                         ensure_ascii=False))
        sys.exit(1)

    write_text(os.path.join(args.work, "screening_criteria.json"),
               json.dumps(criteria, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"ok": True, "records": len(ledger), "included": counts["include"],
                      "borderline": counts["borderline"], "excluded": counts["exclude"],
                      "duplicates": counts["duplicate"], "status": status,
                      "deliverables": sorted(dh) + ["manifest.json"]},
                     ensure_ascii=False))
    sys.exit(2 if status == "blocked" else 0)


if __name__ == "__main__":
    main()
