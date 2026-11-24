#!/usr/bin/env python3
"""appraise.py —— 签名引擎：逐维度判定核验 + 确定性评分定级。

判定行（appraisals.jsonl）：
  {record_id, dim_id, level_id,
   basis_location("文件名:行号区间或段落号"，如 "S1.txt:L4" / "S1.txt:L4-L6" / "S1.txt:P2"),
   basis_quote}

规则：
  A1 完整性：--included 清单中每研究 × 每维度都必须有判定；
  A2 依据可核：basis_quote 必须是 basis_location 所指源文本的 verbatim 子串
     （规范化空白后比对；找不到则给出最接近候选位置提示）；
  A3 level_id 必须属于该维度。

评分：每研究加权总分 = Σ weight × (level.score / 该维度满分)，
按 grade_rules 映射风险等级；输出 appraisal_report.json。

退出码：0=通过；2=sources 目录缺失或某研究无源文件（诚实降级）；
3=A1–A3 违规或输入非法。
"""
import argparse
import difflib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rubric_check import validate_rubric  # noqa: E402

TOL = 1e-6


def norm_ws(s):
    """规范化空白：所有连续空白折叠为单个空格。"""
    return " ".join(s.split())


def locate_text(lines, paragraphs, locator):
    """按 L<a> / L<a>-L<b> / P<n> 取定位文本；非法返回 None。"""
    loc = locator.strip()
    if loc.upper().startswith("L"):
        body = loc[1:]
        try:
            if "-" in body:
                a, b = body.split("-", 1)
                a, b = int(a.lstrip("Ll")), int(b.lstrip("Ll"))
            else:
                a = b = int(body)
        except ValueError:
            return None
        if a < 1 or b > len(lines) or a > b:
            return None
        return "\n".join(lines[a - 1:b])
    if loc.upper().startswith("P"):
        try:
            n = int(loc[1:])
        except ValueError:
            return None
        if n < 1 or n > len(paragraphs):
            return None
        return paragraphs[n - 1]
    return None


def closest_hint(lines, quote):
    """在全文各行中找与 quote 最接近的一行，返回提示字符串。"""
    nq = norm_ws(quote)
    best_ratio, best_idx = 0.0, -1
    for i, ln in enumerate(lines, 1):
        r = difflib.SequenceMatcher(None, nq, norm_ws(ln)).ratio()
        if r > best_ratio:
            best_ratio, best_idx = r, i
    if best_idx > 0:
        return (f"最接近候选：第 {best_idx} 行（相似度 {best_ratio:.2f}）："
                f"{lines[best_idx - 1].strip()[:80]}")
    return "全文为空，无可比对文本。"


