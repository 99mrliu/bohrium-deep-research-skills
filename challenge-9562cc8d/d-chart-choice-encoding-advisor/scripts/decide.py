#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""decide.py — 图表选型与编码决策引擎（图表选型方向）。

读取 statistics.json（数据画像）与 task.md（分析目的），为任务要求的每个
交付图件产出一条可机读的决策：选定图型、编码映射（位置/长度/颜色/分面）、
选择理由、明确否决的备选图型及否决理由、约束核查记录。
决策文件 chart_decisions.json 是图件渲染的唯一依据（run_case.py 遵循执行）。

用法：
    python3 decide.py --stats /app/output/statistics.json \
        --task /input/task.md --out /app/output/chart_decisions.json
"""
import argparse
import json
import os
import re
import sys


def decide(stats, task_text):
    n = stats["n_rows"]
    n_num = len(stats["numeric_columns"])
    grp = stats.get("group", {})
    gmode = grp.get("mode", "none")
    n_levels = len(grp.get("levels") or [])
    desc = stats.get("descriptive", {})
    decisions = {"data_profile": {
        "n_rows": n, "n_numeric": n_num,
        "n_categorical": len(stats.get("categorical_columns", [])),
        "group": grp},
        "global_constraints": [], "figures": [], "advisories": []}

    # ---- global constraint checks -------------------------------------
    decisions["global_constraints"].append({
        "constraint": "no_pie_for_unordered_categories",
        "status": "enforced",
        "detail": "类别为无序分类时禁止饼图/环图表达构成（角度与面积编码会"
                  "夸大差异且不可比）；构成分布改用条形图（零基线）。"})
    decisions["global_constraints"].append({
        "constraint": "zero_baseline_for_bars",
        "status": "enforced",
        "detail": "所有条形/柱状编码（长度编码）一律零基线，禁止截断纵轴。"})
    decisions["global_constraints"].append({
        "constraint": "colorblind_safe_palette",
        "status": "enforced",
        "detail": "Okabe-Ito 调色板；灰度打印下叠加位置/形状冗余编码。"})
    if n_levels > 12:
        decisions["advisories"].append(
            "分组水平数 %d > 12：单图硬塞不可读，建议分面或合并尾部水平为 "
            "'其他' 并在图注注明。" % n_levels)

    # ---- log-scale decisions (per numeric variable) --------------------
    log_vars = []
    for c, st in desc.items():
        if st.get("skewness") is not None and st["skewness"] > 1.0 \
                and st.get("min") is not None and st["min"] > 0:
            log_vars.append({"column": c, "skewness": round(st["skewness"], 3),
                             "decision": "log_axis",
                             "reason": "右偏（偏度>1）且取值为正：对数轴避免少数"
                                       "大值压缩其余观测的可读区间；轴上明确"
                                       "标注“对数尺度”。"})
        elif st.get("skewness") is not None and st["skewness"] > 1.0:
            decisions["advisories"].append(
                "%s 右偏（偏度=%.2f）但含非正值，不能直接用对数轴；保持线性轴。"
                % (c, st["skewness"]))
    decisions["log_scale_decisions"] = log_vars

    # ---- fig1: distributions -------------------------------------------
    decisions["figures"].append({
        "id": "fig1_distributions",
        "purpose": "分布（连续变量，单变量）",
        "chosen": "histogram + gaussian KDE overlay（多面板网格）",
        "encoding": {"x": "变量取值（右偏正值变量为对数轴）", "y": "频数",
                     "curve": "KDE 密度（副轴）", "facet": "每变量一面板"},
        "rationale": "直方图直接展示频数分布与偏态；KDE 辅助判断峰态；"
                     "面板化避免多变量叠印。",
        "rejected": [
            {"chart": "饼图", "reason": "连续变量无构成语义；角度编码不可比。"},
            {"chart": "均值条形图", "reason": "只显示点估计，掩盖分布形态与"
                                              "异常值。"},
            {"chart": "茎叶图", "reason": "n=%d 超出其可读范围。" % n}],
        "panel_rule": "3 列网格；面板字母 (a)(b)…；面板内标注偏度。"})

    # ---- fig2: grouped comparison --------------------------------------
    if gmode == "categorical":
        rej = [{"chart": "仅均值±误差条形图（dynamite plot）",
                "reason": "隐藏分布与样本量；误差线含义常被误读。"},
               {"chart": "小提琴图", "reason": "组内 n 较小（<20）时密度估计不"
                                               "稳定；本数据各组 n 见分组统计。"},
               {"chart": "并列柱状图（时间序列式）",
                "reason": "分组为无序类别，非有序时间轴。"}]
        decisions["figures"].append({
            "id": "fig2_grouped_boxplots",
            "purpose": "分组比较（连续变量 × 无序分类 %s）" % grp.get("column"),
            "chosen": "分组箱线图 + 抖动散点叠加（panel 按组间 F 统计量排序，"
                      "至多 8 个）",
            "encoding": {"x": "组（位置）", "y": "变量取值（位置）",
                         "color": "组（Okabe-Ito，与散点图例一致）",
                         "box": "Q1–Q3", "whisker": "1.5×IQR"},
            "rationale": "箱线图给出五数概括，散点叠加揭示样本量与离群点；"
                         "按组间区分度（F 统计量）排序，把最有区分度的变量"
                         "放在前面。",
            "rejected": rej,
            "panel_rule": "F 统计量降序取前 8；须线=1.5×IQR；离群点仅标记。"})
    else:
        decisions["figures"].append({
            "id": "fig2_grouped_boxplots",
            "purpose": "目标变量分组比较（无现成分组列）",
            "chosen": "按 %s 四分位分箱后的箱线图 + 抖动散点" % grp.get("column"),
            "encoding": {"x": "分箱（有序类别，位置）", "y": "目标变量取值",
                         "box": "Q1–Q3", "whisker": "1.5×IQR"},
            "rationale": "无分类变量时以偏斜连续协变量等频分箱构造有序分组，"
                         "观察目标变量条件分布的迁移；分箱边界写入图注。",
            "rejected": [
                {"chart": "对连续协变量直接做并列条形图",
                 "reason": "连续轴无类别语义，条形长度会造成虚假比较。"}],
            "panel_rule": "目标变量 + 与目标 |r| 最高的 3 个协变量。"})

    # ---- fig3: pairwise relations --------------------------------------
    decisions["figures"].append({
        "id": "fig3_scatter_pairs",
        "purpose": "相关（双变量）",
        "chosen": "两两散点图（按 |r| 最大选取 + 任务点名变量对，分组着色）",
        "encoding": {"x": "变量 1（位置）", "y": "变量 2（位置）",
                     "color": "分组（Okabe-Ito）",
                     "annotation": "Pearson r 与 n"},
        "rationale": "位置编码是最准确的定量通道；着色分组可识别辛普森悖论"
                     "式结构；r 与 n 直接标注在面板标题。",
        "rejected": [
            {"chart": "气泡图（面积编码第三变量）",
             "reason": "面积感知非线性，夸大差异；第三变量改走分面或着色。"},
            {"chart": "3D 散点图", "reason": "透视造成位置判读失真。"},
            {"chart": "双 y 轴组合图",
             "reason": "双轴的相对尺度可任意调节，易误导；量纲不同变量"
                       "分列展示。"}],
        "panel_rule": "|r| 降序前 3 + 任务点名对；n>300 固定种子抽样。"})

    # ---- fig4: correlation structure -----------------------------------
    decisions["figures"].append({
        "id": "fig4_correlation_heatmap",
        "purpose": "相关结构（多变量）",
        "chosen": "Pearson 相关热图（格内标注系数，色标固定 [-1, 1]，"
                  "发散色 RdBu_r）",
        "encoding": {"cell": "|r|（饱和度的长度语义）", "hue": "符号（红正蓝负）",
                     "text": "r 值（精确补偿颜色感知误差）"},
        "rationale": "固定对称色标防止跨图比较失真；格内数字补偿颜色通道的"
                     "低精度；成对完整观测口径写入图注。",
        "rejected": [
            {"chart": "未固定色标的聚类热图",
             "reason": "色标随数据范围漂移，跨图不可比。"},
            {"chart": "相关网络图", "reason": "边粗细编码 |r| 精度低，节点布局"
                                              "引入无信息维度。"}],
        "panel_rule": "单面板；变量数 > 14 时仅展示 |r| 最高的 14 个并记录。"})

    if stats.get("frequency_tables"):
        decisions["advisories"].append(
            "分类变量频数已在 statistics.json 给出；如需构成图，使用零基线条形"
            "图而非饼图（global constraint）。")
    return decisions


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stats", required=True)
    ap.add_argument("--task", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    with open(args.stats, encoding="utf-8") as fh:
        stats = json.load(fh)
    task_text = ""
    if args.task and os.path.isfile(args.task):
        with open(args.task, encoding="utf-8") as fh:
            task_text = fh.read()
    decisions = decide(stats, task_text)
    decisions["decision_engine"] = "decide.py (chart-choice-encoding-advisor)"
    decisions["task_excerpt"] = task_text[:200]
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(decisions, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"figures": len(decisions["figures"]),
                      "log_scale": [d["column"]
                                    for d in decisions["log_scale_decisions"]],
                      "advisories": len(decisions["advisories"])},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
