#!/usr/bin/env python3
"""review_loop.py — 对抗式过程质量控制：写作与审核分离，审核不通过的论断不得交付。

子命令：
  prepare   解析案例包，为每题生成草稿文件（含 CLAIM/NOTE/ANSWER/CONDITIONS 区），
            并立即写 status=partial 骨架到 --out。
  audit     逐论断机器审核（尽力"证伪"）：
              F1 引文逐字（找不到 → unsupported）；
              F2 论断数值必须出现在引文中（缺失 → revise）；
              F3 引文含否定/转折语境（not/no significant/however/failed to）
                 而论断未体现 → revise（语境风险）；
              F4 论断含比较措辞（更高/优于/低于/倍/more/fewer）但引文中
                 不同取值不足两个 → revise；
              F5 论断含数值而引文中数值附近无单位 → warn（单位风险）；
            NOTE 行必须有"已核对"段落列表，否则 revise。
            输出 audit_report.json 与 audit.md，verdict ∈ pass / revise / unsupported。
  render    只把 verdict=pass 的论断写进 result.json；revise/unsupported 的论断
            降级为 unanswered_parts 条目（诚实部分结果），状态由审核记录机械推导；
            原子写出 /app/output/result.json（--legacy 时再写 /app/answers.json）。

标准库实现。模型写草稿，机器证伪，迭代到全 pass 或预算耗尽为止。
"""
import argparse
import json
import re
import sys
from pathlib import Path

NEG_RE = re.compile(r"\b(not|no|never|failed to|however|but|did not|does not|cannot)\b", re.I)
CMP_RE = re.compile(r"更高|更高|优于|低于|倍|高[约出达]|more than|fewer than|higher|lower|outperform", re.I)
NUM_RE = re.compile(r"(?<![A-Za-z0-9.])[-+]?\d+(?:\.\d+)?(?![A-Za-z0-9])")
UNIT_RE = re.compile(r"(MPa|GPa|Pa|mW|kW|W|eV|mm/s|mm/min|mg/L|mol|mL|L|percent|%|°C|degrees|K|h|min|s|ms|epoch|ms\b)", re.I)
STATUS_ENUM = {"answered", "partial", "insufficient_evidence", "input_error"}


