#!/usr/bin/env python3
"""render_contract.py — 下游渲染工程：契约驱动的确定性拼装。

子命令：
  init      解析案例包；从 output_contract 提取交付所需的全部顶层字段，
            写 contract.json（字段清单）；生成每题答题纸（sheets/Q*.md）；
            立即把含全部契约字段的骨架 result.json 写到 --out（占位值，
            status=partial）。
  refresh   每次改完答题纸后重渲染 result.json（幂等；占位字段保留，
            已作答题目如实更新）——部分结果始终落盘。
  finalize  严格校验后原子写出最终产物：契约字段一个不缺、无占位残留、
            引文逐字、问题全覆盖、状态枚举合法；通过则写
            /app/output/result.json 与 --legacy 指定的 /app/answers.json。
            流水线不产出的契约字段由 --extra 指定的 extra_fields.json 并入。

渲染是确定性的：模型从不手写 result.json。标准库实现。
"""
import argparse
import json
import re
import sys
from pathlib import Path

STATUS_ENUM = {"answered", "partial", "insufficient_evidence", "input_error"}
PLACEHOLDER = "<待填>"
BASELINE_FIELDS = ["case_id", "paper_id", "material_version",
                   "status", "answers", "coverage"]


def load_case(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    paras = {}
    for i, p in enumerate(raw.get("paragraphs") or raw.get("sections") or []):
        if isinstance(p, dict):
            pid = str(p.get("paragraph_id") or p.get("id") or f"P{i + 1}")
            paras[pid] = " ".join(str(p.get("text") or p.get("content") or "").split())
        else:
            m = re.match(r"^\s*([A-Za-z0-9_.\-]+)\s*(.*)$", str(p), re.S)
            pid, text = (m.group(1), m.group(2)) if m else (f"P{i + 1}", str(p))
            paras[pid] = " ".join(text.split())
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


def contract_fields(case):
    """契约顶层字段 = 基线字段 ∪ output_contract 声明的字段。"""
    fields = list(BASELINE_FIELDS)
    oc = case.get("output_contract") or {}
    if isinstance(oc, dict):
        for k in oc:
            if k not in fields:
                fields.append(k)
    elif isinstance(oc, list):
        for k in oc:
            if isinstance(k, str) and k not in fields:
                fields.append(k)
    return fields


def skeleton(case, fields, reason):
    result = {"case_id": case["case_id"], "paper_id": case["paper_id"],
              "material_version": case["material_version"], "status": "partial",
              "answers": [{"question_id": qid, "answer": "", "conditions": [],
                           "status": "partial", "claims": [],
                           "unanswered_parts": [{"part": qtext, "reason": reason}]}
                          for qid, qtext in case["questions"]],
              "coverage": {"read_sections": [], "unread_sections": []}}
    for f in fields:
        if f not in result:
            result[f] = PLACEHOLDER
    return result


def cmd_init(args):
    work = Path(args.work); work.mkdir(parents=True, exist_ok=True)
    try:
        case = load_case(args.case)
    except Exception as e:
        out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
        atomic_write(out / "result.json", json.dumps(
            {"case_id": "unknown", "status": "input_error", "input_error": str(e)},
            ensure_ascii=False, indent=1))
        sys.stderr.write(f"INPUT_ERROR: {e}\n")
        return 2
    fields = contract_fields(case)
    (work / "contract.json").write_text(json.dumps(
        {"required_top_level_fields": fields,
         "note": "流水线产出基线字段；其余字段必须经 --extra 的 extra_fields.json 提供"},
        ensure_ascii=False, indent=1), encoding="utf-8")
    (work / "case_norm.json").write_text(json.dumps(case, ensure_ascii=False, indent=1), encoding="utf-8")
    sheets = work / "sheets"; sheets.mkdir(exist_ok=True)
    for qid, qtext in case["questions"]:
        (sheets / f"{qid}.md").write_text(f"""# {qid} 答题纸

题目：{qtext}

STATUS: partial
ANSWER:
（中文回答；材料未报告时写明"已核对 P…，材料未报告 X"）
CONDITIONS: （分号分隔；无则留空）
CLAIM: reported | （中文论断） | P段号 "逐字引文" ; P段号 "引文2"
（每行一条 CLAIM；无法回答的子问用下行）
UNANSWERED: （缺口子问） | （原因）
""", encoding="utf-8")
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    atomic_write(out / "result.json", json.dumps(
        skeleton(case, fields, "答题纸尚未提交"), ensure_ascii=False, indent=1))
    print(f"init ok: contract fields={fields}; sheets -> {sheets}; skeleton -> {out}")
    return 0


CLAIM_LINE = re.compile(r'^CLAIM:\s*(reported|inferred)\s*\|\s*(.+?)\s*\|\s*(.+)$')
EV_RE = re.compile(r'([A-Za-z0-9_.\-]+)\s*"([^"]+)"')


def parse_sheet(path):
    d = {"status": "partial", "answer": "", "conditions": [], "claims": [], "unanswered_parts": []}
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if s.startswith("STATUS:"):
            d["status"] = s.split(":", 1)[1].strip()
        elif s.startswith("ANSWER:"):
            buf = [s.split(":", 1)[1].strip()]
            i += 1
            while i < n and not re.match(r"^(STATUS|CONDITIONS|CLAIM|UNANSWERED):", lines[i].strip()):
                if lines[i].strip() and not lines[i].strip().startswith(("（", "(", "#")):
                    buf.append(lines[i].strip())
                i += 1
            d["answer"] = "\n".join(b for b in buf if b).strip()
            continue
        elif s.startswith("CONDITIONS:"):
            d["conditions"] = [t.strip() for t in s.split(":", 1)[1].split(";") if t.strip()
                               and not t.strip().startswith("（")]
        elif s.startswith("CLAIM:"):
            m = CLAIM_LINE.match(s)
            if m:
                d["claims"].append({"kind": m.group(1), "text": m.group(2),
                                    "evidence": EV_RE.findall(m.group(3))})
        elif s.startswith("UNANSWERED:"):
            part = s.split(":", 1)[1]
            if "|" in part:
                p, r = part.split("|", 1)
                if p.strip() and not p.strip().startswith("（"):
                    d["unanswered_parts"].append({"part": p.strip(), "reason": r.strip()})
        i += 1
    return d


def render(work, out_path=None, legacy=None, extra=None, strict=False):
    case = json.loads((work / "case_norm.json").read_text(encoding="utf-8"))
    contract = json.loads((work / "contract.json").read_text(encoding="utf-8"))
    fields = contract["required_top_level_fields"]
    extra_data = json.loads(Path(extra).read_text(encoding="utf-8")) if extra else {}
    errors, warns = [], []

    answers = []
    for qid, qtext in case["questions"]:
        sp = work / "sheets" / f"{qid}.md"
        if sp.exists():
            d = parse_sheet(sp)
        else:
            d = {"status": "partial", "answer": "", "conditions": [], "claims": [],
                 "unanswered_parts": [{"part": qtext, "reason": "答题纸缺失"}]}
        claims = []
        for j, c in enumerate(d["claims"], 1):
            cid = f"{qid}-C{j}"
            for pid, quote in c["evidence"]:
                q = " ".join(quote.split())
                if pid not in case["paragraphs"]:
                    errors.append(f"{qid}/{cid}: 证据段落 {pid} 不在材料清单")
                elif q not in case["paragraphs"][pid]:
                    errors.append(f"{qid}/{cid}: 引文不逐字（{pid}）: {q[:50]!r}")
            claims.append({"claim_id": cid, "text": c["text"], "kind": c["kind"],
                           "evidence": [{"paragraph_id": pid, "quote": q}
                                        for pid, q in c["evidence"]]})
        status = d["status"]
        if status not in STATUS_ENUM:
            errors.append(f"{qid}: status 非法 {status!r}"); status = "partial"
        answers.append({"question_id": qid, "answer": d["answer"], "conditions": d["conditions"],
                        "status": status, "claims": claims,
                        "unanswered_parts": d["unanswered_parts"]})

    result = {"case_id": case["case_id"], "paper_id": case["paper_id"],
              "material_version": case["material_version"],
              "status": "completed" if all(a["status"] in ("answered", "insufficient_evidence")
                                           for a in answers) else "partial",
              "answers": answers,
              "coverage": {"read_sections": [], "unread_sections": []}}
    for f in fields:
        if f not in result:
            if f in extra_data:
                result[f] = extra_data[f]
            else:
                result[f] = PLACEHOLDER
                (errors if strict else warns).append(
                    f"契约字段 {f!r} 流水线不产出，需 --extra extra_fields.json 提供")
    # extra_fields 中契约未声明的键不并入（防串味）
    for k in extra_data:
        if k not in fields:
            warns.append(f"extra_fields 的键 {k!r} 不在契约中，未并入")

    text = json.dumps(result, ensure_ascii=False, indent=1)
    if out_path:
        atomic_write(Path(out_path), text)
    if legacy and not (strict and errors):
        atomic_write(Path(legacy), text)
    return result, errors, warns


def cmd_refresh(args):
    work = Path(args.work)
    result, errors, warns = render(work, out_path=str(Path(args.out) / "result.json"),
                                   legacy=args.legacy, extra=args.extra)
    for w in warns:
        print("WARN:", w)
    for e in errors:
        print("ERROR:", e)
    print(f"refresh ok: status={result['status']}（部分结果已落盘）")
    return 0


def cmd_finalize(args):
    work = Path(args.work)
    result, errors, warns = render(work, strict=True, extra=args.extra)
    for w in warns:
        print("WARN:", w)
    for e in errors:
        print("ERROR:", e)
    if errors:
        print(f"finalize FAILED: {len(errors)} error(s)；产物未写。")
        return 1
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(result, ensure_ascii=False, indent=1)
    atomic_write(out / "result.json", text)
    if args.legacy:
        atomic_write(Path(args.legacy), text)
    print(f"finalize ok: status={result['status']} -> {out / 'result.json'}"
          + (f" 与 {args.legacy}" if args.legacy else ""))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--case", required=True)
    p.add_argument("--work", required=True); p.add_argument("--out", required=True)
    for name in ("refresh", "finalize"):
        p = sub.add_parser(name); p.add_argument("--work", required=True)
        p.add_argument("--out", required=True); p.add_argument("--legacy")
        p.add_argument("--extra", help="extra_fields.json：流水线不产出的契约字段")
    args = ap.parse_args()
    sys.exit({"init": cmd_init, "refresh": cmd_refresh, "finalize": cmd_finalize}[args.cmd](args))


if __name__ == "__main__":
    main()
