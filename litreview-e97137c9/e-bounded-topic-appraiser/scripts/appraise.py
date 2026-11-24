#!/usr/bin/env python3
"""appraise.py — 有界选题评估（bundle E 签名脚本 3）。

输入：
  - work/case_extras.json：候选选题与约束（ingest 从 case.json 递归探测）；
    候选选题缺失时回退读取模型产物 work/topics.md（'- ' 或 '## ' 起始行）。
  - work/gap_register.json：已登记空白（gap_register.py）。
  - work/facet_matrix.json：facet 覆盖（facet_scan.py）。
  - work/docs.jsonl + work/pages/：文献分级与全文（约束核查用）。

评分规则（细则见 rules/appraisal_rubric.md）：
  novelty_within_corpus = 1 − |支持文献| / |可用文献|；
    支持文献 = facet signature 被该选题 signature 完全覆盖的文献。
  evidence_sufficiency = min(1, (n_fulltext + 0.5·n_abstract) / 3)，按相关文献
    （与选题共享 ≥1 个 signature facet）计。
  constraint_fit = 各约束核查得分均值（satisfied=1 / unverifiable=0.5 / violated=0）；
    无约束时记 null，权重归一为 0.6·novelty + 0.4·sufficiency。
  加权总分 = 0.45·novelty + 0.30·sufficiency + 0.25·fit；
  档位：≥0.75 strong；0.45–0.75 conditional；<0.45 not_recommended。

产物：out/appraisal_matrix.json、out/decision_memo.md（决策备忘录，
结构遵循 templates/decision_memo.md）。
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import facet_scan  # noqa: E402

W_NOVELTY, W_SUFFICIENCY, W_FIT = 0.45, 0.30, 0.25
BAND_STRONG, BAND_CONDITIONAL = 0.75, 0.45
INVIVO_METHODS = {"随机对照试验", "队列研究", "病例对照", "横断面", "单臂试验",
                  "荟萃分析", "系统综述", "动物实验"}
INVIVO_TEXT_RE = re.compile(r"in vivo|体内|participants|randomi[sz]ed|受试|患者", re.I)
SAMPLE_RES = [re.compile(r"[nN]\s*=\s*(\d+)"),
              re.compile(r"(\d+)\s*(?:名|例|participants|patients|subjects|volunteers)", re.I)]
CONS_SAMPLE_RE = re.compile(r"(?:样本量|sample\s*size)\s*[≥>＞=:]?\s*(\d+)", re.I)


def load_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def topic_signature(topic_text, flat_vocab):
    """用 facet 词表 aliases 给选题文本打标 → facet id 集合。"""
    tl = topic_text.lower()
    sig = set()
    for fid, cat, value, aliases in flat_vocab:
        if any(facet_scan.alias_hit(tl, a) for a in aliases):
            sig.add(fid)
    return sig


def parse_topics_md(path):
    topics = []
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            m = re.match(r"\s*(?:[-*]\s+|##\s+)(.+?)\s*$", line)
            if m and len(m.group(1)) >= 4:
                topics.append(m.group(1))
    return list(dict.fromkeys(topics))


def max_sample_size(text):
    best = 0
    for rx in SAMPLE_RES:
        for m in rx.finditer(text):
            best = max(best, int(m.group(1)))
    return best


def eval_constraint(constraint, signature, related_docs, doc_texts, doc_facets):
    """返回 (score, status, detail)。score ∈ {1.0, 0.5, 0.0}。"""
    text = constraint
    tl = text.lower()
    sig_values = {fid.split(":", 1)[1] for fid in signature}
    related_facets = set()
    for d in related_docs:
        related_facets |= doc_facets.get(d, set())
    related_values = {fid.split(":", 1)[1] for fid in related_facets}
    related_text = "\n".join(doc_texts.get(d, "") for d in related_docs)

    verdicts = []
    m = CONS_SAMPLE_RE.search(text)
    if m:
        need = int(m.group(1))
        best = max((max_sample_size(doc_texts.get(d, "")) for d in related_docs), default=0)
        ok = best >= need
        verdicts.append((1.0 if ok else 0.0, "satisfied" if ok else "violated",
                         f"样本量≥{need}：相关文献最大样本量 {best}"))
    if re.search(r"体内|in[\s-]?vivo", tl):
        if {"体外实验", "细胞系"} & sig_values:
            verdicts.append((0.0, "violated", "体内限定：选题 signature 含体外/细胞系维度"))
        elif sig_values & INVIVO_METHODS or related_values & INVIVO_METHODS \
                or INVIVO_TEXT_RE.search(related_text):
            verdicts.append((1.0, "satisfied", "体内限定：选题/相关文献具备体内研究特征"))
        else:
            verdicts.append((0.5, "unverifiable", "体内限定：相关证据不足以判定"))
    if re.search(r"体外|in[\s-]?vitro", tl) and not re.search(r"体内", tl):
        if "体外实验" in sig_values or "体外实验" in related_values:
            verdicts.append((1.0, "satisfied", "体外限定：选题/相关文献具备体外研究特征"))
        else:
            verdicts.append((0.0, "violated", "体外限定：未见体外研究维度"))
    if re.search(r"随机|rct|randomi[sz]ed", tl):
        if "随机对照试验" in sig_values or "随机对照试验" in related_values:
            verdicts.append((1.0, "satisfied", "随机化限定：命中随机对照试验 facet"))
        else:
            verdicts.append((0.0, "violated", "随机化限定：相关文献均非随机对照设计"))
    if not verdicts:
        tokens = re.findall(r"[A-Za-z]{3,}|[一-鿿]{2,}", text)
        haystack = (tl + "\n" + related_text.lower())
        hit = [t for t in tokens if t.lower() in haystack]
        if hit:
            verdicts.append((1.0, "satisfied", f"关键词命中：{', '.join(hit[:5])}"))
        else:
            verdicts.append((0.5, "unverifiable", "约束关键词在选题与相关文献中均无命中，无法核查"))
    score = sum(v[0] for v in verdicts) / len(verdicts)
    status = "satisfied" if all(v[1] == "satisfied" for v in verdicts) else \
        ("violated" if any(v[1] == "violated" for v in verdicts) else "unverifiable")
    return round(score, 3), status, "；".join(v[2] for v in verdicts)


def band(total):
    if total >= BAND_STRONG:
        return "strong"
    if total >= BAND_CONDITIONAL:
        return "conditional"
    return "not_recommended"


def run(work, out):
    os.makedirs(out, exist_ok=True)
    extras = json.load(open(os.path.join(work, "case_extras.json"), encoding="utf-8")) \
        if os.path.exists(os.path.join(work, "case_extras.json")) else {}
    matrix = json.load(open(os.path.join(work, "facet_matrix.json"), encoding="utf-8"))
    register = json.load(open(os.path.join(work, "gap_register.json"), encoding="utf-8")) \
        if os.path.exists(os.path.join(work, "gap_register.json")) else {"gaps": []}
    docs = load_jsonl(os.path.join(work, "docs.jsonl"))
    tiers = {d["doc_id"]: d.get("tier") for d in docs}
    usable = matrix.get("usable_docs", [])
    doc_facets = {d: set(v) for d, v in matrix.get("doc_facets", {}).items()}
    doc_texts = {d: facet_scan.doc_text(work, d) for d in usable}
    flat_vocab = facet_scan.load_vocab()
    profile = json.load(open(os.path.join(work, "case_profile.json"), encoding="utf-8")) \
        if os.path.exists(os.path.join(work, "case_profile.json")) else {}

    notes = []
    topics = list(extras.get("candidate_topics") or [])
    topics_source = "case_extras"
    if not topics:
        topics = parse_topics_md(os.path.join(work, "topics.md"))
        topics_source = "topics_md_fallback"
        if topics:
            notes.append("case.json 未提供候选选题，已回退使用模型产物 work/topics.md（模拟/模型产出，需人工确认）")
    constraints = list(extras.get("constraints") or [])
    if not topics:
        notes.append("无任何候选选题可评估（case_extras 与 topics.md 均为空）")

    gaps = register.get("gaps", [])
    n_usable = max(1, len(usable))
    rows = []
    for topic in topics:
        sig = topic_signature(topic, flat_vocab)
        supporting = sorted(d for d in usable if sig and sig <= doc_facets.get(d, set()))
        related = sorted(d for d in usable if sig & doc_facets.get(d, set()))
        novelty = round(1 - len(supporting) / n_usable, 3)
        n_full = sum(1 for d in related if tiers.get(d) == "fulltext")
        n_abs = sum(1 for d in related if tiers.get(d) == "abstract_only")
        sufficiency = round(min(1.0, (n_full + 0.5 * n_abs) / 3.0), 3)

        checks, fit_scores = [], []
        for c in constraints:
            score, status, detail = eval_constraint(c, sig, related, doc_texts, doc_facets)
            checks.append({"constraint": c, "status": status, "score": score, "detail": detail})
            fit_scores.append(score)
            if status == "unverifiable":
                notes.append(f"选题「{topic[:40]}」约束「{c[:40]}」无法完全核查，按 0.5 计入")
        fit = round(sum(fit_scores) / len(fit_scores), 3) if fit_scores else None

        if fit is None:
            total = round(0.6 * novelty + 0.4 * sufficiency, 3)
        else:
            total = round(W_NOVELTY * novelty + W_SUFFICIENCY * sufficiency + W_FIT * fit, 3)
        rec = band(total)

        # 绑定空白：facet_absent（signature 命中）/ single_source 与 conflict（文献交集）
        bound = []
        for g in gaps:
            if g["gap_type"] == "facet_absent" and g.get("facet") in sig:
                bound.append(g["gap_id"])
            elif g["gap_type"] in ("single_source", "unresolved_conflict") and \
                    set(g.get("docs_involved", [])) & set(related):
                bound.append(g["gap_id"])

        rationale = (
            f"语料内新颖度 {novelty}（{len(supporting)}/{len(usable)} 篇已直接覆盖该选题）；"
            f"证据充分度 {sufficiency}（相关文献 {len(related)} 篇：fulltext {n_full}、abstract_only {n_abs}）；"
            f"约束契合度 {fit if fit is not None else 'null（无约束）'}"
            f"（{sum(1 for c in checks if c['status'] == 'satisfied')}/{len(checks)} 条满足）"
            if checks else
            f"语料内新颖度 {novelty}；证据充分度 {sufficiency}；无约束可核，权重按 0.6/0.4 归一"
        )
        if bound:
            rationale += f"；绑定空白 {', '.join(bound)}（详见 gap_register）"
        rows.append({
            "topic": topic,
            "topic_signature": sorted(sig),
            "supporting_docs": supporting,
            "related_docs": related,
            "novelty_within_corpus": novelty,
            "evidence_sufficiency": sufficiency,
            "constraint_fit": fit,
            "constraint_checks": checks,
            "weighted_total": total,
            "recommendation": rec,
            "rationale": rationale,
            "bound_gaps": bound,
        })

    rows.sort(key=lambda r: -r["weighted_total"])
    appraisal = {
        "case_id": profile.get("case_id", "unknown_case"),
        "research_question": profile.get("research_question", ""),
        "topics_source": topics_source,
        "weights": {"novelty_within_corpus": W_NOVELTY,
                    "evidence_sufficiency": W_SUFFICIENCY,
                    "constraint_fit": W_FIT,
                    "no_constraint_fallback": "0.6·novelty + 0.4·sufficiency"},
        "bands": {"strong": f">= {BAND_STRONG}",
                  "conditional": f"{BAND_CONDITIONAL}–{BAND_STRONG}",
                  "not_recommended": f"< {BAND_CONDITIONAL}"},
        "n_usable_docs": len(usable),
        "appraisals": rows,
        "notes": notes,
    }
    with open(os.path.join(out, "appraisal_matrix.json"), "w", encoding="utf-8") as f:
        json.dump(appraisal, f, ensure_ascii=False, indent=2)

    memo = render_memo(appraisal, register, constraints)
    with open(os.path.join(out, "decision_memo.md"), "w", encoding="utf-8") as f:
        f.write(memo)
    return appraisal


def render_memo(appraisal, register, constraints):
    """按 templates/decision_memo.md 结构程序化渲染决策备忘录。"""
    L = []
    L.append("# 选题评估决策备忘录（decision memo）")
    L.append("")
    L.append(f"- case_id：{appraisal['case_id']}")
    L.append(f"- 研究问题：{appraisal['research_question'] or '（未提供）'}")
    L.append(f"- 候选选题来源：{appraisal['topics_source']}")
    L.append(f"- 可用文献：{appraisal['n_usable_docs']} 篇；登记空白：{register.get('n_gaps', 0)} 条"
             f"（{json.dumps(register.get('by_type', {}), ensure_ascii=False)}）")
    L.append(f"- 权重：novelty {appraisal['weights']['novelty_within_corpus']} / "
             f"sufficiency {appraisal['weights']['evidence_sufficiency']} / "
             f"fit {appraisal['weights']['constraint_fit']}")
    L.append("")
    L.append("## 1. 结论一览")
    L.append("")
    L.append("| 选题 | 新颖度 | 充分度 | 约束契合 | 加权总分 | 推荐档位 |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for r in appraisal["appraisals"]:
        fit = "null" if r["constraint_fit"] is None else f"{r['constraint_fit']:.3f}"
        L.append(f"| {r['topic']} | {r['novelty_within_corpus']:.3f} | "
                 f"{r['evidence_sufficiency']:.3f} | {fit} | {r['weighted_total']:.3f} | "
                 f"**{r['recommendation']}** |")
    L.append("")
    L.append("## 2. 逐题评估理由")
    for r in appraisal["appraisals"]:
        L.append("")
        L.append(f"### {r['topic']} — {r['recommendation']}（{r['weighted_total']:.3f}）")
        L.append(f"- 理由：{r['rationale']}")
        L.append(f"- 选题 signature：{', '.join(r['topic_signature']) or '（未命中词表）'}")
        L.append(f"- 支持文献：{', '.join(r['supporting_docs']) or '无'}；"
                 f"相关文献：{', '.join(r['related_docs']) or '无'}")
        for c in r["constraint_checks"]:
            L.append(f"- 约束「{c['constraint']}」→ {c['status']}（{c['detail']}）")
    L.append("")
    L.append("## 3. 绑定空白清单")
    any_bound = False
    for r in appraisal["appraisals"]:
        if r["bound_gaps"]:
            any_bound = True
            L.append(f"- {r['topic']} → {', '.join(r['bound_gaps'])}")
    if not any_bound:
        L.append("- 无（所有选题均未绑定登记空白，需警惕空白登记与选题脱节）")
    L.append("")
    L.append("## 4. 边界与不确定性")
    for n in appraisal.get("notes", []):
        L.append(f"- {n}")
    L.append("- 新颖度仅在当前语料内有界成立；语料外是否空白需另行查证，本备忘录不外推。")
    L.append("- 每条空白均绑定 docs_checked 与 binding_evidence（见 gap_register.json），"
             "本备忘录不接受无绑定的'有待进一步研究'式表述。")
    L.append("")
    return "\n".join(L)


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    a = run(args.work, args.out)
    summary = {r["topic"][:30]: r["recommendation"] for r in a["appraisals"]}
    print(json.dumps({"topics": len(a["appraisals"]),
                      "topics_source": a["topics_source"],
                      "recommendations": summary}, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
