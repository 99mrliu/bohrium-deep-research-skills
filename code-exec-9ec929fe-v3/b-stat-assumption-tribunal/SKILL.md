---
name: stat-assumption-tribunal
description: >-
  统计推断合规裁决技能。适用场景：案例要求描述统计、组间比较、相关分析或任何需要可辩护的数值结论时；
  核心价值是前提检验不过关就不允许报告 p 值——自动改判非参数备选并给出书面理由，且每个描述统计量
  都附带显式口径（ddof、四分位方法、缺失策略、去重策略）。也适用于复核既有数值断言（verify-claims
  独立复算）。不适用场景：纯 SQL 抽取、仅绘图、无需统计口径的机械汇总。
---

# stat-assumption-tribunal：统计推断合规裁决

## 重心与设计理由

静默统计错误是科研数据分析中最危险的失败模式：把缺失值当 0、未声明去重口径就分组、
t 检验前提未检查就报告 p 值、同一报告内口径不统一。本技能的对策是把「能不能报」与
「报多少」分离：工具 `scripts/stattool.py` 先执行显式前提检验（正态性、方差齐性、
最小样本量），前提通过才允许参数检验的 p 值进入结论；前提失败时自动改判
（reroute）到 Mann-Whitney U 或 Kruskal-Wallis，并在 `reroute_reason` 中写明理由，
退出码 2 表示「已改判」这一劝告性事实而非失败。所有描述统计量双口径并列
（ddof=0 与 ddof=1、inclusive 与 exclusive 四分位），缺失与重复行计数单列，
杜绝口径含糊。工具仅用 Python 标准库，特殊函数（不完全 beta、不完全伽马、
t／F／卡方 CDF）自行实现并经 `selftest` 子命令数值校验，无网络依赖。

## 固定路径与运行契约

- 技能安装位置：`/skills/weekly-skill`，裁决工具为 `/skills/weekly-skill/scripts/stattool.py`。
- 输入：`/input/case.json`（含 `case_id` 与 `output_contract` 必填字段）、`/input/task.md`、
  数据字典与数据文件。只读，不得修改。
- 草稿：`/app/work`（中间 JSON、日志）。
- 交付：`/app/output`，其中 `result.json` 必须包含：
  1. `case_id` 与 `output_contract` 声明的全部字段；
  2. `status`（`complete`／`partial`／`in_progress`，如实填写）；
  3. `anomalies`（缺失、重复、异常值、前提失败等，逐条列出）；
  4. `provenance`（输入文件 sha256、行数、工具与 Python 版本——直接取自 stattool
     输出 JSON 的 `input` 与 `tool_version` 字段）；
  5. 变更记录（对数据施加的任何过滤、剔除、转换）。
- 诚实原则：前提不满足时不得报告参数检验 p 值；无法计算的字段如实写入
  `partial` 并在 `missing_fields` 中说明原因；不得编造数值；不得静默类型转换。

## 执行协议

1. **描述统计先行落盘**：对每个涉及的数值列运行
   `python3 /skills/weekly-skill/scripts/stattool.py descriptive --csv <数据> --col <列> [--group <分组列>] --out /app/work/desc_<列>.json`，
   记录 n、n_missing、双 ddof 标准差、双方法四分位、偏度、峰度与均值 95％ CI。
2. **推断先裁决后引用**：组间比较运行
   `stattool.py compare --csv <数据> --group <分组列> --value <数值列> --out /app/work/compare_decision.json`；
   相关分析运行 `stattool.py corr --csv <数据> --x <列1> --y <列2>`。
   仅在 `reroute_reason` 为 null 时引用参数检验结果；否则引用改判后的检验，
   并在结论中复述改判理由。
3. **回填 result.json**：把 decision JSON 的关键数字（chosen_test、statistic、df、
   p_value、effect_size、ci95、prerequisite_checks 的逐项结论）填入 `result.json`
   对应字段，并注明完整检验链（前提检验名称 → 通过与否 → 最终检验）。
4. **verify-claims 复核**：把写入 `result.json` 的每一条数值断言整理成 claims 文件，
   运行 `stattool.py verify-claims --claims <claims.json> --csv <数据>`；
   退出码非 0 时不得交付，须修正断言后复跑。
