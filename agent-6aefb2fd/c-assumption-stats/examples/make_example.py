#!/usr/bin/env python3
"""合成示例（SYNTHETIC EXAMPLE，非正式案例结果）：
构造三组合成数据验证决策树的分流：
  feat_normal：三组正态、组间有差异 → 应选 ANOVA，显著，η² 大
  feat_skewed：对数正态、组间有差异 → 应选 Kruskal-Wallis + Dunn
  feat_null  ：三组同分布 → 不显著
另构造回归数据 y = 2*x1 - x2 + 噪声 验证 regress 模式。

用法：python3 make_example.py [输出根目录，默认 /tmp/ps-example]
"""
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/tmp/ps-example")
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
os.makedirs(ROOT, exist_ok=True)

rng = np.random.default_rng(42)
n = 40
frames = []
for gi, g in enumerate(["g1", "g2", "g3"]):
    frames.append(pd.DataFrame({
        "grp": g,
        "feat_normal": rng.normal(10 + 3 * gi, 1.0, n),
        "feat_skewed": rng.lognormal(1.0 + 0.5 * gi, 0.8, n),
        "feat_null": rng.normal(5.0, 1.0, n),
    }))
df = pd.concat(frames, ignore_index=True)
toy = os.path.join(ROOT, "toy_groups.csv")
df.to_csv(toy, index=False)

m = 120
x1, x2 = rng.normal(0, 1, m), rng.normal(0, 1, m)
y = 2 * x1 - x2 + rng.normal(0, 0.3, m)
pd.DataFrame({"x1": x1, "x2": x2, "y": y}).to_csv(
    os.path.join(ROOT, "toy_regress.csv"), index=False)


def run(cmd):
    print("+", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    assert r.returncode == 0, r.returncode
    return r


run([sys.executable, os.path.join(SCRIPTS, "premise_stats.py"), "group",
     "--table", toy, "--group", "grp", "--out", ROOT])
doc = json.load(open(os.path.join(ROOT, "statistics_group.json"), encoding="utf-8"))
assert doc["features"]["feat_normal"]["method"] == "one_way_anova", \
    doc["features"]["feat_normal"]["method"]
assert doc["features"]["feat_skewed"]["method"] == "kruskal_wallis", \
    doc["features"]["feat_skewed"]["method"]
assert doc["features"]["feat_skewed"]["posthoc"], "Dunn 两两比较缺失"
assert not doc["features"]["feat_null"]["significant_bonferroni_family"]
assert doc["features"]["feat_normal"]["significant_bonferroni_family"]
assert doc["discrimination_ranking"][0]["feature"] == "feat_normal"
assert doc["multiple_testing"]["bonferroni_alpha"] == round(0.05 / 3, 6)
print("CHECK OK: 正态→ANOVA / 偏态→KW+Dunn / 零效应→不显著；排序首位 feat_normal；Bonferroni α=0.0167")

run([sys.executable, os.path.join(SCRIPTS, "premise_stats.py"), "regress",
     "--table", os.path.join(ROOT, "toy_regress.csv"), "--target", "y", "--out", ROOT])
rdoc = json.load(open(os.path.join(ROOT, "statistics_regression.json"), encoding="utf-8"))
ols = rdoc["ols_standardized"]
assert ols["r_squared"] > 0.95, ols["r_squared"]
assert ols["coefficients"]["x1"]["beta_std"] > 0.5 > ols["coefficients"]["x2"]["beta_std"]
assert "因果" in ols["caveat"]
print(f"CHECK OK: 回归 R²={ols['r_squared']}，β_x1={ols['coefficients']['x1']['beta_std']} > 0 > "
      f"β_x2={ols['coefficients']['x2']['beta_std']}，强制因果声明在位")
print("SYNTHETIC EXAMPLE PASSED ->", ROOT)