def grade_of(total, grade_rules):
    """按 [min, max) 区间映射等级，最顶层区间右端点闭合。"""
    rules = sorted(grade_rules, key=lambda r: r["min_score"])
    for i, r in enumerate(rules):
        upper_closed = (i == len(rules) - 1)
        if r["min_score"] - TOL <= total < r["max_score"] - TOL:
            return r["grade"]
        if upper_closed and abs(total - r["max_score"]) <= TOL:
            return r["grade"]
    return rules[-1]["grade"]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rubric", required=True, help="量表 rubric.json 路径")
    ap.add_argument("--appraisals", required=True, help="判定 appraisals.jsonl 路径")
    ap.add_argument("--sources", required=True, help="源文本目录（每纳入研究一个 .txt）")
    ap.add_argument("--included", required=True, help="纳入研究 id 清单 included.json")
    ap.add_argument("--out", required=True, help="输出 appraisal_report.json 路径")
    args = ap.parse_args()

    # ---- 读入 rubric 并复用校验 ----
    for p, tag in ((args.rubric, "rubric"), (args.appraisals, "appraisals"),
                   (args.included, "included")):
        if not os.path.isfile(p):
            print(f"[E2] 输入缺失：{tag} 文件不存在：{p}", file=sys.stderr)
            return 2
    try:
        with open(args.rubric, "r", encoding="utf-8") as f:
            rubric = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"[E3] rubric JSON 解析失败：{e}", file=sys.stderr)
        return 3
    rubric_violations = validate_rubric(rubric)
    if rubric_violations:
        print(f"[E3] rubric 未通过校验（共 {len(rubric_violations)} 处）：",
              file=sys.stderr)
        for code, msg in rubric_violations:
            print(f"  [{code}] {msg}", file=sys.stderr)
        return 3

    try:
        with open(args.included, "r", encoding="utf-8") as f:
            inc = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"[E3] included JSON 解析失败：{e}", file=sys.stderr)
        return 3
    included = inc.get("included") if isinstance(inc, dict) else inc
    if not isinstance(included, list) or not included:
        print("[E3] included 必须是非空数组或含 included 数组的对象。", file=sys.stderr)
        return 3

    # ---- sources 目录（诚实降级 exit 2）----
    if not os.path.isdir(args.sources):
        print(f"[E2] 诚实降级：sources 目录缺失：{args.sources}。"
              "仅可交付 rubric 与结构，无法进行依据可核评价。", file=sys.stderr)
        return 2

    source_cache = {}
    for rid in included:
        path = os.path.join(args.sources, f"{rid}.txt")
        if not os.path.isfile(path):
            print(f"[E2] 诚实降级：研究 {rid} 无源文件：{path}。"
                  "该研究只能做题录级线索评价。", file=sys.stderr)
            return 2
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        lines = text.splitlines()
        paragraphs = [p for p in
                      ("\n".join(blk) for blk in
                       _split_blocks(lines))]
        source_cache[rid] = (lines, paragraphs)

    # ---- 读入判定 ----
    judgments = {}
    errors = []
    with open(args.appraisals, "r", encoding="utf-8") as f:
        for ln, raw in enumerate(f, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                j = json.loads(raw)
            except json.JSONDecodeError as e:
                errors.append(("E3", f"第 {ln} 行 JSON 解析失败：{e}"))
                continue
            rid, dim = j.get("record_id"), j.get("dim_id")
            if not rid or not dim:
                errors.append(("E3", f"第 {ln} 行缺 record_id 或 dim_id。"))
                continue
            if "basis_quote" not in j or not j.get("basis_quote"):
                errors.append(("A2", f"第 {ln} 行（{rid}/{dim}）缺 basis_quote，"
                                     "逐维度判定必须带 verbatim 原文依据。"))
                continue
            if not j.get("basis_location"):
                errors.append(("A2", f"第 {ln} 行（{rid}/{dim}）缺 basis_location。"))
                continue
            judgments.setdefault(rid, {})[dim] = j

    dim_map = {d["dim_id"]: d for d in rubric["dimensions"]}

    # A1 完整性
    for rid in included:
        for dim_id in dim_map:
            if rid not in judgments or dim_id not in judgments[rid]:
                errors.append(("A1", f"研究 {rid} 缺维度 {dim_id} 的判定。"))

    # A3 level_id 属于该维度
    for rid, per_dim in judgments.items():
        for dim_id, j in per_dim.items():
            if dim_id not in dim_map:
                errors.append(("A3", f"研究 {rid} 判定了 rubric 中不存在的维度：{dim_id}。"))
                continue
            valid = {lv["level_id"] for lv in dim_map[dim_id]["levels"]}
            if j.get("level_id") not in valid:
                errors.append(("A3", f"研究 {rid}/{dim_id} 的 level_id "
                                     f"{j.get('level_id')!r} 不属于该维度 {sorted(valid)}。"))

    if errors:
        print(f"[校验失败] 共 {len(errors)} 处违规：", file=sys.stderr)
        for code, msg in errors:
            print(f"  [{code}] {msg}", file=sys.stderr)
        return 3

    # A2 依据可核（需全部判定齐备后核验）
    for rid in included:
        lines, paragraphs = source_cache[rid]
        for dim_id in dim_map:
            j = judgments[rid][dim_id]
            loc_raw = j["basis_location"]
            if ":" not in loc_raw:
                errors.append(("A2", f"{rid}/{dim_id} basis_location 格式须为 "
                                     f"'文件名:行号区间或段落号'：{loc_raw!r}"))
                continue
            fname, locator = loc_raw.rsplit(":", 1)
            if fname != f"{rid}.txt":
                errors.append(("A2", f"{rid}/{dim_id} basis_location 指向文件 "
                                     f"{fname!r}，与研究 {rid} 的源文件不符。"))
                continue
            located = locate_text(lines, paragraphs, locator)
            if located is None:
                errors.append(("A2", f"{rid}/{dim_id} basis_location 无法解析或"
                                     f"越界：{loc_raw!r}"))
                continue
            if norm_ws(j["basis_quote"]) not in norm_ws(located):
                hint = closest_hint(lines, j["basis_quote"])
                errors.append(("A2", f"{rid}/{dim_id} basis_quote 不是 "
                                     f"{loc_raw} 所指文本的 verbatim 子串。{hint}"))

    if errors:
        print(f"[校验失败] 共 {len(errors)} 处违规：", file=sys.stderr)
        for code, msg in errors:
            print(f"  [{code}] {msg}", file=sys.stderr)
        return 3

    # ---- 确定性评分定级 ----
    studies = []
    for rid in included:
        scores_per_dim = {}
        basis_map = {}
        total = 0.0
        for dim_id, d in dim_map.items():
            j = judgments[rid][dim_id]
            full = max(lv["score"] for lv in d["levels"])
            lv = next(l for l in d["levels"] if l["level_id"] == j["level_id"])
            normalized = lv["score"] / full if full > 0 else 0.0
            scores_per_dim[dim_id] = {
                "level_id": lv["level_id"], "score": lv["score"],
                "full_score": full, "normalized": round(normalized, 6),
                "weight": d["weight"],
            }
            basis_map[dim_id] = {
                "basis_location": j["basis_location"],
                "basis_quote": j["basis_quote"],
            }
            total += d["weight"] * normalized
        total = round(total, 6)
        studies.append({
            "record_id": rid,
            "scores_per_dim": scores_per_dim,
            "total": total,
            "grade": grade_of(total, rubric["grade_rules"]),
            "basis_map": basis_map,
        })

    report = {
        "scale_id": rubric["scale_id"],
        "scale_version": rubric["version"],
        "grade_rules": rubric["grade_rules"],
        "scoring_rule": "total = Σ weight × (level.score / 该维度满分)",
        "studies": studies,
        "counts": {"included": len(included),
                   "dimensions": len(dim_map),
                   "judgments": sum(len(v) for v in judgments.values())},
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[OK] 评价报告已生成：{args.out}")
    for s in studies:
        print(f"  {s['record_id']}: total={s['total']:.3f} grade={s['grade']}")
    return 0


def _split_blocks(lines):
    """按空行切段，产出段落列表。"""
    block = []
    for ln in lines:
        if ln.strip():
            block.append(ln)
        elif block:
            yield block
            block = []
    if block:
        yield block


if __name__ == "__main__":
    sys.exit(main())
