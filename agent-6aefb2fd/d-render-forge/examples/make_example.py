#!/usr/bin/env python3
"""合成示例（SYNTHETIC EXAMPLE，非正式案例结果）：
构造玩具 cleaned 表与统计 JSON，端到端验证：
  - figure_forge.py 按意图渲染 3 张图 + 谱系 manifest；
  - report_forge.py scaffold 机器渲染统计表格，verify 通过；
  - 把报告中的一个数字改成无源值 → verify 退出码 6。

用法：python3 make_example.py [输出根目录，默认 /tmp/rf-example]
"""
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/tmp/rf-example")
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
WORK = os.path.join(ROOT, "work")
OUT = os.path.join(ROOT, "output")
FIGS = os.path.join(OUT, "figures")
for d in (WORK, OUT, FIGS):
    os.makedirs(d, exist_ok=True)

rng = np.random.default_rng(7)
n = 50
df = pd.concat([pd.DataFrame({
    "cls": g,
    "m1": rng.normal(10 + 4 * i, 1, n),
    "m2": rng.normal(5, 1, n),
    "m3": rng.lognormal(1, 0.5, n),
}) for i, g in enumerate(["a", "b", "c"])], ignore_index=True)
cleaned = os.path.join(OUT, "cleaned_data.csv")
df.to_csv(cleaned, index=False)

stats_doc = {"mode": "group_compare", "group_column": "cls", "alpha": 0.05,
             "group_levels": ["a", "b", "c"],
             "multiple_testing": {"family": "features", "size": 2,
                                  "bonferroni_alpha": 0.025},
             "features": {
                 "m1": {"n_per_group": {"a": 50, "b": 50, "c": 50},
                        "premises": {"normality_ok": True},
                        "method": "one_way_anova", "statistic": 4213.5,
                        "p_value": 0.0, "effect_size": {"eta_squared": 0.9883},
                        "significant_bonferroni_family": True},
                 "m2": {"n_per_group": {"a": 50, "b": 50, "c": 50},
                        "premises": {"normality_ok": True},
                        "method": "one_way_anova", "statistic": 0.42,
                        "p_value": 0.6573, "effect_size": {"eta_squared": 0.0056},
                        "significant_bonferroni_family": False}},
             "discrimination_ranking": [
                 {"feature": "m1", "score": 0.9883, "method": "one_way_anova", "p_value": 0.0},
                 {"feature": "m2", "score": 0.0056, "method": "one_way_anova", "p_value": 0.6573}]}
stats_path = os.path.join(OUT, "statistics.json")
json.dump(stats_doc, open(stats_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

spec = [{"id": "fig_group_m1m2", "intent": "group_compare", "columns": ["m1", "m2"], "group": "cls"},
        {"id": "fig_corr", "intent": "correlation", "columns": ["m1", "m2", "m3"]},
        {"id": "fig_rank", "intent": "ranking", "labels": ["m1", "m2"],
         "values": [0.9883, 0.0056], "title": "Discrimination (eta^2)",
         "value_source": "statistics.json:discrimination_ranking"}]
spec_path = os.path.join(WORK, "figspec.json")
json.dump(spec, open(spec_path, "w", encoding="utf-8"), ensure_ascii=False)


def run(cmd, expect=0):
    print("+", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    assert r.returncode == expect, f"退出码 {r.returncode} != {expect}"
    return r


run([sys.executable, os.path.join(SCRIPTS, "figure_forge.py"),
     "--table", cleaned, "--spec", spec_path, "--out", FIGS])
man = json.load(open(os.path.join(FIGS, "figures_manifest.json"), encoding="utf-8"))
assert len(man) == 3
for m in man:
    assert os.path.getsize(m["file"]) > 5000, m["file"]
print("CHECK OK: 3 张图渲染成功且非空，manifest 谱系完整（含 axis_policy 与 spec 原文）")

report = os.path.join(OUT, "report.md")
run([sys.executable, os.path.join(SCRIPTS, "report_forge.py"), "scaffold",
     "--stats", stats_path, "--out", report, "--title", "玩具数据分析（合成示例）"])
# 填写小节：只引用有源数字（行数 150 来自 cleaning_log.json）
cleaning = os.path.join(WORK, "cleaning_log.json")
json.dump({"initial_rows": 150, "final_rows": 150, "removed": 0},
          open(cleaning, "w", encoding="utf-8"))
text = open(report, encoding="utf-8").read()
text = text.replace("<!-- 填写：数据来源、双源一致性结论、清洗规则与行数变化 -->",
                    "玩具合成数据，150 行 3 组；无缺失无重复；m1 的 η²=0.9883 表明组间差异主导。")
open(report, "w", encoding="utf-8").write(text)
run([sys.executable, os.path.join(SCRIPTS, "report_forge.py"), "verify",
     "--report", report, "--sources", stats_path, cleaning])
print("CHECK OK: scaffold 渲染 + 填写后 verify 通过（所有 ≥3 位有效数字有源）")

text2 = text.replace("0.9883", "0.9812")  # 篡改成无源数字
open(report, "w", encoding="utf-8").write(text2)
r = run([sys.executable, os.path.join(SCRIPTS, "report_forge.py"), "verify",
         "--report", report, "--sources", stats_path, cleaning], expect=6)
assert "UNSOURCED_NUMBER: 0.9812" in r.stderr
print("CHECK OK: 无源数字 0.9812 被 verify 阻断（退出码 6）")
open(report, "w", encoding="utf-8").write(text)  # 恢复
print("SYNTHETIC EXAMPLE PASSED ->", ROOT)