def load_case(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    paras = {}
    src = raw.get("paragraphs") or raw.get("sections") or []
    for i, p in enumerate(src):
        if isinstance(p, dict):
            pid = str(p.get("paragraph_id") or p.get("id") or f"P{i + 1}")
            text = str(p.get("text") or p.get("content") or "")
        else:
            m = re.match(r"^\s*([A-Za-z0-9_.\-]+)\s*(.*)$", str(p), re.S)
            pid, text = (m.group(1), m.group(2)) if m else (f"P{i + 1}", str(p))
        paras[pid] = " ".join(text.split())
    for key, pre in (("tables", "T"), ("figure_captions", "F"), ("references", "R")):
        for j, item in enumerate(raw.get(key) or []):
            paras[f"{pre}{j + 1}"] = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
    qs = raw.get("questions") or []
    questions = [(str(q.get("question_id") or f"Q{i + 1}"), str(q.get("text") or q.get("question") or ""))
                 if isinstance(q, dict) else (f"Q{i + 1}", str(q)) for i, q in enumerate(qs)]
    return {"case_id": str(raw.get("case_id") or raw.get("id") or "unknown"),
            "paper_id": str(raw.get("paper_id") or raw.get("paper") or ""),
            "material_version": str(raw.get("material_version") or raw.get("version") or ""),
            "paragraphs": paras, "questions": questions,
            "output_contract": raw.get("output_contract") or {}}


def atomic_write(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def cmd_prepare(args):
    work = Path(args.work); work.mkdir(parents=True, exist_ok=True)
    try:
        case = load_case(args.case)
    except Exception as e:
        out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
        atomic_write(out / "result.json", json.dumps(
            {"case_id": "unknown", "paper_id": "unknown", "material_version": "unknown",
             "status": "input_error", "input_error": str(e), "answers": [],
             "coverage": {"read_sections": [], "unread_sections": []}},
            ensure_ascii=False, indent=1))
        sys.stderr.write(f"INPUT_ERROR: {e}\n")
        return 2
    drafts = work / "drafts"; drafts.mkdir(exist_ok=True)
    for qid, qtext in case["questions"]:
        (drafts / f"{qid}.md").write_text(f"""# {qid} 草稿

题目：{qtext}

## CLAIMS
# 格式：CLAIM reported|inferred | 中文论断 | P段号 "逐字引文" ; P段号 "引文2"
# 无法回答的子问：NOTE | 缺口描述 | 原因 | 已核对: P1,P2

## ANSWER
（由通过的论断合并成的连贯中文回答；材料未报告时写明核对范围）

## CONDITIONS
- （每条一个条件；没有则删除此行）
""", encoding="utf-8")
    (work / "case_norm.json").write_text(json.dumps(case, ensure_ascii=False, indent=1), encoding="utf-8")
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    atomic_write(out / "result.json", json.dumps({
        "case_id": case["case_id"], "paper_id": case["paper_id"],
        "material_version": case["material_version"], "status": "partial",
        "answers": [{"question_id": qid, "answer": "", "conditions": [], "status": "partial",
                     "claims": [], "unanswered_parts": [{"part": qtext, "reason": "草稿尚未提交审核"}]}
                    for qid, qtext in case["questions"]],
        "coverage": {"read_sections": [], "unread_sections": []}}, ensure_ascii=False, indent=1))
    print(f"prepare ok: {len(case['questions'])} draft(s), skeleton written -> {out}")
    return 0


CLAIM_LINE = re.compile(r'^CLAIM\s+(reported|inferred)\s*\|\s*(.+?)\s*\|\s*(.+)$')
NOTE_LINE = re.compile(r'^NOTE\s*\|\s*(.+?)\s*\|\s*(.+?)(?:\|\s*已核对[:：]\s*(.+))?$')
EV_RE = re.compile(r'([A-Za-z0-9_.\-]+)\s*"([^"]+)"')


def parse_draft(path):
    claims, notes, answer, conditions = [], [], "", []
    section = None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("## "):
            section = s[3:].strip().upper(); continue
        if not s or s.startswith("#"):
            continue
        if section == "CLAIMS":
            m = CLAIM_LINE.match(s)
            if m:
                evs = [(pid, q) for pid, q in EV_RE.findall(m.group(3))]
                claims.append({"kind": m.group(1), "text": m.group(2), "evidence": evs})
                continue
            m = NOTE_LINE.match(s)
            if m:
                notes.append({"part": m.group(1), "reason": m.group(2),
                              "checked": [t.strip() for t in (m.group(3) or "").split(",") if t.strip()]})
        elif section == "ANSWER":
            answer += s + "\n"
        elif section == "CONDITIONS" and s.startswith("- "):
            conditions.append(s[2:])
    return {"claims": claims, "notes": notes,
            "answer": answer.strip(), "conditions": conditions}


def audit_claim(claim, paras):
    """尽力证伪一条论断，返回 (verdict, findings[])。"""
    findings, quotes = [], ""
    for pid, quote in claim["evidence"]:
        q = " ".join(quote.split())
        if pid not in paras:
            findings.append(("F1", f"段落 {pid} 不在材料清单"))
        elif q not in paras[pid]:
            findings.append(("F1", f"引文不逐字（{pid}）: {q[:50]!r}"))
        else:
            quotes += " " + q
    if any(f[0] == "F1" for f in findings):
        return "unsupported", findings
    for num in set(NUM_RE.findall(claim["text"])):
        if num not in quotes:
            findings.append(("F2", f"论断数值 {num} 未出现在引文中"))
    neg = [w for w in NEG_RE.findall(quotes)]
    if neg and not NEG_RE.search(claim["text"]) and not re.search(r"未|不|无|否定|转折", claim["text"]):
        findings.append(("F3", f"引文含否定/转折语境 {sorted(set(neg))}，论断未体现"))
    if CMP_RE.search(claim["text"]):
        distinct = set(NUM_RE.findall(quotes))
        if len(distinct) < 2:
            findings.append(("F4", "论断含比较措辞但引文中不同取值不足两个"))
    if NUM_RE.search(claim["text"]) and not UNIT_RE.search(quotes):
        findings.append(("F5", "论断含数值但引文中未见单位（单位风险）"))
    hard = [f for f in findings if f[0] in ("F2", "F3", "F4")]
    return ("revise" if hard else "pass"), findings


def cmd_audit(args):
    work = Path(args.work)
    case = json.loads((work / "case_norm.json").read_text(encoding="utf-8"))
    report = {"questions": []}
    md = ["# 对抗审核报告", ""]
    for qid, _ in case["questions"]:
        dpath = work / "drafts" / f"{qid}.md"
        entry = {"question_id": qid, "claims": [], "notes": []}
        md.append(f"## {qid}")
        if not dpath.exists():
            entry["missing"] = True
            md.append("- 草稿缺失：整题按 partial 处理")
        else:
            draft = parse_draft(dpath)
            for i, c in enumerate(draft["claims"], 1):
                verdict, findings = audit_claim(c, case["paragraphs"])
                rec = {"idx": i, "kind": c["kind"], "text": c["text"][:80],
                       "verdict": verdict,
                       "findings": [{"rule": r, "msg": m} for r, m in findings]}
                entry["claims"].append(rec)
                tag = {"pass": "PASS", "revise": "REVISE", "unsupported": "UNSUPPORTED"}[verdict]
                md.append(f"- C{i} [{tag}] {c['text'][:60]}")
                for r, m in findings:
                    md.append(f"    - {r}: {m}")
            for n in draft["notes"]:
                ok = bool(n["checked"])
                entry["notes"].append({**n, "verdict": "pass" if ok else "revise"})
                if not ok:
                    md.append(f"- NOTE [REVISE] {n['part'][:50]}：缺『已核对』段落列表")
        report["questions"].append(entry)
    atomic_write(work / "audit_report.json", json.dumps(report, ensure_ascii=False, indent=1))
    atomic_write(work / "audit.md", "\n".join(md) + "\n")
    npass = sum(1 for q in report["questions"] for c in q.get("claims", []) if c["verdict"] == "pass")
    ntot = sum(len(q.get("claims", [])) for q in report["questions"])
    print(f"audit done: {npass}/{ntot} claims pass; report -> {work / 'audit.md'}")
    return 0


def cmd_render(args):
    work = Path(args.work)
    case = json.loads((work / "case_norm.json").read_text(encoding="utf-8"))
    report = json.loads((work / "audit_report.json").read_text(encoding="utf-8"))
    answers = []
    for qid, qtext in case["questions"]:
        qrep = next((q for q in report["questions"] if q["question_id"] == qid), {})
        draft = parse_draft(work / "drafts" / f"{qid}.md") if (work / "drafts" / f"{qid}.md").exists() \
            else {"claims": [], "notes": [], "answer": "", "conditions": []}
        verdicts = {c["idx"]: c for c in qrep.get("claims", [])}
        claims, ups = [], list(qrep.get("notes") and
                                 [{"part": n["part"], "reason": n["reason"] +
                                   ("（已核对：" + ",".join(n["checked"]) + "）" if n["checked"] else "（缺核对记录）")}
                                  for n in qrep["notes"] if n["verdict"] == "pass"] or [])
        for i, c in enumerate(draft["claims"], 1):
            v = verdicts.get(i, {})
            if v.get("verdict") == "pass":
                claims.append({"claim_id": f"{qid}-C{i}", "text": c["text"], "kind": c["kind"],
                               "evidence": [{"paragraph_id": pid, "quote": q}
                                            for pid, q in c["evidence"]]})
            else:
                why = "; ".join(f"{f['rule']}:{f['msg']}" for f in v.get("findings", [])) or "草稿缺失"
                ups.append({"part": c["text"][:80], "reason": f"论断未通过对抗审核（{v.get('verdict', 'not_audited')}）：{why}"})
        good_notes = [n for n in qrep.get("notes", []) if n["verdict"] == "pass"]
        if claims and not ups:
            status = "answered"
        elif claims:
            status = "partial"
        elif good_notes:
            status = "insufficient_evidence"
        else:
            status = "partial"
        answers.append({"question_id": qid, "answer": draft["answer"], "conditions": draft["conditions"],
                        "status": status, "claims": claims, "unanswered_parts": ups})
    result = {"case_id": case["case_id"], "paper_id": case["paper_id"],
              "material_version": case["material_version"],
              "status": "completed" if all(a["status"] in ("answered", "insufficient_evidence") for a in answers) else "partial",
              "answers": answers, "coverage": args.coverage and json.loads(Path(args.coverage).read_text(encoding="utf-8"))
              or {"read_sections": [], "unread_sections": []}}
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    atomic_write(out / "result.json", json.dumps(result, ensure_ascii=False, indent=1))
    if args.legacy:
        atomic_write(Path(args.legacy), json.dumps(result, ensure_ascii=False, indent=1))
    n = sum(1 for a in answers for _ in a["claims"])
    print(f"render ok: {n} claims delivered, status={result['status']} -> {out / 'result.json'}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--case", required=True)
    p.add_argument("--work", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("audit"); p.add_argument("--work", required=True)
    p = sub.add_parser("render"); p.add_argument("--work", required=True)
    p.add_argument("--out", required=True); p.add_argument("--legacy")
    p.add_argument("--coverage", help="coverage.json（可选，由留痕工具生成）")
    args = ap.parse_args()
    sys.exit({"prepare": cmd_prepare, "audit": cmd_audit, "render": cmd_render}[args.cmd](args))


if __name__ == "__main__":
    main()
