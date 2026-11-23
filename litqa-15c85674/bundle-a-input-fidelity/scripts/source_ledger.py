#!/usr/bin/env python3
"""source_ledger.py — 案例包"上游数据真实性"工具。

四个子命令覆盖一条流水线：
  audit    宽容解析 /input/case.json 常见字段变体；逐段完整性审计
           （重复编号、空文本、编码损伤、截断、非 UTF-8 控制字符）；
           按启发式把每段归类为 abstract / body / table / caption / reference；
           为每段计算 SHA-256 作为版本坐标；输出归一化案例、材料清单、
           以及一份所有问题状态为 partial 的诚实骨架 result.json。
  mark     登记"实际读过哪些段落"（读取留痕，幂等去重）。
  coverage 依据读取留痕与材料清单机械推导 coverage 字段（不依赖模型自述）。
  check    对拟提交的 result.json 做机器校验：问题全覆盖、引文逐字、
           编号存在、status 枚举合法、claims 字段齐备。ERROR 时退出码 1。

只用 Python 标准库（3.10+）。所有路径由调用方显式传入，脚本不假设目录结构。
"""
import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

STATUS_ENUM = {"answered", "partial", "insufficient_evidence", "input_error"}
KIND_ENUM = {"reported", "inferred"}

# ---------- 宽容解析 ----------

def _first(d, *keys):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] not in (None, ""):
            return d[k]
    return None


def _as_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def _norm_paragraphs(raw_paras):
    """把段落清单的多种写法归一化成 [{paragraph_id, text}]。"""
    out = []
    for i, p in enumerate(_as_list(raw_paras)):
        if isinstance(p, str):
            m = re.match(r"^\s*(\[[A-Za-z0-9_.\-]+\]|P\d+|T\d+|F\d+|R\d+|Ref\d+)\s*", p)
            pid = m.group(1).strip("[]") if m else f"P{i + 1}"
            text = p[m.end():].strip() if m else p.strip()
        elif isinstance(p, dict):
            pid = _first(p, "paragraph_id", "id", "pid", "para_id", "number") or f"P{i + 1}"
            text = _first(p, "text", "content", "body", "paragraph") or ""
            if not isinstance(text, str):
                text = json.dumps(text, ensure_ascii=False)
        else:
            pid, text = f"P{i + 1}", str(p)
        out.append({"paragraph_id": str(pid), "text": str(text)})
    return out


def _norm_questions(raw_qs):
    out = []
    for i, q in enumerate(_as_list(raw_qs)):
        if isinstance(q, str):
            out.append({"question_id": f"Q{i + 1}", "text": q})
        elif isinstance(q, dict):
            qid = _first(q, "question_id", "id", "qid", "number") or f"Q{i + 1}"
            text = _first(q, "text", "question", "content", "prompt") or ""
            out.append({"question_id": str(qid), "text": str(text)})
    return out


