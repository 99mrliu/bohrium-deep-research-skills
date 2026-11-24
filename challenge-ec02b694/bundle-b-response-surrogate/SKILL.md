---
name: response-surrogate
description: 当任务涉及实验响应指标（转化率、收率、强度等）的口径登记与基于历史数据的代理模型预测时使用；强制披露预测不确定度与外推风险，禁止把模型预测当作实测值。
---

# response-surrogate：响应指标代理建模与不确定度诚实

## 1. 定位声明

本技能解决「实验参数优化建议」中方向 2 的问题：**响应指标定义与代理建模**。

核心主张：

- 先登记指标口径（名称、单位、测量方法、优化方向、可接受波动），再谈任何数值比较；
- 用历史数据拟合的代理模型（RSM）只产出**带不确定区间的预测**，区间与有效域是机器可检查的产物；
- 在外推区给出无不确定度的"精确"预测、或把模型预测写成实测值，是本技能明确禁止的典型失败。

本技能 = 本方法规程 + `scripts/` 下三个确定性 Python 脚本（Python 3 标准库，无网络）。
技能只做**口径登记、拟合、预测与风险标注**，不替 Agent 做最终科研判断。

## 2. 何时使用 / 不适用

**何时使用（触发条件）**

- 任务要求根据历史实验数据建议下一轮实验条件；
- 任务涉及"预测某条件下的指标""找最优参数""响应面/代理模型"等表述；
- 案例提供历史 CSV/表格，且响应指标可量化。

**不适用**

- 没有任何历史数据（纯文献调研）——直接走文献证据路径，不要虚构代理模型；
- 响应指标无法量化或口径本身存在争议且无法从材料中澄清——登记为 uncertainty，诚实报 `partial`；
- 机理解释、动力学推导类任务——代理模型是黑箱局部近似，不提供机理。

## 3. 运行时契约（Harness 环境）

- 技能安装于 `/skills/weekly-skill`；Agent 工作目录 `/app/work`；输入在 `/input/`，结果写 `/app/output/`。
- `/input/case.json` 含 `case_id`、任务描述、`output_contract` 字段清单、材料路径；`/input/task.md` 为任务正文；案例材料为真实 PDF/文本/CSV，PDF 用 `pdftotext` 自行解析。
- 最终 `/app/output/result.json` 必须含：`case_id`（照抄输入）、`output_contract` 声明的**全部字段（动态读取 case.json，不得硬编码）**、`status`（success/partial/unable_to_determine/refused，诚实）、`sources`、`uncertainty`、变更记录。
- 预算约 64 次模型请求 / 900 秒：**脚本运行优先、尽早落盘诚实 partial**，不要在拟合细节上反复消耗请求。

## 4. 固定命令顺序

在 `/app/work` 下依次执行（路径按实际调整）：

```bash
# 0. 读取 /input/case.json，确定因子列名与响应指标列名（PDF 材料先 pdftotext 解析）
# 1. 指标口径注册
python3 /skills/weekly-skill/scripts/metric_registry.py \
    --case /input/case.json --csv history.csv \
    --factors factor1,factor2 --out metric_registry.json
# 2. 代理模型拟合（quadratic 优先，样本不足自动降级）
python3 /skills/weekly-skill/scripts/fit_surrogate.py \
    --csv history.csv --factors factor1,factor2 --response metric_name \
    --model auto --out surrogate.json
# 3. 候选点预测（可多个；域外自动触发 extrapolation 警告）
python3 /skills/weekly-skill/scripts/predict.py \
    --surrogate surrogate.json \
    --points candidates.json --out prediction.json
# 4. 汇总写 /app/output/result.json
```

退出码约定：`0` 正常；`1` 降级/外推/空注册表（产物仍有效，但必须在 result.json 中如实反映）；`2` 输入级错误（产物为占位/错误说明）。任何退出码下脚本都不会 traceback，且都尽量落盘。

## 5. 工作流程与预算分配（约 64 请求 / 900 秒）

| 阶段 | 动作 | 模型请求预算 | 时间预算 |
|---|---|---|---|
| A 读输入 | 读 case.json / task.md；`pdftotext` 解析材料；确定因子与响应列 | ≤ 8 | ≤ 120 s |
| B 注册口径 | 跑 metric_registry.py；把单位缺失/列缺失写入 uncertainty | ≤ 4 | ≤ 60 s |
| C 拟合 | 跑 fit_surrogate.py；读 surrogate.json 的 R²、LOO-CV RMSE、诊断 | ≤ 6 | ≤ 90 s |
| D 预测 | 选 3–8 个候选点跑 predict.py；域内/域外分开标注 | ≤ 6 | ≤ 90 s |
| E 组装 result.json | 按 output_contract 填字段；预测值一律标注 `[模型预测 ±区间]` | ≤ 16 | ≤ 240 s |
| F 校验落盘 | 复查字段齐全、status 诚实、sources/uncertainty 非空 | ≤ 8 | ≤ 120 s |
| 余量 | 意外重试 | ~16 | ~180 s |

**降级守则**：任一脚本退出码非 0 时，不重试超过 1 次；把降级产物与原因直接写进
`evidence_and_risk` 与 `uncertainty`，status 置 `partial`，继续走完流程。