5. **交付前 checklist**：`case_id` 一致；`output_contract` 字段齐全；
   `status` 与事实相符；`anomalies` 非空列表逐条可溯源；`provenance` 含输入 sha256；
   所有 p 值均有对应前提检验记录；口径（ddof、四分位方法、缺失策略）已写明。

## 异常处理

- **缺列**：工具报错并列出可用列名，退出码 1；应核对数据字典后换用正确列名，
  不得猜测同义列。
- **n 过小**：描述统计要求 n≥3；compare 中任一组 n<3 直接拒绝；任一组 n<8 时
  拒绝参数检验并改判秩检验。此类限制须写入 `anomalies` 与 `missing_fields`。
- **并列秩过多**：秩检验自动施加并列校正（tie correction）并在输出中报告
  `n_tie_groups`；全部取值相同（完全并列）时工具报无法计算，不得强行给出 p 值。
- **常数列**：方差为 0 的列在 descriptive 与 corr 中直接报错退出；compare 中
  常数组无法通过正态性前提，按改判逻辑处理。
- **非数值内容**：除已声明的缺失标记（空、NA、N/A、NaN、null、None、.）外，
  无法解析的取值一律报错，绝不静默转为 0 或缺失。

## 预算意识

- 每个子命令一次调用即输出完整 JSON 并可用 `--out` 落盘，落盘文件即 partial
  交付物；应按「描述 → 裁决 → 复核」顺序执行，每步成功即保存，避免预算耗尽时
  无物可交。
- 64 次模型请求、900 秒的预算下，stattool 的单次运行耗时在毫秒级，模型请求应
  主要用于解读结果与撰写结论，而非反复重算；verify-claims 应在写定 result.json
  后一次性复核全部断言。
- 示例脚本 `examples/run_example.sh` 一次跑通全流程，可作为零探索成本的调用模板。

## 最小调用示例（合成示例）

```bash
# 数据：examples/synthetic_case/two_groups_syn.csv（82 行虚构数据，A 组近似正态、
# B 组右偏，含 4 个缺失值与 2 行重复；列：sample_id,group,value,dosage）
python3 scripts/stattool.py descriptive \
  --csv examples/synthetic_case/two_groups_syn.csv --col value --group group \
  --out /app/work/desc_value.json
# 期望：B 组正态性前提失败 → 改判 Mann-Whitney，退出码 2
python3 scripts/stattool.py compare \
  --csv examples/synthetic_case/two_groups_syn.csv --group group --value value \
  --out /app/work/compare_decision.json
echo "compare exit=$?"
python3 scripts/stattool.py corr \
  --csv examples/synthetic_case/two_groups_syn.csv --x value --y dosage
python3 scripts/stattool.py verify-claims \
  --claims examples/synthetic_case/claims_demo.json \
  --csv examples/synthetic_case/two_groups_syn.csv
echo "verify exit=$?"   # 演示文件含 2 条故意写错的断言，期望退出码 1
```

实测行为：compare 输出 `chosen_test = mann_whitney_u`、
`reroute_reason` 指明 B 组 D'Agostino-Pearson K² 检验 p≈2.5e-8 未通过，
退出码 2；verify-claims 对 6 条断言给出 4 PASS／2 FAIL，退出码 1。
完整演示见 `examples/run_example.sh`。

## 局限性

- 正态性筛查采用 D'Agostino-Pearson K²（n≥8）加小样本偏度／峰度经验规则，
  属通行惯例而非定理；临界值可在 `references/statistical_playbook.md` 查阅依据。
- Mann-Whitney 与 Kruskal-Wallis 采用并列校正的正态／卡方近似，未实现精确
  置换分布；每组 n 极小（3–7）时 p 值仅为近似。
- 多重比较不自动校正，只在 playbook 中要求显式报告比较次数。
- 仅处理单数值列、单分组变量的一维设计；不支持配对设计、协变量调整与
  回归建模。
- verify-claims 的容差为相对 1e-6（p 值绝对 1e-3），跨工具小数位差异可能
  触发 FAIL，此时应核对口径而非强行对齐。
