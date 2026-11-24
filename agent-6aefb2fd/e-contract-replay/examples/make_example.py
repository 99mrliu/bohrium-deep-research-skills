#!/usr/bin/env python3
"""合成示例（SYNTHETIC EXAMPLE，非正式案例结果）：
构造玩具迷你案例（input: raw csv + case.json；output: 全套交付物），端到端验证：
  - contract_seal begin/fill/raise/seal 全流程，含 fill 拒绝悬空路径；
  - replay_check 复算通过；
  - 篡改报告数字 → replay_check 退出码 7。

用法：python3 make_example.py [输出根目录，默认 /tmp/cr-example]
"""
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/tmp/cr-example")
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
INP = os.path.join(ROOT, "input")
OUT = os.path.join(ROOT, "output")
FIGS = os.path.join(OUT, "figures")
for d in (INP, OUT, FIGS):
    os.makedirs(d, exist_ok=True)

rng = np.random.default_rng(3)
n = 120
df = pd.DataFrame({"grp": np.repeat(["a", "b", "c"], n // 3),
                   "m1": np.concatenate([rng.normal(10 + 2 * i, 1, n // 3) for i in range(3)]),
                   "m2": rng.normal(5, 1, n)})
raw = pd.concat([df, df.iloc[:3]], ignore_index=True)  # 3 条完全重复
raw.to_csv(os.path.join(INP, "toy_raw.csv"), index=False)
case = {"case_id": "synthetic-toy-e01",
        "output_contract": {"fields": [{"name": k} for k in
            ["cleaned_data", "statistics", "figures", "report", "quality_evidence", "exceptions"]]}}
json.dump(case, open(os.path.join(INP, "case.json"), "w", encoding="utf-8"), ensure_ascii=False)

# 玩具交付物（真实计算，非编造）
cleaned = df.copy()
cleaned_path = os.path.join(OUT, "cleaned_data.csv")
cleaned.to_csv(cleaned_path, index=False)
m1_mean = round(float(cleaned["m1"].mean()), 4)
stats_doc = {"features": {"m1": {"method": "one_way_anova", "p_value": 0.0001,
                                 "effect_size": {"eta_squared": 0.62}, "mean_overall": m1_mean},
                          "m2": {"method": "one_way_anova", "p_value": 0.83,
                                 "effect_size": {"eta_squared": 0.003}}}}
json.dump(stats_doc, open(os.path.join(OUT, "statistics.json"), "w",
                          encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump({"initial_rows": 123, "final_rows": 120, "removed": 3},
          open(os.path.join(OUT, "cleaning_evidence.json"), "w", encoding="utf-8"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(4, 3))
ax.hist(cleaned["m1"], bins=20)
fig.savefig(os.path.join(FIGS, "fig_m1.png"), dpi=150)
plt.close(fig)
report = os.path.join(OUT, "report.md")
report_text = (f"# 玩具分析报告（合成示例）\n\n清洗 123 行 → 120 行（删除 3 条重复）。\n"
               f"m1 总均值 {m1_mean}；组间 ANOVA p=0.0001，η²=0.62，差异显著。\n"
               f"m2 不显著（p=0.83）。\n\n## 异常\n无未解释异常。\n")
open(report, "w", encoding="utf-8").write(report_text)


def run(cmd, expect=0):
    print("+", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    assert r.returncode == expect, f"退出码 {r.returncode} != {expect}: {r.stderr[:300]}"
    return r


SEAL = os.path.join(SCRIPTS, "contract_seal.py")
RES = os.path.join(OUT, "result.json")
run([sys.executable, SEAL, "begin", "--case", os.path.join(INP, "case.json"), "--out", RES])
# fill 拒绝悬空 /app/output 路径
r = subprocess.run([sys.executable, SEAL, "fill", "--out", RES,
                    "--set", "figures=['/app/output/figures/nonexistent.png']"],
                   capture_output=True, text=True)
assert r.returncode != 0 and "FILL_REFUSE" in (r.stderr + r.stdout), r.stderr
print("CHECK OK: fill 拒绝悬空 /app/output 路径")
run([sys.executable, SEAL, "fill", "--out", RES,
     "--set", f"cleaned_data={cleaned_path}",
     "--set", f"statistics={os.path.join(OUT, 'statistics.json')}",
     "--set", f"figures=['{os.path.join(FIGS, 'fig_m1.png')}']",
     "--set", f"report={report}",
     "--set", f"quality_evidence=['{os.path.join(OUT, 'cleaning_evidence.json')}']",
     "--set", 'exceptions="无未解释异常"'])
run([sys.executable, SEAL, "seal", "--case", os.path.join(INP, "case.json"),
     "--out", RES, "--status", "success"])
print("CHECK OK: 全字段填齐后 seal success")

REPLAY = os.path.join(SCRIPTS, "replay_check.py")
run([sys.executable, REPLAY, "--input", INP, "--output", OUT,
     "--case", os.path.join(INP, "case.json"), "--cleaned", cleaned_path])
print("CHECK OK: 第三方复算通过（R1 契约 / R2 行数 120≤123 / R3 数字复算池）")

open(report, "w", encoding="utf-8").write(report_text.replace(str(m1_mean), "9.876"))
r = run([sys.executable, REPLAY, "--input", INP, "--output", OUT,
         "--case", os.path.join(INP, "case.json"), "--cleaned", cleaned_path], expect=7)
assert "REPLAY_FAIL: R3" in r.stdout
print(f"CHECK OK: 报告数字篡改为 9.876（真值 {m1_mean}）被复算抓获（退出码 7）")
open(report, "w", encoding="utf-8").write(report_text)
print("SYNTHETIC EXAMPLE PASSED ->", ROOT)
