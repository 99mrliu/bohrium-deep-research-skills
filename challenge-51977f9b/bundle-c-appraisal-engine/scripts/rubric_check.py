#!/usr/bin/env python3
"""rubric_check.py —— 校验声明式质量评价量表（rubric.json）。

量表 schema：
{scale_id, version,
 dimensions: [{dim_id, name,
               levels: [{level_id, score(数值), definition(≥10字符)}],
               weight}],
 grade_rules: [{grade, min_score, max_score, implication}]}

规则：
  R1 全部维度 weight 之和 = 1.0（容差 1e-6）；
  R2 每个 level 的 definition ≥ 10 字符，且 dim 内 level_id 唯一；
  R3 grade_rules 的 [min_score, max_score] 区间无缝覆盖 [0,1] 且不重叠，
     每条必须含 implication（该等级如何影响结论权重）；
  R4 dim_id 全局唯一，且每个 weight > 0。

退出码：0=通过；2=输入不足；3=校验失败（违规逐条列出）。
"""
import argparse
import json
import os
import sys

TOL = 1e-6


def validate_rubric(rubric):
    """返回违规列表，每项形如 (规则码, 描述)；空列表表示通过。"""
    violations = []

    if not isinstance(rubric, dict):
        return [("E0", "rubric 顶层必须是 JSON 对象。")]
    for key in ("scale_id", "version", "dimensions", "grade_rules"):
        if key not in rubric:
            violations.append(("E0", f"缺少必备字段：{key}"))
    if violations:
        return violations

    dims = rubric["dimensions"]
    if not isinstance(dims, list) or not dims:
        violations.append(("E0", "dimensions 必须是非空数组。"))
        return violations

    # R4：dim_id 唯一、weight > 0
    seen_dims = set()
    total_weight = 0.0
    for d in dims:
        dim_id = d.get("dim_id")
        if not dim_id:
            violations.append(("E0", "存在缺 dim_id 的维度。"))
            continue
        if dim_id in seen_dims:
            violations.append(("R4", f"dim_id 重复：{dim_id}"))
        seen_dims.add(dim_id)
        w = d.get("weight")
        if not isinstance(w, (int, float)):
            violations.append(("E0", f"维度 {dim_id} 的 weight 缺失或非数值。"))
        else:
            if w <= 0:
                violations.append(("R4", f"维度 {dim_id} 的 weight 必须 > 0，当前 {w}。"))
            total_weight += w

        # R2：level_id 唯一、definition ≥ 10 字符
        levels = d.get("levels")
        if not isinstance(levels, list) or not levels:
            violations.append(("E0", f"维度 {dim_id} 的 levels 必须是非空数组。"))
            continue
        seen_levels = set()
        for lv in levels:
            lid = lv.get("level_id")
            if not lid:
                violations.append(("E0", f"维度 {dim_id} 存在缺 level_id 的等级。"))
                continue
            if lid in seen_levels:
                violations.append(("R2", f"维度 {dim_id} 内 level_id 重复：{lid}"))
            seen_levels.add(lid)
            if not isinstance(lv.get("score"), (int, float)):
                violations.append(("E0", f"维度 {dim_id}/{lid} 的 score 缺失或非数值。"))
            definition = lv.get("definition", "")
            if len(definition) < 10:
                violations.append(
                    ("R2", f"维度 {dim_id}/{lid} 的 definition 不足 10 字符：{definition!r}"))

    # R1：权重和 = 1.0
    if abs(total_weight - 1.0) > TOL:
        violations.append(("R1", f"权重之和为 {total_weight:.10f}，须等于 1.0（容差 1e-6）。"))

    # R3：grade_rules 无缝覆盖 [0,1] 且不重叠、每条含 implication
    rules = rubric["grade_rules"]
    if not isinstance(rules, list) or not rules:
        violations.append(("E0", "grade_rules 必须是非空数组。"))
    else:
        intervals = []
        for r in rules:
            grade = r.get("grade", "<未命名>")
            mn, mx = r.get("min_score"), r.get("max_score")
            if not isinstance(mn, (int, float)) or not isinstance(mx, (int, float)):
                violations.append(("E0", f"等级 {grade} 缺 min_score/max_score 或非数值。"))
                continue
            if mn >= mx:
                violations.append(("R3", f"等级 {grade} 区间非法：min_score {mn} >= max_score {mx}。"))
            if not r.get("implication"):
                violations.append(("R3", f"等级 {grade} 缺 implication（该等级如何影响结论权重）。"))
            intervals.append((mn, mx, grade))
        intervals.sort()
        if intervals:
            if abs(intervals[0][0] - 0.0) > TOL:
                violations.append(("R3", f"grade_rules 未从 0.0 开始覆盖，最低起点 "
                                         f"{intervals[0][0]}。"))
            for i in range(1, len(intervals)):
                if abs(intervals[i][0] - intervals[i - 1][1]) > TOL:
                    violations.append(
                        ("R3", f"等级 {intervals[i - 1][2]} 与 {intervals[i][2]} 区间"
                               f"不衔接或重叠：{intervals[i - 1][1]} vs {intervals[i][0]}。"))
            if abs(intervals[-1][1] - 1.0) > TOL:
                violations.append(("R3", f"grade_rules 未覆盖到 1.0，最高终点 "
                                         f"{intervals[-1][1]}。"))
    return violations


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rubric", required=True, help="量表 rubric.json 路径")
    args = ap.parse_args()

    if not os.path.isfile(args.rubric):
        print(f"[E2] 输入缺失：rubric 文件不存在：{args.rubric}", file=sys.stderr)
        return 2
    try:
        with open(args.rubric, "r", encoding="utf-8") as f:
            rubric = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"[E3] rubric JSON 解析失败：{e}", file=sys.stderr)
        return 3

    violations = validate_rubric(rubric)
    if violations:
        print(f"[校验失败] rubric 共 {len(violations)} 处违规：", file=sys.stderr)
        for code, msg in violations:
            print(f"  [{code}] {msg}", file=sys.stderr)
        return 3
    print(f"[OK] rubric 校验通过：scale_id={rubric['scale_id']} "
          f"version={rubric['version']}，维度 {len(rubric['dimensions'])} 个，"
          f"等级规则 {len(rubric['grade_rules'])} 条。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
