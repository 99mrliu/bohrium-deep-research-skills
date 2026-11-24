#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""conflict_adjudicate.py — 冲突检出 / 裁定校验 / 证据分级一致性 / 综合文本审计。

C1 自动检出冲突对（同 outcome_domain 且 direction 一方 positive 一方 negative），
   写出 conflict_registry.json（每对含双方 study_id 与关键字段并置）。
C2 校验 Agent 回填的 adjudication：每冲突对必须有
   {design_comparison, n_comparison, consistency_note, verdict}，
   verdict ∈ {favor_a, favor_b, coexist_by_context, undecidable}，
   前三项至少两项非空；verdict=undecidable 时 consistency_note 必须说明
   为何无法裁定（禁止裸“尚存争议”一类短语）。
C3 证据分级一致性：conclusions 每条含 {statement, grade∈A-D, evidence[]}；
   grade A/B 要求 evidence 中 ≥2 个一致方向且 design∈{rct,meta_analysis,cohort}
   的研究；涉及未裁定冲突对的 conclusion 不得高于 C。
C4 综合文本审计：synthesis.md 按句切分（中文句号/分号/换行），每句必须以
   [事实]/[推断]/[无法确定] 之一结尾（标题行与空行豁免）；[事实] 句必须含
   ≥1 个存在于矩阵的 study_id（模式 S-数字）。

退出码：0 通过；1 门控违例（stdout 逐项打印 C 编号与位置）；2 用法/IO 错误。
仅使用 Python 标准库；产物 JSON 使用 ensure_ascii=False, indent=2，不含随机数/时间戳。
"""
import argparse
import json
import re
import sys
from collections import Counter

TIER_DESIGNS = {"rct", "meta_analysis", "cohort"}
VERDICTS = {"favor_a", "favor_b", "coexist_by_context", "undecidable"}
GRADES = {"A", "B", "C", "D"}
COUNTED_DIRECTIONS = {"positive", "negative", "null"}
CORE_KEYS = ("study_id", "design", "n", "population", "intervention",
             "outcome_domain", "direction", "magnitude", "limits", "source")
ADJ_FIELDS = ("design_comparison", "n_comparison", "consistency_note")
LABEL_RE = re.compile(r"\[(事实|推断|无法确定)\]")
STUDY_ID_RE = re.compile(r"S-\d+")
BARE_NOTES = {"尚存争议", "存在争议", "尚有争议", "仍有争议", "有争议", "争议",
              "无定论", "尚无定论", "未有定论", "结论不一", "不确定", "尚不确定",
              "无法确定", "难以确定", "未知", "待研究", "有待研究",
              "undecidable", "unclear", "unknown", "tbd", "n/a"}
MIN_UNDECIDABLE_NOTE = 20
STRIP_CHARS = "。．.；;，,、:： \t\r\n"


def usage_error(msg):
    print(f"用法/IO 错误: {msg}", file=sys.stderr)
    return 2


def load_matrix(path):
    """读取 JSONL 矩阵；结构不合规时返回错误字符串（提示先过 matrix_check）。"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw_lines = fh.read().splitlines()
    except OSError as exc:
        return None, f"无法读取矩阵 {path}: {exc}"
    studies = []
    for lineno, raw in enumerate(raw_lines, start=1):
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            return None, f"矩阵行{lineno} 非合法 JSON；请先运行 matrix_check.py"
        if not isinstance(rec, dict) or any(k not in rec for k in CORE_KEYS):
            return None, f"矩阵行{lineno} 缺少核心字段；请先运行 matrix_check.py"
        studies.append(rec)
    if not studies:
        return None, "矩阵为空"
    return studies, None


def detect_conflicts(studies):
    """C1: 同 outcome_domain 内 positive × negative 的全部配对，确定性排序。"""
    by_domain = {}
    for s in studies:
        by_domain.setdefault(s["outcome_domain"], []).append(s)
    conflicts = []
    for domain in sorted(by_domain):
        group = sorted(by_domain[domain], key=lambda s: s["study_id"])
        pos = [s for s in group if s["direction"] == "positive"]
        neg = [s for s in group if s["direction"] == "negative"]
        for a in pos:
            for b in neg:
                conflicts.append({
                    "conflict_id": f"C-{len(conflicts) + 1}",
                    "outcome_domain": domain,
                    "study_a": a,
                    "study_b": b,
                    "adjudication_required": True,
                })
    return conflicts


def load_json_file(path, what):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh), None
    except OSError as exc:
        return None, f"无法读取{what} {path}: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"{what} {path} 非合法 JSON: {exc}"


