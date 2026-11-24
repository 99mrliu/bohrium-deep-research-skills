#!/usr/bin/env python3
"""anchor_audit.py — 页级主张焊接审计（anchor weld gate）。

对 claims.json（{"claims": [...]} 或裸数组）中的每张 claim card 执行三道
确定性检查，全部通过才计 verified：

  A. 逐字锚定：把 anchor 引文重新按字找回源索引。
     归一化 = NFKC + casefold + 空白压缩 + 换行/连字符断词修复。
     锚定五态：
       verified       在 locator.pdf_page 声明页内逐字命中
       page_mismatch  全文其它页命中（引文对、页码错）
       not_verbatim   归一化后全文档未命中（疑似凭记忆改写）
       doc_missing    locator.file 不在源索引中
       quote_empty    anchor 为空或归一化后为空
  B. 数字防漂移扫描：slide_text 中每个数字 token 必须在所焊文档的
     数字注册表（source_index.py 产物）中按数值精确出现，
     否则 number_not_in_source。
  C. 强度措辞门：strength ∈ {preliminary, contextual} 的 claim，
     其 slide_text 不得含 references/strength-lexicon.md 中的
     过强词表，否则 strength_overclaim。

主状态按 quote_empty → doc_missing → 锚定态 → 数字 → 强度的顺序取首个失败；
detail 字段会同时列出其余违例，便于一次修完。

产物（写入 --outdir，默认与 claims 同目录）：
  audit_report.json  每条 claim 的状态与定位 + 汇总 + 回链率
退出码：0 全部 verified；1 存在任何非 verified（stdout 逐项清单）；
2 用法/IO/schema 错误。仅标准库。
"""
import argparse
import json
import os
import re
import sys
import unicodedata

ANCHOR_STATES = ("verified", "page_mismatch", "not_verbatim",
                 "doc_missing", "quote_empty")
EXTRA_STATES = ("number_not_in_source", "strength_overclaim")
ALL_STATES = ANCHOR_STATES + EXTRA_STATES
WEAK_STRENGTHS = ("preliminary", "contextual")
REQUIRED_KEYS = ("claim_id", "slide_text", "strength", "locator", "anchor")

# 与 source_index.py 同源的数字 token 规则
NUMBER_RE = re.compile(r"(?<![\w.+-])(\d+(?:,\d{3})*(?:\.\d+)?)(?![\d.])")

LEX_BEGIN = "<!-- LEXICON:BEGIN -->"
LEX_END = "<!-- LEXICON:END -->"


