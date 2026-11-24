#!/usr/bin/env python3
"""verify_claims.py -- 论断保真核验器（开题论断保真管线的强制门）。

对 fact ledger（JSONL）逐条核验：
  - fact / number / citation：anchor 与 quote 均必填；quote 经归一化后必须是
    对应锚点段落文本的逐字子串，否则 fail；缺字段记 unverifiable（不静默放过）。
  - inference：不强制引文，但 claim_text 必须含「推断」字样；若附带 anchor+quote
    则同样做逐字核验；只给一个字段记 unverifiable。

归一化规则（只统一写法，不改字意）：
  1. unicodedata NFKC：全角字符折半角（ＡＢＣ→ABC、（→(、U+3000→空格）；
  2. 一切空白序列折叠为单个空格。
归一化后仍不命中 = 论断失真，fail。

退出码：0 = all_verified；1 = 存在 fail/unverifiable（或台账为空）。
被拦截的 claim_id 写入报告的 blocked 列表：这些论断禁止进入交付稿。
"""
import argparse
import json
import sys
import unicodedata

ANCHORED_KINDS = {"fact", "number", "citation"}
ALL_KINDS = ANCHORED_KINDS | {"inference"}
INFERENCE_MARK = "推断"


def squash(text):
    """全半角 + 空白归一化，供逐字比对使用。"""
    return " ".join(unicodedata.normalize("NFKC", text).split())


def load_anchor_texts(path):
    texts = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rec = json.loads(line)
                texts[rec["anchor"]] = rec["text"]
    return texts


def load_ledger(path):
    claims = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                claims.append(json.loads(line))
    return claims


def check_one(claim, anchors, fallback_id):
    cid = claim.get("claim_id") or fallback_id
    kind = claim.get("kind") or ""
    section = claim.get("section") or ""
    claim_text = claim.get("claim_text") or ""
    anchor = claim.get("anchor")
    quote = claim.get("quote")
    base = {"claim_id": cid, "kind": kind, "section": section, "anchor": anchor}

    if kind not in ALL_KINDS:
        return dict(base, status="unverifiable",
                    reason="kind 非法（须为 fact|number|citation|inference）"), False

    if kind == "inference":
        if INFERENCE_MARK not in claim_text:
            return dict(base, status="fail",
                        reason="inference 论断未在 claim_text 中标注「推断」"), False
        if anchor and quote:
            pass  # 附带引文：落入下方逐字核验
        elif anchor or quote:
            return dict(base, status="unverifiable",
                        reason="inference 引文不完整（anchor/quote 只给了一个）"), False
        else:
            return dict(base, status="ok",
                        reason="inference 无强制引文，已标注「推断」"), False

    # fact/number/citation 必核；inference 带完整引文也走到这里
    if not anchor or not quote:
        return dict(base, status="unverifiable",
                    reason="缺少 anchor 或 quote 字段"), False
    text = anchors.get(anchor)
    if text is None:
        return dict(base, status="fail",
                    reason="anchor 不在 anchor_map 中"), False
    if squash(quote) in squash(text):
        return dict(base, status="ok"), True
    return dict(base, status="fail",
                reason="quote 非锚点文本逐字子串（归一化后仍不命中）",
                quote_head=quote[:80]), False


def run(anchor_path, ledger_path, out_path, accepted_path=None):
    anchors = load_anchor_texts(anchor_path)
    claims = load_ledger(ledger_path)

    results = []
    blocked = []
    accepted = []
    n_ok = n_fail = n_unver = n_linked = 0
    for idx, claim in enumerate(claims, start=1):
        item, linked = check_one(claim, anchors, "C%03d" % idx)
        results.append(item)
        if item["status"] == "ok":
            n_ok += 1
            accepted.append(claim)
            if linked:
                n_linked += 1
        elif item["status"] == "fail":
            n_fail += 1
            blocked.append({"claim_id": item["claim_id"],
                            "status": "fail", "reason": item["reason"]})
        else:
            n_unver += 1
            blocked.append({"claim_id": item["claim_id"],
                            "status": "unverifiable", "reason": item["reason"]})

    total = len(claims)
    report = {"anchor_map": anchor_path, "ledger": ledger_path,
              "total": total, "ok": n_ok, "fail": n_fail,
              "unverifiable": n_unver,
              "all_verified": n_fail == 0 and n_unver == 0 and total > 0,
              "link_back_rate": round(n_linked / total, 4) if total else 0.0,
              "link_back_note": "回链率 = 逐字核验通过且带锚点的论断数 / 论断总数",
              "blocked": blocked,
              "results": results}
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    if accepted_path:
        with open(accepted_path, "w", encoding="utf-8") as fh:
            for claim in accepted:
                fh.write(json.dumps(claim, ensure_ascii=False) + "\n")
    print(json.dumps({"total": total, "ok": n_ok, "fail": n_fail,
                      "unverifiable": n_unver,
                      "all_verified": report["all_verified"],
                      "link_back_rate": report["link_back_rate"],
                      "blocked": [b["claim_id"] for b in blocked]},
                     ensure_ascii=False))
    return 0 if report["all_verified"] else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("anchor_map", help="anchor_extract.py 产出的 anchor_map.jsonl")
    ap.add_argument("ledger", help="fact ledger（JSONL，每行一条论断）")
    ap.add_argument("out", help="核验报告输出 JSON")
    ap.add_argument("--accepted", default=None,
                    help="可选：把核验通过（ok）的论断原样写到该 JSONL，供交付稿使用")
    args = ap.parse_args()
    return run(args.anchor_map, args.ledger, args.out, args.accepted)


if __name__ == "__main__":
    sys.exit(main())
