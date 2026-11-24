---
name: assumption-gated-inference
description: >-
  Assumption-gated statistical inference with machine-checkable decision audit:
  one command loads CSV/SQLite, cleans (missing report_and_exclude, duplicate
  report/dedupe per policy, 1.5×IQR flag-only), then gates test selection on
  D'Agostino K² normality (n≥8) + Levene(median) homogeneity — Student/Welch t,
  Mann-Whitney U (tie-corrected), ANOVA / Welch ANOVA / Kruskal-Wallis — and
  writes a structured decision_log (per-group normality p, Levene p, n,
  chosen_test, reason_codes, rejected candidates, per-group value hashes) into
  result.json. An independent auditor (decision_audit.py) recomputes everything
  from raw data and exits 1 on ASSUMPTION_MISMATCH / TEST_MISMATCH /
  STAT_MISMATCH / P_MISMATCH / BOOT_CI_DRIFT / HOLM_MISMATCH / ALPHA_MISMATCH.
  Design-matched effect sizes (Hedges g with exact-J + bootstrap B=2000
  seed=20240501, η²/ω²/ε², rank-biserial, Hodges-Lehmann) and Holm post-hoc are
  bound to every result. 统计分析与结果解读：先验假设、再选检验、决策链全程留痕、
  可被独立重算审计（纯标准库统计核心，scipy 交叉校验 <1e-6）。不做：数据真实性/
  跨源一致性审计、图表美化渲染、文本措辞润色（其他 bundle 负责）。
---

# assumption-gated-inference — 假设门控推断 + 决策链可重算审计

**核心思想：** 检验选择不是"经验判断"，而是一条从原始数据出发、每一步都可被
独立脚本重算的决策链。pipeline 负责产出，auditor 负责证伪：假设结论翻转、
检验选错、统计量/p 被改动、bootstrap CI 漂移、Holm 算错、α 不符——全部
exit 1 并给出违例码。

## 何时使用 / 边界

**适用**：给定 `/input/case.json` + `/input/task.md` + 数据文件（CSV 有无表头、
多编码、缺失 token；SQLite 第一个用户表，TEXT 存数值也可）的**组间比较**任务
（两组或 k 组独立样本），需要：方法选择有据、效应量+95%CI、多重校正、结果可复核。

**不适用（明确边界）**：
- 配对设计、相关/回归、列联表（本 bundle 决策树只覆盖独立组间比较；遇到时
  在 limitations 中声明而非硬做）；
- 数据真实性、CSV↔SQLite 跨源一致性、单位口径审计（上游 bundle 职责）；
- 缺失机制分析与插补（本 bundle 只做 report_and_exclude）；
- 发表级图表渲染（仅产出示意性 SVG 箱线图）。

## 运行契约

- 输入：`/input/case.json` + `/input/task.md` + case.json 声明的数据文件。
- 中间产物：`/app/work`（digest.md、decisions.json）。交付：`/app/output`
  （result.json + report.md + fig_boxplots.svg）。
- `result.json` 必须含 `case_id` 与 `output_contract.required_fields` 全部字段
  （case_id, status, cleaning, descriptive, hypothesis_test, effect_size,
  confidence_interval, interpretation, limitations），另附 decision_log、
  sources(sha256)、reproducibility、uncertainty、exceptions、decisions。
- 诚实 partial：失败或部分完成写 `status=failed/partial` 并附 exceptions 原因，
  绝不静默跳过，绝不预制答案——所有数字必须真实运行产生。

## 精确命令工作流

```bash
# 0. 定向（1 次请求）
cat /input/case.json /input/task.md; ls -la /input

# SKILL_DIR 探测（Skill 安装目录，通常 /skills/weekly-skill）
SKILL_DIR=$(dirname "$(find /skills -name 'pipeline_b.py' -path '*scripts*' 2>/dev/null | head -1)")/..
# 若上面为空：SKILL_DIR=/skills/weekly-skill

# 1. 一键 baseline 全流程（0 模型请求，秒级）
python3 $SKILL_DIR/scripts/pipeline_b.py run \
  --input-dir /input --work-dir /app/work --output-dir /app/output

# 2. 重心审计：独立重算决策链（0 模型请求；exit 0 才可信任）
python3 $SKILL_DIR/scripts/decision_audit.py \
  --input-dir /input --result /app/output/result.json

# 3. 读 digest，确认/覆盖 ≤5 项裁决（1 次请求；无误可跳过）
cat /app/work/digest.md
python3 $SKILL_DIR/scripts/pipeline_b.py decide --work-dir /app/work \
  --key outcomes --value '["strength"]' --reason "task 只关注抗压强度"
# key ∈ group / outcomes / focus / alpha / drop_grouping
# 注意：alpha 以 case.json constraints 为契约；decide 覆盖 alpha 会触发
# decision_audit 的 ALPHA_MISMATCH（审计硬性比对 case.json），仅当你确认
# case.json 本身有误且同步修改它时才使用。

# 4. finalize 重写交付物（0 模型请求）
python3 $SKILL_DIR/scripts/pipeline_b.py finalize \
  --input-dir /input --work-dir /app/work --output-dir /app/output

# 5. 交付前自查（0 模型请求）：audit exit 0 + JSON 合法
python3 $SKILL_DIR/scripts/decision_audit.py --input-dir /input --result /app/output/result.json
python3 -m json.tool /app/output/result.json > /dev/null && echo JSON-OK
```