def normalize(text):
    """NFKC + 连字符换行修复 + casefold + 空白压缩。"""
    if text is None:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"-\s*\n\s*", "", text)  # "experi-\nmental" -> "experimental"
    text = text.casefold()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_index(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        index = json.load(f)
    docs = {}
    for d in index.get("docs", []):
        if d.get("parse_status") != "ok":
            continue
        pages = []
        for pg in d.get("pages", []):
            pages.append({"page": pg.get("page"),
                          "norm": normalize(pg.get("text", ""))})
        values = set()
        for rec in d.get("numbers", []):
            values.add(str(rec.get("value", "")).replace(",", ""))
        docs[d.get("doc_id")] = {"pages": pages, "number_values": values}
    return docs


def load_lexicon(path):
    """解析 references/strength-lexicon.md 标记区，一词一行。"""
    words = []
    if not path or not os.path.isfile(path):
        return words
    inside = False
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s == LEX_BEGIN:
                inside = True
                continue
            if s == LEX_END:
                break
            if inside and s and not s.startswith("#"):
                words.append(s.casefold())
    return words


def values_match(token, registry_values):
    """数值精确匹配：先去千分位逗号做字符串比对，再退化为浮点等值。"""
    t = token.replace(",", "")
    if t in registry_values:
        return True
    try:
        tf = float(t)
    except ValueError:
        return False
    for v in registry_values:
        try:
            if float(v) == tf:
                return True
        except ValueError:
            continue
    return False


def audit_claim(claim, docs, lexicon):
    cid = claim.get("claim_id", "?")
    locator = claim.get("locator") or {}
    file_ref = locator.get("file")
    anchor = claim.get("anchor")
    slide_text = str(claim.get("slide_text") or "")
    strength = str(claim.get("strength") or "").strip().casefold()
    extra = []

    nq = normalize(str(anchor) if anchor is not None else "")
    if not nq:
        return cid, "quote_empty", None, "anchor 为空或归一化后为空", extra

    if not file_ref or file_ref not in docs:
        return cid, "doc_missing", None, \
            f"locator.file '{file_ref}' 不在源索引中", extra

    doc = docs[file_ref]
    # A. 逐字锚定
    try:
        want_page = int(locator.get("pdf_page"))
    except (TypeError, ValueError):
        want_page = None
    anchor_state, found_page = "not_verbatim", None
    if want_page is not None:
        for pg in doc["pages"]:
            if pg["page"] == want_page and nq in pg["norm"]:
                anchor_state, found_page = "verified", want_page
                break
    if anchor_state != "verified":
        for pg in doc["pages"]:
            if nq in pg["norm"]:
                anchor_state, found_page = "page_mismatch", pg["page"]
                break

    # B. 数字防漂移扫描（slide_text 每个数字必须出自该文档数字注册表）
    bad_numbers = []
    for m in NUMBER_RE.finditer(slide_text):
        token = m.group(1)
        if not values_match(token, doc["number_values"]):
            bad_numbers.append(token)

    # C. 强度措辞门（preliminary/contextual 不得含过强词）
    bad_words = []
    if strength in WEAK_STRENGTHS:
        ntext = normalize(slide_text)
        for w in lexicon:
            if re.search(r"(?<![\w])" + re.escape(w) + r"(?![\w])", ntext):
                bad_words.append(w)

    # 汇总主状态与附加违例
    if anchor_state != "verified":
        primary = anchor_state
        detail = ("页内逐字命中" if anchor_state == "verified" else
                  f"引文实际位于第 {found_page} 页，声明页为 {want_page}"
                  if anchor_state == "page_mismatch" else
                  "归一化后全文档未命中（疑似凭记忆改写或臆造）")
        if bad_numbers:
            extra.append("number_not_in_source: " + ", ".join(bad_numbers))
        if bad_words:
            extra.append("strength_overclaim: " + ", ".join(bad_words))
        return cid, primary, found_page, detail, extra

    if bad_numbers:
        return cid, "number_not_in_source", found_page, \
            "slide_text 数字未在源数字注册表出现: " + ", ".join(bad_numbers), \
            (["strength_overclaim: " + ", ".join(bad_words)] if bad_words
             else extra)
    if bad_words:
        return cid, "strength_overclaim", found_page, \
            f"strength={strength} 的 slide_text 含过强词: " + \
            ", ".join(bad_words), extra
    return cid, "verified", found_page, "页内逐字命中，数字与措辞均合规", extra


def main():
    ap = argparse.ArgumentParser(description="页级主张焊接审计（anchor weld gate）")
    ap.add_argument("--claims", default="/app/work/claims.json",
                    help="claim card 清单（默认 /app/work/claims.json）")
    ap.add_argument("--index", default="/app/work/source_index.json",
                    help="source_index.py 产物（默认 /app/work/source_index.json）")
    ap.add_argument("--lexicon", default=None,
                    help="过强词表（默认 bundle 内 references/strength-lexicon.md）")
    ap.add_argument("--outdir", default=None,
                    help="产物目录（默认与 claims 同目录）")
    args = ap.parse_args()

    if not os.path.isfile(args.claims):
        print(f"[IO ERROR] claims 不存在: {args.claims}")
        return 2
    try:
        with open(args.claims, encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[SCHEMA ERROR] claims 不是合法 JSON: {e}")
        return 2
    claims = payload.get("claims") if isinstance(payload, dict) else payload
    if not isinstance(claims, list) or not claims:
        print("[SCHEMA ERROR] claims 必须是非空数组（或含 claims 数组的对象）")
        return 2
    for i, c in enumerate(claims):
        if not isinstance(c, dict):
            print(f"[SCHEMA ERROR] 第 {i + 1} 条 claim 不是对象")
            return 2
        missing = [k for k in REQUIRED_KEYS if k not in c]
        if missing:
            print(f"[SCHEMA ERROR] claim #{i + 1} 缺字段: {', '.join(missing)}")
            return 2
        if not isinstance(c.get("locator"), dict) or "file" not in c["locator"]:
            print(f"[SCHEMA ERROR] claim #{i + 1} locator 缺 file")
            return 2

    docs = load_index(args.index)
    if docs is None:
        print(f"[IO ERROR] 源索引不存在: {args.index}（先运行 source_index.py）")
        return 2
    lexicon_path = args.lexicon or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "references", "strength-lexicon.md")
    lexicon = load_lexicon(lexicon_path)
    if not lexicon:
        print(f"[IO ERROR] 过强词表为空或不可读: {lexicon_path}")
        return 2

    outdir = args.outdir or os.path.dirname(os.path.abspath(args.claims))
    os.makedirs(outdir, exist_ok=True)

    counts = {s: 0 for s in ALL_STATES}
    results = []
    failures = []
    for c in claims:
        cid, state, found_page, detail, extra = audit_claim(c, docs, lexicon)
        counts[state] += 1
        results.append({"claim_id": cid, "state": state,
                        "found_page": found_page, "detail": detail,
                        "extra_violations": extra})
        print(f"[anchor_audit] {cid}: {state} — {detail}"
              + (f" | 附加违例: {'; '.join(extra)}" if extra else ""))
        if state != "verified":
            failures.append(f"{cid}: {state} — {detail}")

    total = len(results)
    verified = counts["verified"]
    linkage = round(verified / total, 4) if total else None
    report = {
        "claims_file": os.path.abspath(args.claims),
        "index_file": os.path.abspath(args.index),
        "lexicon_file": os.path.abspath(lexicon_path),
        "total": total,
        "linkage_rate": linkage,
        "states": counts,
        "results": results,
    }
    rpath = os.path.join(outdir, "audit_report.json")
    with open(rpath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[anchor_audit] 汇总: {total} 条 claim，verified {verified} 条，"
          f"回链率 linkage_rate={linkage}")
    print(f"[anchor_audit] 状态计数: "
          + ", ".join(f"{s}={counts[s]}" for s in ALL_STATES))
    print(f"[anchor_audit] 报告写出: {rpath}")
    if failures:
        print("[anchor_audit] 未通过清单:")
        for item in failures:
            print("  - " + item)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
