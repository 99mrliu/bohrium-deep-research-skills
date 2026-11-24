#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_matrix.py — 论断×来源证据矩阵构建与审计（仅标准库，Python >= 3.9）。

输入：
  --claims     claims.json  论断台账（schema 见 references/claims-schema.md）
  --anchors    anchors.json 锚点登记表（own_data: Dnn，literature: Lnn）
  --discussion discussion.md 按台账写成的讨论正文（句内挂 [Dnn]/[Lnn] 锚）
输出：
  --out        evidence_matrix.md  论断 × 锚点 × 关系 × 语气 对照矩阵
  --json       coverage.json       覆盖与审计结果（机器可读）

审计规则：
  (a) 每条论断的正文必须出现在 discussion.md 中，且其全部锚点以 [Dnn]/[Lnn]
      形式挂在论断所在句（论断跨句时窗口自动扩展至覆盖各句）；
  (b) 每条论断至少有 1 个锚点（无锚论断 = 孤儿论断，ERROR）；
  (c) 文献锚点关系为 一致/不一致/部分一致 时，论断句或其相邻句必须出现相应
      关系措辞（一致/不一致/部分一致 及同义说法）；
  (d) 论断引用的锚点 id 与正文出现的锚点 id 必须存在于 anchors.json 登记表；
      正文出现登记表之外的锚点 = ERROR；
  (e) 登记表中未被任何论断使用的锚点以 INFO 报告（不判失败）；
  (f) 正文中出现但不属于任何论断的文献锚点 = 装饰引用（ERROR）。