def normalize_adjudications(obj):
    """接受 {conflict_id: adjudication} 或 [{conflict_id, ...}] 两种形态。"""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.startswith("_"):
                continue
            out[k] = v
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict) and "conflict_id" in item:
                cid = item["conflict_id"]
                if isinstance(item.get("adjudication"), dict):
                    out[cid] = item["adjudication"]
                else:
                    out[cid] = {k: item[k] for k in ADJ_FIELDS + ("verdict",)
                                if k in item}
    return out


def check_adjudications(conflicts, adj_map):
    """C2: 裁定完整性校验。"""
    viol = []
    known_ids = {c["conflict_id"] for c in conflicts}
    for c in conflicts:
        cid = c["conflict_id"]
        pair = f"{c['study_a']['study_id']} vs {c['study_b']['study_id']}"
        adj = adj_map.get(cid)
        if adj is None:
            viol.append(f"C2 {cid}（{pair}）: 缺少 adjudication 条目")
            continue
        if not isinstance(adj, dict):
            viol.append(f"C2 {cid}（{pair}）: adjudication 必须为对象")
            continue
        missing = [k for k in ADJ_FIELDS + ("verdict",) if k not in adj]
        if missing:
            viol.append(f"C2 {cid}（{pair}）: 缺少字段 {missing}")
        verdict = adj.get("verdict")
        if "verdict" in adj and verdict not in VERDICTS:
            viol.append(f"C2 {cid}（{pair}）: verdict={verdict!r} 不在 {sorted(VERDICTS)}")
        filled = 0
        for k in ADJ_FIELDS:
            v = adj.get(k)
            if isinstance(v, str) and v.strip():
                filled += 1
            elif v is not None and not isinstance(v, str):
                viol.append(f"C2 {cid}（{pair}）: {k} 必须为字符串")
        if filled < 2:
            viol.append(
                f"C2 {cid}（{pair}）: design_comparison / n_comparison / "
                f"consistency_note 至少两项非空（当前 {filled} 项）")
        if verdict == "undecidable":
            note = adj.get("consistency_note")
            note_s = note.strip() if isinstance(note, str) else ""
            norm = note_s.strip(STRIP_CHARS).lower()
            if note_s and norm in BARE_NOTES:
                viol.append(
                    f"C2 {cid}（{pair}）: verdict=undecidable 时 consistency_note "
                    f"不得为裸短语（如“尚存争议”），必须说明为何无法裁定")
            elif len(note_s) < MIN_UNDECIDABLE_NOTE:
                viol.append(
                    f"C2 {cid}（{pair}）: verdict=undecidable 时 consistency_note "
                    f"须 ≥{MIN_UNDECIDABLE_NOTE} 字并具体说明无法裁定的原因"
                    f"（当前 {len(note_s)} 字）")
    for cid in sorted(set(adj_map) - known_ids):
        viol.append(f"C2 {cid}: adjudications 含登记表中不存在的 conflict_id")
    return viol


def unresolved_study_ids(conflicts, adj_map):
    """未裁定 = 无条目 / verdict 非法 / verdict=undecidable。"""
    unresolved = set()
    for c in conflicts:
        adj = adj_map.get(c["conflict_id"])
        v = adj.get("verdict") if isinstance(adj, dict) else None
        if v not in VERDICTS or v == "undecidable":
            unresolved.add(c["study_a"]["study_id"])
            unresolved.add(c["study_b"]["study_id"])
    return unresolved


def check_conclusions(obj, id2study, conflicts, adj_map):
    """C3: 证据分级一致性校验。"""
    viol = []
    concl = obj.get("conclusions") if isinstance(obj, dict) else obj
    if not isinstance(concl, list):
        return ["C3: conclusions 必须为列表（或含 conclusions 键的对象）"]
    unresolved = unresolved_study_ids(conflicts, adj_map)
    for i, item in enumerate(concl, start=1):
        tag = f"C3 结论#{i}"
        if not isinstance(item, dict):
            viol.append(f"{tag}: 必须为对象 {{statement, grade, evidence}}")
            continue
        stmt = item.get("statement")
        grade = item.get("grade")
        ev = item.get("evidence")
        if not isinstance(stmt, str) or not stmt.strip():
            viol.append(f"{tag}: statement 缺失或为空")
        if grade not in GRADES:
            viol.append(f"{tag}: grade={grade!r} 不在 A-D")
            continue
        if not isinstance(ev, list) or not ev:
            viol.append(f"{tag}: evidence 必须为非空 study_id 列表")
            continue
        unknown = [e for e in ev if e not in id2study]
        if unknown:
            viol.append(f"{tag}: evidence 含矩阵中不存在的 study_id {unknown}")
            continue
        if grade in ("A", "B"):
            cnt = Counter(
                id2study[e]["direction"] for e in ev
                if id2study[e]["design"] in TIER_DESIGNS
                and id2study[e]["direction"] in COUNTED_DIRECTIONS)
            best = max(cnt.values()) if cnt else 0
            if best < 2:
                viol.append(
                    f"{tag}: grade={grade} 要求 evidence 中 ≥2 个一致方向且 "
                    f"design∈{{rct,meta_analysis,cohort}} 的研究"
                    f"（当前一致方向最大计数 {best}）")
        hit = sorted(set(ev) & unresolved)
        if hit and grade in ("A", "B"):
            viol.append(
                f"{tag}: 涉及未裁定冲突对研究 {hit}，grade 不得高于 C（当前 {grade}）")
    return viol


