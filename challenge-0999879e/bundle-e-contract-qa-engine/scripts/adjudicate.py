#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adjudicate.py — 候选 findings 的机器复核（Pass 2 误报抑制）。

子命令：
  scaffold  生成 work/findings_candidate.json 模板（供 Agent 填写）
  check     对 work/findings_candidate.json 执行机械复核：
    ① 必填字段齐全：facet / type / severity / location.anchor /
       original_text / evidence / suggestion
    ② 枚举合法性：severity ∈ {critical,major,minor,info}；
       type ∈ {事实错误,证据不足,规范问题,建议性意见,方法缺陷,报告不全}；
       facet ∈ 六分面
    ③ 锚点复验：original_text 空白归一化后必须出现在 /input 抽取文本中，
       否则降级 pending_review
    ④ 误报抑制：命中学科惯例豁免词表、type-facet 不一致 → 提示 recheck
  输出 work/adjudication_report.json，每条 accepted / downgraded / rejected
  及理由，全程留痕。

处置优先级：rejected > downgraded > accepted。
仅使用 Python 3 标准库。
"""
import argparse
import json
import os
import sys
import tempfile

FACETS = ["事实核验", "引用支持", "方法设计", "统计报告", "论证链", "学术规范"]
SEVERITIES = ["critical", "major", "minor", "info"]
TYPES = ["事实错误", "证据不足", "规范问题", "建议性意见", "方法缺陷", "报告不全"]

# facet -> 推荐的 type 集合（越界不判错，仅提示 recheck）
TYPE_FACET_MAP = {
    "事实核验": {"事实错误"},
    "引用支持": {"证据不足"},
    "方法设计": {"方法缺陷"},
    "统计报告": {"报告不全", "事实错误", "方法缺陷"},
    "论证链": {"证据不足", "建议性意见", "方法缺陷"},
    "学术规范": {"规范问题", "报告不全"},
}

# 学科写作惯例豁免词表：命中即提示 recheck（详见 references/false_positive_suppression.md）
EXEMPTION_WORDS = [
    "按目标期刊惯例", "按期刊惯例", "按本刊惯例", "遵循期刊格式", "按期刊要求",
    "依本领域惯例", "按领域惯例", "按学科惯例", "遵循本领域惯例",
    "按编辑部要求", "按出版方要求", "格式从简", "此处从简",
]

# 硬必填：缺失即 rejected；软必填：缺失即 downgraded
HARD_REQUIRED = ["facet", "type", "severity", "original_text"]
SOFT_REQUIRED = ["evidence", "suggestion"]


def eprint(*a):
    print(*a, file=sys.stderr)


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def atomic_write_json(path, obj):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def norm_ws(s):
    """空白归一化：删除全部空白字符后比较。"""
    return "".join(str(s).split())


TEMPLATE_ENTRY = {
    "facet": "事实核验",
    "type": "事实错误",
    "severity": "major",
    "location": {"file": "manuscript.md", "section": "摘要", "anchor": "原文短引"},
    "original_text": "（从稿件原文逐字摘抄、用于锚点复验的句子，≤80 字）",
    "evidence": "（判定依据：与原文何处矛盾 / 缺什么 / 违反哪条规范；禁止编造文献与页码）",
    "suggestion": "（可交办的具体修改建议）",
}


def cmd_scaffold(args):
    os.makedirs(args.work_dir, exist_ok=True)
    path = os.path.join(args.work_dir, "findings_candidate.json")
    if os.path.exists(path) and not args.force:
        eprint("ERROR: %s 已存在；用 --force 覆盖" % path)
        return 2
    doc = {
        "_说明": [
            "本文件由 Agent 填写：每条 finding 必须含 facet/type/severity/location.anchor/",
            "original_text/evidence/suggestion。original_text 必须逐字摘自稿件原文，",
            "adjudicate check 会对其做锚点复验；无法确认的条目不要写进本文件。",
            "facet 取值：" + " / ".join(FACETS),
            "type 取值：" + " / ".join(TYPES),
            "severity 取值：" + " / ".join(SEVERITIES),
        ],
        "findings": [dict(TEMPLATE_ENTRY) for _ in range(args.count)],
    }
    atomic_write_json(path, doc)
    print("SCAFFOLD_OK path=%s entries=%d" % (path, args.count))
    return 0


def adjudicate_entry(idx, f, corpus_norm):
    reasons, hints = [], []
    if not isinstance(f, dict):
        return {"index": idx, "disposition": "rejected",
                "reasons": ["条目不是 JSON object"], "recheck_hints": [], "finding": f}

    # ① 必填字段
    hard_missing = [k for k in HARD_REQUIRED
                    if not (isinstance(f.get(k), str) and f.get(k).strip())]
    soft_missing = [k for k in SOFT_REQUIRED
                    if not (isinstance(f.get(k), str) and f.get(k).strip())]
    loc = f.get("location")
    anchor_ok = isinstance(loc, dict) and isinstance(loc.get("anchor"), str) \
        and loc.get("anchor").strip()
    if hard_missing:
        reasons.append("硬必填字段缺失或为空: " + ", ".join(hard_missing))
    if soft_missing:
        reasons.append("软必填字段缺失或为空（降级 pending_review）: " + ", ".join(soft_missing))
    if not anchor_ok:
        reasons.append("location.anchor 缺失或为空（降级 pending_review）")

    # ② 枚举合法性（非法即 rejected）
    sev, typ, facet = f.get("severity"), f.get("type"), f.get("facet")
    if isinstance(sev, str) and sev not in SEVERITIES:
        reasons.append("severity 非法值 %r（合法值: %s）" % (sev, "/".join(SEVERITIES)))
    if isinstance(typ, str) and typ not in TYPES:
        reasons.append("type 非法值 %r（合法值: %s）" % (typ, "/".join(TYPES)))
    if isinstance(facet, str) and facet not in FACETS:
        reasons.append("facet 非法值 %r（合法值: %s）" % (facet, "/".join(FACETS)))

    rejected = bool(hard_missing) or any(
        r.startswith(("severity 非法值", "type 非法值", "facet 非法值")) for r in reasons)
    if rejected:
        return {"index": idx, "disposition": "rejected", "reasons": reasons,
                "recheck_hints": hints, "finding": f}

    # ③ 锚点复验：original_text 空白归一化后必须出现在抽取文本中
    ot_norm = norm_ws(f["original_text"])
    anchor_pos = corpus_norm.find(ot_norm)
    if anchor_pos < 0:
        reasons.append("锚点复验失败：original_text（空白归一化后）未在 /input 抽取文本中复验到，"
                       "疑似编造或转述，降级 pending_review")
    elif not anchor_ok:
        # original_text 复验通过但 location.anchor 缺失，已在 soft 里记过
        pass

    # ④ 误报抑制
    joined = " ".join(str(f.get(k, "")) for k in
                      ("original_text", "evidence", "suggestion", "title"))
    hits = [w for w in EXEMPTION_WORDS if w in joined]
    if hits:
        hints.append("命中豁免词表 %s：疑似学科/期刊惯例被误判为缺陷，请人工 recheck"
                     "（见 references/false_positive_suppression.md）" % "、".join(hits))
    allowed = TYPE_FACET_MAP.get(facet, set())
    if facet in TYPE_FACET_MAP and typ in TYPES and typ not in allowed:
        hints.append("type 与 facet 不一致：facet=%s 通常对应 type ∈ {%s}，当前 type=%s，"
                     "请 recheck 是否归类正确" % (facet, "、".join(sorted(allowed)), typ))

    if anchor_pos < 0 or soft_missing or not anchor_ok:
        disposition = "downgraded"
        reasons.append("处置：pending_review（不凭空补结论，待人工复核）")
    else:
        disposition = "accepted"
    entry = {"index": idx, "disposition": disposition, "reasons": reasons,
             "recheck_hints": hints, "finding": f}
    if anchor_pos >= 0:
        entry["anchor_pos"] = anchor_pos
    return entry


def cmd_check(args):
    cand_path = os.path.join(args.work_dir, "findings_candidate.json")
    text_path = os.path.join(args.work_dir, "extracted_text.txt")
    if not os.path.isfile(cand_path):
        eprint("ERROR: 未找到 %s（先用 scaffold 生成模板并由 Agent 填写）" % cand_path)
        return 2
    if not os.path.isfile(text_path):
        eprint("ERROR: 未找到 %s（先运行 contract_init.py）" % text_path)
        return 2
    try:
        cand = json.loads(read_text(cand_path))
    except json.JSONDecodeError as ex:
        eprint("ERROR: findings_candidate.json 不是合法 JSON: %s" % ex)
        return 2
    findings = cand.get("findings") if isinstance(cand, dict) else cand
    if not isinstance(findings, list):
        eprint("ERROR: findings_candidate.json 应为 list 或含 findings 数组的 object")
        return 2

    corpus_norm = norm_ws(read_text(text_path))
    entries = [adjudicate_entry(i, f, corpus_norm) for i, f in enumerate(findings)]
    summary = {
        "total": len(entries),
        "accepted": sum(1 for e in entries if e["disposition"] == "accepted"),
        "downgraded": sum(1 for e in entries if e["disposition"] == "downgraded"),
        "rejected": sum(1 for e in entries if e["disposition"] == "rejected"),
        "recheck_hints": sum(1 for e in entries if e["recheck_hints"]),
    }
    report = {
        "case_id": _read_case_id(args.work_dir),
        "checks": ["required_fields", "enum_validity", "anchor_recheck",
                   "exemption_wordlist", "type_facet_consistency"],
        "summary": summary,
        "entries": entries,
    }
    out = os.path.join(args.work_dir, "adjudication_report.json")
    atomic_write_json(out, report)
    print("ADJUDICATE_OK total=%(total)d accepted=%(accepted)d downgraded=%(downgraded)d "
          "rejected=%(rejected)d recheck=%(recheck_hints)d report=%(report)s"
          % dict(summary, report=out))
    return 0


def _read_case_id(work_dir):
    p = os.path.join(work_dir, "answer_sheet.json")
    try:
        return json.loads(read_text(p)).get("case_id")
    except Exception:  # noqa: BLE001
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="候选 findings 机器复核（Pass 2 误报抑制）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("scaffold", help="生成 findings_candidate.json 模板")
    sp.add_argument("--work-dir", default="/app/work")
    sp.add_argument("--count", type=int, default=1, help="模板条目数（默认 1）")
    sp.add_argument("--force", action="store_true", help="覆盖已存在文件")
    sp.set_defaults(func=cmd_scaffold)
    cp = sub.add_parser("check", help="执行机械复核并输出 adjudication_report.json")
    cp.add_argument("--work-dir", default="/app/work")
    cp.set_defaults(func=cmd_check)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