退出码：0 = 无 ERROR；1 = 存在 ERROR（孤儿论断/无出处/未知锚点/关系未措辞化/装饰引用）。
"""
import argparse
import json
import re
import sys

RELATIONS_LIT = ("一致", "不一致", "部分一致", "机制解释", "背景")
RELATION_OWN = "支持"
STRENGTHS = ("直陈", "初步", "推测")

# 关系措辞核验关键词（核验窗口：论断句 ± 相邻一句）
RELATION_KEYWORDS = {
    "一致": [r"(?<!不)(?<!部分)一致", r"相符", r"吻合", r"印证了"],
    "不一致": [r"不一致", r"不符", r"相悖", r"相矛盾", r"矛盾"],
    "部分一致": [r"部分一致", r"部分相符", r"基本一致", r"大体一致", r"大致相符"],
}

ANCHOR_TOKEN_RE = re.compile(r"\[([DL]\d{1,3})\]")
ANY_BRACKET_RE = re.compile(r"\[([^\[\]\s]{1,16})\]")
SENT_BOUNDARY = "。！？!?；;\n"


def norm(s):
    """空白归一化：中文文本按去除全部空白后比较。"""
    return re.sub(r"\s+", "", s)


def strip_anchors(s):
    return ANCHOR_TOKEN_RE.sub("", s)


def split_sentences(text):
    """按中英文句读切句，保留边界符。返回句子字符串列表。"""
    sents, buf = [], []
    for ch in text:
        buf.append(ch)
        if ch in SENT_BOUNDARY:
            s = "".join(buf).strip()
            if s:
                sents.append(s)
            buf = []
    rest = "".join(buf).strip()
    if rest:
        sents.append(rest)
    return sents


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_window(sent_stripped_norm, claim_norm, max_span=5):
    """在归一化后的句子序列中滑窗查找论断正文，返回 (start, end) 句下标（含端点）。"""
    n = len(sent_stripped_norm)
    for span in range(1, min(max_span, n) + 1):
        for i in range(0, n - span + 1):
            if claim_norm in "".join(sent_stripped_norm[i:i + span]):
                return i, i + span - 1
    return None


def main(argv=None):
    p = argparse.ArgumentParser(
        description="构建论断×来源证据矩阵并审计：无孤儿论断、无装饰引用、关系措辞化。")
    p.add_argument("--claims", required=True, help="claims.json 论断台账")
    p.add_argument("--anchors", required=True, help="anchors.json 锚点登记表")
    p.add_argument("--discussion", required=True, help="discussion.md 讨论正文")
    p.add_argument("--out", required=True, help="输出证据矩阵 markdown 路径")
    p.add_argument("--json", required=True, help="输出 coverage.json 路径")
    args = p.parse_args(argv)

    errors, infos = [], []

    claims = load_json(args.claims)
    anchors = load_json(args.anchors)
    with open(args.discussion, "r", encoding="utf-8") as f:
        discussion = f.read()

    own_reg = {a["id"] for a in anchors.get("own_data", [])}
    lit_reg = {a["id"] for a in anchors.get("literature", [])}
    all_reg = own_reg | lit_reg

    # ---------- 台账 schema 校验 ----------
    seen_ids = set()
    for c in claims:
        cid = c.get("id", "?")
        if cid in seen_ids:
            errors.append("论断 id 重复: %s" % cid)
        seen_ids.add(cid)
        if not c.get("text"):
            errors.append("%s 缺少 text" % cid)
        if c.get("strength") not in STRENGTHS:
            errors.append("%s 语气强度非法: %r（允许: %s）"
                          % (cid, c.get("strength"), "/".join(STRENGTHS)))
        cl = c.get("anchors") or []
        if not cl:
            errors.append("%s 无锚点（孤儿论断），不得进入正文" % cid)  # 规则 (b)
        for a in cl:
            aid = a.get("id", "")
            rel = a.get("relation", "")
            if not re.fullmatch(r"[DL]\d{1,3}", aid):
                errors.append("%s 锚点 id 格式非法: %r" % (cid, aid))
                continue
            if aid not in all_reg:
                errors.append("%s 引用登记表之外的锚点: %s" % (cid, aid))  # 规则 (d)
                continue
            if aid.startswith("D") and rel != RELATION_OWN:
                errors.append("%s 自数据锚点 %s 的关系应为「支持」，实际为 %r" % (cid, aid, rel))
            if aid.startswith("L") and rel not in RELATIONS_LIT:
                errors.append("%s 文献锚点 %s 的关系非法: %r（允许: %s）"
                              % (cid, aid, rel, "/".join(RELATIONS_LIT)))

    # ---------- 正文锚点核验 ----------
    disc_tokens = ANCHOR_TOKEN_RE.findall(discussion)
    for tok in sorted(set(disc_tokens)):
        if tok not in all_reg:
            errors.append("正文出现登记表之外的锚点: [%s]" % tok)  # 规则 (d)
    for m in ANY_BRACKET_RE.finditer(discussion):
        tok = m.group(1)
        if tok[:1].upper() in ("D", "L") and not re.fullmatch(r"[DL]\d{1,3}", tok):
            errors.append("正文锚点格式错误: [%s]（应为 [Dnn]/[Lnn]）" % tok)

    claim_anchor_union = {a.get("id") for c in claims for a in (c.get("anchors") or [])}
    for tok in sorted(set(disc_tokens)):
        if tok in all_reg and tok.startswith("L") and tok not in claim_anchor_union:
            errors.append("装饰引用: 正文 [%s] 未挂到任何论断" % tok)  # 规则 (f)
        if tok in all_reg and tok.startswith("D") and tok not in claim_anchor_union:
            infos.append("正文自数据锚点 [%s] 未挂到任何论断，请确认是否有意为之" % tok)

    # ---------- 定位论断句并核验句内锚点、关系措辞 ----------
    sentences = split_sentences(discussion)
    sent_norm = [norm(strip_anchors(s)) for s in sentences]
    per_claim = []
    for c in claims:
        cid = c.get("id", "?")
        text = c.get("text", "")
        win = find_window(sent_norm, norm(text)) if text else None
        row = {"id": cid, "text": text, "anchors": [a.get("id") for a in (c.get("anchors") or [])],
               "relations": {a.get("id"): a.get("relation") for a in (c.get("anchors") or [])},
               "strength": c.get("strength"), "located": False,
               "inline_ok": False, "relation_verbalized_ok": True, "ok": False}
        if win is None:
            errors.append("%s 论断正文未在 discussion.md 中出现（句内挂锚无从核验）" % cid)
            per_claim.append(row)
            continue
        row["located"] = True
        row["window_sentences"] = [win[0] + 1, win[1] + 1]
        win_text = "".join(sentences[win[0]:win[1] + 1])
        lo = max(0, win[0] - 1)
        hi = min(len(sentences) - 1, win[1] + 1)
        neighbor_text = "".join(sentences[lo:hi + 1])

        inline_missing = []
        for a in (c.get("anchors") or []):
            aid = a.get("id", "")
            if ("[%s]" % aid) not in win_text:
                inline_missing.append(aid)
        if inline_missing:
            errors.append("%s 锚点未挂入论断句: %s" % (cid, ", ".join(inline_missing)))  # 规则 (a)
        else:
            row["inline_ok"] = True

        for a in (c.get("anchors") or []):
            aid, rel = a.get("id", ""), a.get("relation", "")
            if aid.startswith("L") and rel in RELATION_KEYWORDS and aid in all_reg:
                pats = RELATION_KEYWORDS[rel]
                if not any(re.search(pt, neighbor_text) for pt in pats):
                    row["relation_verbalized_ok"] = False
                    errors.append(
                        "%s 文献锚点 %s 声明关系「%s」，但论断句及相邻句未出现相应措辞"
                        % (cid, aid, rel))  # 规则 (c)

        row["ok"] = (row["located"] and row["inline_ok"]
                     and row["relation_verbalized_ok"] and bool(c.get("anchors")))
        per_claim.append(row)

    # ---------- 未使用锚点（INFO）----------
    for aid in sorted(all_reg - claim_anchor_union - set(disc_tokens)):
        infos.append("登记锚点 %s 未被任何论断使用" % aid)  # 规则 (e)

    # ---------- 输出矩阵 ----------
    md = []
    md.append("# 讨论证据对照矩阵\n")
    md.append("| 论断ID | 论断 | 锚点 | 关系 | 语气 | 定位 | 句内锚点 | 关系措辞 | 结论 |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    for row in per_claim:
        pairs = "; ".join("%s(%s)" % (a, row["relations"].get(a, "?")) for a in row["anchors"]) or "—"
        short = row["text"] if len(row["text"]) <= 40 else row["text"][:40] + "…"
        verdict = "OK" if row["ok"] else "FAIL"
        md.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            row["id"], short, ", ".join(row["anchors"]) or "—", pairs,
            row["strength"] or "—",
            "是" if row["located"] else "否",
            "是" if row["inline_ok"] else "否",
            "是" if row["relation_verbalized_ok"] else "否",
            verdict))
    md.append("")
    md.append("## 审计消息\n")
    if errors:
        md.append("### ERROR\n")
        md.extend("- %s" % e for e in errors)
    if infos:
        md.append("### INFO\n")
        md.extend("- %s" % i for i in infos)
    if not errors and not infos:
        md.append("- 无")
    md.append("")
    md.append("## 结论\n")
    md.append("**%s**（ERROR %d 条，INFO %d 条）" % ("FAIL" if errors else "PASS", len(errors), len(infos)))
    md.append("")
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    coverage = {
        "claims_total": len(claims),
        "claims_ok": sum(1 for r in per_claim if r["ok"]),
        "anchors_registered": sorted(all_reg),
        "anchors_used_in_claims": sorted(claim_anchor_union & all_reg),
        "anchors_cited_in_discussion": sorted(set(disc_tokens)),
        "unused_anchors": sorted(all_reg - claim_anchor_union - set(disc_tokens)),
        "errors": errors,
        "infos": infos,
        "claims": per_claim,
        "verdict": "FAIL" if errors else "PASS",
    }
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(coverage, f, ensure_ascii=False, indent=2)
        f.write("\n")

    for e in errors:
        print("[ERR] %s" % e)
    for i in infos:
        print("[INFO] %s" % i)
    print("论断 %d 条，通过 %d 条；ERROR %d 条，INFO %d 条"
          % (len(claims), coverage["claims_ok"], len(errors), len(infos)))
    print("FAIL" if errors else "PASS")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