def check_synthesis(text, id2study):
    """C4: 句级标签审计。按行处理，行内按标签切句。"""
    viol = []
    sent_no = 0
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        matches = list(LABEL_RE.finditer(line))
        if not matches:
            sent_no += 1
            viol.append(
                f"C4 行{lineno} 句{sent_no}: 缺少句级标签 "
                f"[事实]/[推断]/[无法确定]（句首: {line[:40]}）")
            continue
        prev_end = 0
        for m in matches:
            chunk = line[prev_end:m.start()]
            sent_no += 1
            core = chunk.strip(STRIP_CHARS)
            label = m.group(1)
            if not core:
                viol.append(f"C4 行{lineno} 句{sent_no}: 标签 [{label}] 前无实质句内容")
            elif label == "事实":
                ids = STUDY_ID_RE.findall(chunk)
                known = [i for i in ids if i in id2study]
                if not known:
                    viol.append(
                        f"C4 行{lineno} 句{sent_no}: [事实] 句必须引用 ≥1 个矩阵内"
                        f"存在的 study_id（检出 {ids if ids else '无'}）")
            prev_end = m.end()
        tail = line[prev_end:].strip(STRIP_CHARS)
        if tail:
            sent_no += 1
            viol.append(
                f"C4 行{lineno} 句{sent_no}: 末个标签之后存在未标注文本: {tail[:40]}")
    return viol


def main():
    ap = argparse.ArgumentParser(
        description="冲突检出（C1）+ 裁定校验（C2）+ 分级一致性（C3）+ 文本审计（C4）")
    ap.add_argument("--matrix", required=True, help="study_matrix.jsonl 路径")
    ap.add_argument("--registry", default="conflict_registry.json",
                    help="C1 输出的 conflict_registry.json 路径")
    ap.add_argument("--adjudications", help="Agent 回填的 adjudications.json（启用 C2）")
    ap.add_argument("--conclusions", help="conclusions.json（启用 C3）")
    ap.add_argument("--synthesis", help="synthesis.md（启用 C4）")
    args = ap.parse_args()

    studies, err = load_matrix(args.matrix)
    if err:
        return usage_error(err)
    id2study = {s["study_id"]: s for s in studies}

    # C1 冲突检出并写登记表（无论后续校验是否通过，产物均落盘）
    conflicts = detect_conflicts(studies)
    registry = {
        "matrix": args.matrix,
        "n_studies": len(studies),
        "n_conflicts": len(conflicts),
        "conflicts": conflicts,
    }
    try:
        with open(args.registry, "w", encoding="utf-8") as fh:
            json.dump(registry, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except OSError as exc:
        return usage_error(f"无法写出登记表 {args.registry}: {exc}")
    print(f"C1 冲突检出: {len(conflicts)} 个冲突对 -> {args.registry}")

    violations = []
    adj_map = {}
    if args.adjudications:
        adj_obj, err = load_json_file(args.adjudications, "adjudications")
        if err:
            return usage_error(err)
        if not isinstance(adj_obj, (dict, list)):
            return usage_error("adjudications 必须为对象或列表")
        adj_map = normalize_adjudications(adj_obj)
        violations += check_adjudications(conflicts, adj_map)
    elif args.conclusions:
        print("提示: 未提供 --adjudications，所有冲突对在 C3 中按未裁定处理")

    if args.conclusions:
        concl_obj, err = load_json_file(args.conclusions, "conclusions")
        if err:
            return usage_error(err)
        violations += check_conclusions(concl_obj, id2study, conflicts, adj_map)

    if args.synthesis:
        try:
            with open(args.synthesis, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            return usage_error(f"无法读取 synthesis {args.synthesis}: {exc}")
        violations += check_synthesis(text, id2study)

    if violations:
        print(f"conflict_adjudicate 未通过: {len(violations)} 项违例")
        for v in violations:
            print("  " + v)
        return 1
    print("conflict_adjudicate 通过: C1-C4 已执行项全部满足")
    return 0


if __name__ == "__main__":
    sys.exit(main())