## 6. 输出物说明表

| 产物 | 生成者 | 关键字段 | 用途 |
|---|---|---|---|
| `metric_registry.json` | metric_registry.py | `metrics[]`(name/unit/method/direction/acceptable_fluctuation)、`validation.uncertainties[]` | 指标口径的机器可检查登记；一切数值比较前先核口径 |
| `surrogate.json` | fit_surrogate.py | `mode`(rsm/fallback)、`coefficients`、`r_squared`、`loo_cv.rmse`、`residual_diagnostics`、`valid_domain.box`、`uncertainty_model` | 代理模型及其可信范围；`mode=fallback` 时禁止给出"精确"预测 |
| `prediction.json` | predict.py | `predictions[].prediction`、`interval_95`、`extrapolation`、`warnings[]` | 候选点预测；`extrapolation=true` 的值只能作为待确认假设 |
| `/app/output/result.json` | Agent 汇总 | `case_id` + output_contract 全字段 + `status`/`sources`/`uncertainty`/变更记录 | 评测契约产物 |

## 7. 异常处理表

| 异常 | 脚本行为 | Agent 义务 |
|---|---|---|
| 样本不足（n < p+2） | 拒绝拟合，`mode=fallback`，均值/最近邻 + 显式放大区间（≥3σ 或半极差），写明"样本不足，预测仅供假设" | result.json 中预测必须标注为假设；status 至多 `partial`；confirmation_items 必须含补实验 |
| 正规方程奇异 | 拒绝拟合并说明（主元 < 1e-12），走同一降级路径 | 检查是否因子共线/常数因子；在 uncertainty 中说明设计缺陷 |
| 单位缺失 | 注册表 `unit=null` + uncertainty，**禁止猜单位** | 任何跨来源数值比较前，先把"单位未知"写进 uncertainty |
| 列缺失 | 对应 check 置 fail + uncertainty，注册表仍落盘 | 该指标无证据来源，result.json 中相应字段降级或标 unable_to_determine |
| 候选点在有效域外 | `extrapolation=true`，区间按 (1+3×相对越界距离) 放大，附"该预测为待确认假设，不得作为可执行事实" | 该候选点只能进 confirmation_items，不得作为推荐条件写进 experiment_plan |
| fallback 模式下预测 | 强制 extrapolation 级警告，区间注明非统计意义 | 同上，且必须在 evidence_and_risk 里复述降级原因 |
| PDF 无法解析 / 材料缺失 | — | 记录到 uncertainty，用可得材料继续，status 诚实降级 |

## 8. result.json 契约

```json
{
  "case_id": "<照抄 /input/case.json 的 case_id>",
  "status": "success | partial | unable_to_determine | refused",
  "experiment_plan": "…（按 case.json output_contract 动态确定的字段之一）",
  "evidence_and_risk": "…",
  "confirmation_items": "…",
  "sources": ["metric_registry.json", "surrogate.json", "prediction.json", "案例材料路径/页码"],
  "uncertainty": ["单位缺失…", "样本不足…", "外推候选点…"],
  "change_log": ["注册了 X 个指标", "拟合 quadratic RSM: R2=…, LOO-RMSE=…", "候选点 P3 触发外推警告"]
}
```

硬性规则：

1. `case_id` 照抄输入；output_contract 字段**从 case.json 动态读取**，缺任一个字段即违约；
2. 每个写进 `experiment_plan` 的预测值必须带区间并标注 `[模型预测]`；外推/降级值只能进 `confirmation_items`；
3. `status` 诚实：有任何脚本降级、单位缺失、列缺失、外推候选被采用，都不得报 `success`；
4. `uncertainty` 至少汇总 metric_registry 与 surrogate/predict 的全部 warnings。

## 9. 合成示例

`examples/` 含完整合成示例（数据为人工合成 + 小噪声，见 `examples/README.md`）：

- 输入：`examples/synthetic-input/case.json`（case_id、三字段 output_contract、材料路径）、`history.csv`（12 组 温度×时间→转化率%）、`small_history.csv`（n=4）；
- 输出（真实运行产物）：`metric_registry.json`、`surrogate.json`（quadratic，R²≈0.977，LOO-CV RMSE≈1.49）、`prediction_in_domain.json`（域内正常）、`extrapolation_flagged.json`（域外负例）、`small_surrogate.json` + `small_sample_fallback.json`（n=4 触发拒绝拟合与降级路径）。

复现命令见 `examples/README.md`。

## 10. 局限（必须如实告知调用方）

- **RSM 是局部近似**：完全二次模型只在训练数据邻域内有效，不承诺找到全局最优，更不能外推机理；
- **不能替代实测**：代理模型的所有预测都是待确认假设，最终实验条件必须经实验验证；
- 标准库 OLS 未做正式正态性/异方差检验，残差诊断仅为摘要统计；
- LOO-CV RMSE 在小样本下方差很大，只能作量级参考；
- 有效域盒是各维 min/max 的轴对齐盒，盒内空洞（无数据区域）不会被识别为外推；
- 单响应建模：多响应间的权衡需要 Agent 自行处理，本技能不做多目标聚合。