def load_case(case_path):
    """宽容解析案例包，返回归一化字典；解析失败抛 InputError。"""
    try:
        raw = json.loads(Path(case_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as e:
        raise InputError(f"案例包不可读取或不是 UTF-8：{e}")
    except json.JSONDecodeError as e:
        raise InputError(f"案例包不是合法 JSON：{e}")
    if not isinstance(raw, dict):
        raise InputError("案例包顶层必须是 JSON 对象")

    case_id = _first(raw, "case_id", "caseId", "id")
    paper_id = _first(raw, "paper_id", "paperId", "paper")
    version = _first(raw, "material_version", "materialVersion", "version", "material")
    if case_id is None:
        raise InputError("案例包缺少 case_id 字段")

    paragraphs = None
    for k in ("paragraphs", "sections", "passages"):
        if k in raw:
            paragraphs = _norm_paragraphs(raw[k]); break
    if paragraphs is None:
        for k in ("content", "material"):
            if isinstance(raw.get(k), dict) and isinstance(raw[k].get("paragraphs"), list):
                paragraphs = _norm_paragraphs(raw[k]["paragraphs"]); break
    if paragraphs is None:
        raise InputError("案例包缺少段落清单（paragraphs / sections / passages 均未找到）")

    # 表格、图注、参考文献若独立给出则并入段落清单
    for k, prefix in (("tables", "T"), ("figure_captions", "F"), ("references", "R")):
        if k in raw:
            for j, item in enumerate(_as_list(raw[k])):
                text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
                paragraphs.append({"paragraph_id": f"{prefix}{j + 1}", "text": str(text)})

    questions = None
    for k in ("questions", "question_list", "queries"):
        if k in raw:
            questions = _norm_questions(raw[k]); break
    if questions is None:
        raise InputError("案例包缺少问题清单（questions 未找到）")

    return {
        "case_id": str(case_id),
        "paper_id": str(paper_id) if paper_id else "",
        "material_version": str(version) if version else "",
        "paragraphs": paragraphs,
        "questions": questions,
        "task": _first(raw, "task", "task_description", "instruction") or "",
        "output_contract": raw.get("output_contract") or {},
    }


class InputError(Exception):
    pass

# ---------- 完整性审计与归类 ----------

CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffd]")

SECTION_RULES = [
    ("abstract", re.compile(r"(abstract|摘要)", re.I)),
    ("table", re.compile(r"^(Table\s*\d|表\s*\d)", re.I)),
    ("caption", re.compile(r"^(Figure\s*\d|Fig\.?\s*\d|图\s*\d)", re.I)),
    ("reference", re.compile(r"(et al\.|doi:|isbn)", re.I)),
]


def classify(text):
    for name, rx in SECTION_RULES:
        if rx.search(text[:120]):
            return name
    return "body"


def audit_paragraphs(paragraphs):
    """返回 [(para, section, sha8, flags)]，flags 为空字符串表示无异常。"""
    rows, seen = [], {}
    for para in paragraphs:
        pid, text = para["paragraph_id"], para["text"]
        flags = []
        if not text.strip():
            flags.append("empty")
        if CONTROL_RE.search(text):
            flags.append("encoding_damage")
        if text.strip() and not text.strip().endswith((".", "!", "?", "。", "；", ";", "]", ")", "”")):
            flags.append("possible_truncation")
        if pid in seen:
            flags.append(f"duplicate_id(first={seen[pid]})")
        else:
            seen[pid] = len(rows) + 1
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
        rows.append((para, classify(text), sha, ";".join(flags) or "-"))
    return rows


def norm_ws(s):
    return " ".join(str(s).split())


def quote_found(quote, text):
    return norm_ws(quote) in norm_ws(text)

# ---------- 子命令实现 ----------

def cmd_audit(args):
    work = Path(args.work); work.mkdir(parents=True, exist_ok=True)
    try:
        case = load_case(args.case)
    except InputError as e:
        sys.stderr.write(f"INPUT_ERROR: {e}\n")
        err_dir = Path(args.out) if args.out else work
        err_dir.mkdir(parents=True, exist_ok=True)
        write_input_error_skeleton(err_dir, str(e))
        return 2

    rows = audit_paragraphs(case["paragraphs"])
    norm = dict(case)
    norm["paragraphs"] = [
        {"paragraph_id": p["paragraph_id"], "text": p["text"], "section": sec, "sha256": sha}
        for p, sec, sha, _ in rows
    ]
    (work / "case_norm.json").write_text(
        json.dumps(norm, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = [f"# 材料清单（{case['case_id']} / {case['paper_id']} / {case['material_version']}）",
             "", "| 段落编号 | 类别 | 字符数 | SHA-8 | 完整性标记 |", "|-|-|-:|-|-|"]
    for p, sec, sha, flags in rows:
        lines.append(f"| {p['paragraph_id']} | {sec} | {len(p['text'])} | {sha} | {flags} |")
    bad = [r for r in rows if r[3] != "-"]
    lines += ["", f"共 {len(rows)} 段；完整性异常 {len(bad)} 段。"]
    (work / "inventory.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if args.out:
        out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
        write_skeleton(out, case, reason="输入解析完成，作答尚未开始")
    print(f"audit ok: {len(rows)} paragraphs, {len(bad)} flagged, "
          f"{len(case['questions'])} questions -> {work}")
    return 0


def write_skeleton(out_dir, case, reason):
    result = {
        "case_id": case["case_id"], "paper_id": case["paper_id"],
        "material_version": case["material_version"], "status": "partial",
        "answers": [{"question_id": q["question_id"], "answer": "",
                     "conditions": [], "status": "partial", "claims": [],
                     "unanswered_parts": [{"part": q["text"], "reason": reason}]}
                    for q in case["questions"]],
        "coverage": {"read_sections": [], "unread_sections": []},
    }
    atomic_write(out_dir / "result.json", json.dumps(result, ensure_ascii=False, indent=1))


def write_input_error_skeleton(out_dir, reason):
    result = {"case_id": "unknown", "paper_id": "unknown", "material_version": "unknown",
              "status": "input_error", "answers": [], "input_error": str(reason),
              "coverage": {"read_sections": [], "unread_sections": []}}
    atomic_write(out_dir / "result.json", json.dumps(result, ensure_ascii=False, indent=1))


def cmd_mark(args):
    work = Path(args.work)
    ledger = work / "reading_ledger.jsonl"
    read = {t.strip() for t in args.read.split(",") if t.strip()}
    old = set()
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if line.strip():
                old |= set(json.loads(line).get("read", []))
    merged = sorted(old | read)
    with ledger.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"read": sorted(read)}, ensure_ascii=False) + "\n")
    print("ledger total read:", len(merged))


def cmd_coverage(args):
    work = Path(args.work)
    norm = json.loads((work / "case_norm.json").read_text(encoding="utf-8"))
    ledger = work / "reading_ledger.jsonl"
    read = set()
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if line.strip():
                read |= set(json.loads(line).get("read", []))
    all_ids = {p["paragraph_id"] for p in norm["paragraphs"]}
    unknown = sorted(read - all_ids)
    if unknown:
        print(f"WARN: 留痕中出现清单外的段落编号 {unknown}", file=sys.stderr)
    unread = sorted(all_ids - read)
    coverage = {"read_sections": sorted(read & all_ids),
                "unread_sections": [{"section": u, "reason": args.reason} for u in unread]}
    (work / "coverage.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(coverage, ensure_ascii=False))


def cmd_check(args):
    norm = json.loads(Path(args.case_norm).read_text(encoding="utf-8"))
    result = json.loads(Path(args.result).read_text(encoding="utf-8"))
    errors, warns = [], []
    qids = {q["question_id"] for q in norm["questions"]}
    got = [a.get("question_id") for a in result.get("answers", [])]
    if set(got) != qids:
        errors.append(f"问题覆盖不一致：缺少 {sorted(qids - set(got))}，多出 {sorted(set(got) - qids)}")
    for a in result.get("answers", []):
        qid = a.get("question_id", "?")
        if a.get("status") not in STATUS_ENUM:
            errors.append(f"{qid}: status 非法：{a.get('status')}")
        if not str(a.get("answer", "")).strip():
            errors.append(f"{qid}: answer 为空")
        seen_claim = set()
        for c in a.get("claims", []):
            cid = c.get("claim_id", "?")
            if cid in seen_claim:
                errors.append(f"{qid}: claim_id 重复 {cid}")
            seen_claim.add(cid)
            if c.get("kind") not in KIND_ENUM:
                errors.append(f"{qid}/{cid}: kind 非法：{c.get('kind')}")
            for ev in c.get("evidence", []):
                pid, quote = ev.get("paragraph_id"), ev.get("quote", "")
                para = next((p for p in norm["paragraphs"] if p["paragraph_id"] == pid), None)
                if para is None:
                    errors.append(f"{qid}/{cid}: 证据段落 {pid} 不在清单中")
                elif not quote_found(quote, para["text"]):
                    errors.append(f"{qid}/{cid}: 引文逐字校验失败（{pid}）: {quote[:60]!r}")
                if len(str(quote).split()) > 60:
                    warns.append(f"{qid}/{cid}: 引文过长（>60 词），建议截短")
        if a.get("status") == "answered" and a.get("unanswered_parts"):
            errors.append(f"{qid}: status=answered 但 unanswered_parts 非空")
    for line in errors:
        print("ERROR:", line)
    for line in warns:
        print("WARN:", line)
    print(f"check done: {len(errors)} error(s), {len(warns)} warn(s)")
    return 1 if errors else 0


def atomic_write(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("audit"); p.add_argument("--case", required=True)
    p.add_argument("--work", required=True); p.add_argument("--out")
    p = sub.add_parser("mark"); p.add_argument("--work", required=True)
    p.add_argument("--read", required=True)
    p = sub.add_parser("coverage"); p.add_argument("--work", required=True)
    p.add_argument("--reason", default="未被读取（经问题相关性判断后跳过）")
    p = sub.add_parser("check"); p.add_argument("--case-norm", required=True)
    p.add_argument("--result", required=True)
    args = ap.parse_args()
    sys.exit({"audit": cmd_audit, "mark": cmd_mark,
              "coverage": cmd_coverage, "check": cmd_check}[args.cmd](args))


if __name__ == "__main__":
    main()