若步骤 3 做了 decide，必须重新执行步骤 4 与 5。

## 方法决策规则（硬规则，依据 references/decision-tree.md）

| 场景 | 门控 | 选择 |
|---|---|---|
| 两组 | 全正态(K² p≥α)+方差齐(Levene median p≥α) | Student t |
| 两组 | 全正态+方差不齐 | Welch t |
| 两组 | 任一非正态 / n<8(not_tested) / 零方差 | Mann-Whitney U（tie 校正渐近） |
| k 组 | 全正态+齐 | 单因素 ANOVA（η²/ω²） |
| k 组 | 全正态+不齐 | Welch ANOVA（Welch 1951，η²/ω² 经典口径） |
| k 组 | 其他 | Kruskal-Wallis（tie 校正，ε²） |

- n<8 不做正态性检验，按非正态保守处理（reason_codes 记 `N_LT_8`）；
- 效应量与 CI 口径：见 references/effect-and-ci.md（方向=排序后第二组−第一组；
  bootstrap B=2000 seed=20240501）；
- 事后两两与主检验同路线，Holm 校正，家族=结局内全部两两对，k>6 不做
  （references/multiplicity.md）；
- p 报告 4 位、<0.0001 记 `<0.0001`；结论措辞"在 α=… 水平下差异具有/不具有
  统计学意义"，**禁用"证明"**；显著性与实际意义分开陈述；
- α 一律取 case.json constraints.alpha（默认 0.05），假设门控与主检验共用。

## 预算表（≤64 次请求内，典型 ≤8 次）

| 步骤 | 模型请求 |
|---|---|
| 0 定向 | 1 |
| 1 run / 2 audit / 5 自查 | 0（脚本） |
| 3 读 digest + 裁决 | 1–2 |
| 4 finalize 后核对 report | 1–2 |
| 余量（异常处理、补充解读） | ≤3 |
| **合计** | **≤8** |

## 异常处理表

| 异常 | 识别 | 处置 |
|---|---|---|
| 样本量不足（组 n<8） | decision_log `N_LT_8` | 按非正态保守处理，uncertainty 标注功效不足 |
| 组内方差为零 | `ZERO_VAR` | 正态性记无意义→非参路线；两组均零方差且均值相等 → p=1 |
| 缺失比例高 | cleaning.missing 计数 | report_and_exclude；>20% 时 limitations 警示 |
| 假设不成立 | NORMALITY_FAIL / VAR_INHOMOG | 决策树自动切换 Welch / 秩路线并留痕 |
| 单位不明 | task.md 无单位标注 | unit=null，解释中注明"单位未声明" |
| SQLite 连接失败/无用户表 | exceptions `no_data_table` | 回退 CSV；全无表 → status=failed，exit 1 |
| CSV 无表头 | 表头嗅探（≥半数非数值） | 内置 iris/wine 列名 profile，否则 col_1..N |
| 分组列识别错误 | digest 第 1 项 | `decide --key group --value <列名>` 后 finalize |
| 结局应收窄 | digest 第 2 项 | `decide --key outcomes --value '["…"]'` |
| 完全重复行 | cleaning.duplicates | 未声明 policy 时只报告不删除（圆整测量下重复可为真实观测）；constraints.duplicate_policy 声明时去重保留首行 |
| 组数 >6 | holm.note + exceptions | 只报 omnibus，不做两两比较 |

## 文件清单

- `scripts/statcore_b.py` — 纯标准库统计核心（Lentz 连分式不完全 β、级数/连分式
  γ、Acklam 正态逆函数、K²/Levene/t/Welch/MW/ANOVA/Welch-ANOVA/KW、Hedges g
  精确 J、bootstrap、HL、Holm）
- `scripts/pipeline_b.py` — run/decide/finalize 一键管线，产出含决策链
- `scripts/decision_audit.py` — 重心：独立重算审计器（7 类违例码）
- `scripts/crosscheck_scipy.py` — 可选：scipy 交叉校验（缺失时优雅跳过）
- `references/decision-tree.md` — 决策树、decision_log 契约、审计口径（附录 A）
- `references/assumption-checks.md` — n<8 功效、K² vs Shapiro、Levene 变体
- `references/effect-and-ci.md` — 效应量/CI 口径、bootstrap 确定性协议
- `references/multiplicity.md` — Holm 与家族划分
- `examples/` — 合成示例（make_synthetic.py + run_example.sh 自断言 +
  minimal-example.md + example_output/ 真实产物）
