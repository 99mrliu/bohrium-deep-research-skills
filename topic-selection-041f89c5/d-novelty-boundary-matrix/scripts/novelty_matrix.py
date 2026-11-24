#!/usr/bin/env python3
"""novelty_matrix.py — 创新陈述×已有工作覆盖矩阵与划界判定器。

把提案的每条创新陈述与已有工作逐一对账，按强制规则给出划界判定，
杜绝"首次""填补空白"式无据宣称。

输入：
  --claims claims.json：
    {"proposal_title": "...",
     "search_boundary": "本判断覆盖的来源与时间窗声明（必填）",
     "claims": [{"id": "C1", "text": "创新陈述",
                 "type": "method|data|scenario|conclusion"}]}
  --judgments judgments.jsonl（每行）：
    {"claim_id": "C1", "work_id": "W1",
     "relation": "covers|partial|none",
     "evidence_anchor": "来源文件#定位",   # covers/partial 必填
     "note": "..."}

判定规则（脚本强制，不允许绕过）：
  V1 某条 judgment relation=covers     → covered（已被覆盖）
  V2 无 covers 但有 partial            → partial（部分覆盖）
  V3 全部 none 且 claims.json 声明了 search_boundary → uncovered（未见覆盖）
  V4 该 claim 无任何 judgment，或全部 none 但缺 search_boundary
                                       → indeterminate（无法判定）
一致性检查（违例，判 audit_failed=False 之外的硬输出）：
  X1 covers/partial 的 judgment 缺 evidence_anchor → 违例
  X2 judgment 引用了不存在的 claim_id → 违例
  X3 claim.type 不在四类枚举 → 违例

输出（--out 目录）：
  novelty_matrix.md    覆盖矩阵（claim × work）
  verdicts.json        每条 claim 的判定与依据
  boundary_memo.md     划界备忘录（含检索边界声明与不确定项）
退出码：无违例 0；有违例 1；参数错误 2。仅标准库。
"""
import argparse
import json
import sys
from pathlib import Path

TYPES = {"method", "data", "scenario", "conclusion"}
REL = {"covers", "partial", "none"}
TYPE_ZH = {"method": "方法创新", "data": "数据创新",
           "scenario": "场景迁移", "conclusion": "结论修正"}


def verdict_for(judgments, has_boundary):
    if not judgments:
        return "indeterminate", "无任何对账记录"
    if any(j["relation"] == "covers" for j in judgments):
        return "covered", "被 %s 覆盖" % "、".join(
            j["work_id"] for j in judgments if j["relation"] == "covers")
    if any(j["relation"] == "partial" for j in judgments):
        return "partial", "被 %s 部分覆盖" % "、".join(
            j["work_id"] for j in judgments if j["relation"] == "partial")
    if has_boundary:
        return "uncovered", "对账范围内未见覆盖（边界见备忘录）"
    return "indeterminate", "未见覆盖但未声明检索边界，判定不成立"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--claims", required=True)
    ap.add_argument("--judgments", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    doc = json.loads(Path(args.claims).read_text(encoding="utf-8"))
    claims = doc.get("claims") or []
    boundary = (doc.get("search_boundary") or "").strip()
    claim_ids = {c["id"] for c in claims}
    judgments = []
    with open(args.judgments, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                judgments.append(json.loads(line))

    violations = []
    for j in judgments:
        if j.get("claim_id") not in claim_ids:
            violations.append("judgment 引用不存在的 claim_id: %s（X2）"
                              % j.get("claim_id"))
        if j.get("relation") in ("covers", "partial") \
                and not (j.get("evidence_anchor") or "").strip():
            violations.append("%s×%s: %s 判定缺 evidence_anchor（X1）"
                              % (j.get("claim_id"), j.get("work_id"),
                                 j.get("relation")))
    for c in claims:
        if c.get("type") not in TYPES:
            violations.append("claim %s 类型非法: %r（X3）"
                              % (c.get("id"), c.get("type")))
        for j in judgments:
            if j.get("claim_id") == c["id"] and j.get("relation") not in REL:
                violations.append("%s×%s: relation 非法 %r"
                                  % (c["id"], j.get("work_id"),
                                     j.get("relation")))

    by_claim = {c["id"]: [] for c in claims}
    for j in judgments:
        if j.get("claim_id") in by_claim:
            by_claim[j["claim_id"]].append(j)

    works = sorted({j.get("work_id") for j in judgments} - {None})
    verdicts = {}
    for c in claims:
        v, basis = verdict_for(by_claim[c["id"]], bool(boundary))
        verdicts[c["id"]] = {"text": c.get("text"), "type": c.get("type"),
                             "type_zh": TYPE_ZH.get(c.get("type"), "?"),
                             "verdict": v, "basis": basis}

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    out.joinpath("verdicts.json").write_text(json.dumps(
        {"proposal": doc.get("proposal_title"), "search_boundary": boundary,
         "violations": violations, "verdicts": verdicts},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    mark = {"covers": "●", "partial": "◐", "none": "○"}
    lines = ["# 创新点×已有工作覆盖矩阵", "",
             "提案：%s" % (doc.get("proposal_title") or "未命名"), "",
             "| 创新陈述 | 类型 | " + " | ".join(works) + " | 判定 |",
             "|---|---|" + "---|" * (len(works) + 1)]
    for c in claims:
        row = [c["id"] + " " + (c.get("text") or "")[:30],
               TYPE_ZH.get(c.get("type"), "?")]
        js = {j["work_id"]: j["relation"] for j in by_claim[c["id"]]}
        row += [mark.get(js.get(w), "—") for w in works]
        row.append(verdicts[c["id"]]["verdict"])
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "图例：● 覆盖　◐ 部分覆盖　○ 未见覆盖　— 未对账", ""]
    out.joinpath("novelty_matrix.md").write_text("\n".join(lines),
                                                 encoding="utf-8")

    memo = ["# 创新划界备忘录", "",
            "检索/覆盖边界声明：%s" % (boundary or "**未声明——uncovered 判定不成立**"),
            ""]
    for cid, v in verdicts.items():
        memo.append("- **%s**（%s）：%s。依据：%s"
                    % (cid, v["type_zh"], v["verdict"], v["basis"]))
    if violations:
        memo += ["", "## 一致性违例（必须修复后方可交付）"]
        memo += ["- " + x for x in violations]
    memo += ["", "注意：uncovered 只表示在上述边界内未见覆盖，"
                 "不等于“国内外尚无研究”；扩大边界需重新对账并更新本备忘录。", ""]
    out.joinpath("boundary_memo.md").write_text("\n".join(memo),
                                                encoding="utf-8")
    print(json.dumps({"violations": len(violations),
                      "verdicts": {k: v["verdict"] for k, v in verdicts.items()}},
                     ensure_ascii=False))
    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main())
