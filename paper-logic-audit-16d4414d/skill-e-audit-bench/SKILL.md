---
name: audit-bench-selftest
description: >-
  论文逻辑与论证审查的可验证性工作流：先用内置合成基准自测审查质量，再跑真实案例，
  把"增益证据"做成与正式结果同构、可复跑的记录。当任务是审查 /input 中的科研论文
  （case.json + task.md + PDF/文本材料）且需要证明审查协议真的有效（而不是只声称有效）
  时使用。核心立场：多数审查 Skill 只声称更好，无法证明——本 Skill 附带三篇带已知
  植入缺陷的合成小论文（p1 结论超出数据、p2 跨章不一致、p3 干净对照）和确定性评分器
  scripts/bench.py（纯标准库、零依赖）：先在同一 finding schema 下跑基准得到可复核的
  召回率/精确率/误报率与复跑稳定性（STABLE/DRIFT），再跑真实案例；评分器同时充当
  交付门禁（quote 逐字、字段齐全、空话建议拦截）。召回低于阈值时明确提示先修协议。
  不适用：文字润色、查重、参考文献格式规范、统计复算。
---

# audit-bench-selftest：先证明你的审查协议有效，再用它审真论文

## 定位

本 Skill 的重心在**可验证性**：对应评分维度"增益可验证性"与"创新证据"。它把
审查协议（finding schema + 严重度判据 + 反误报规则）当作被测对象：基准三篇
合成论文的植入缺陷是已知真值，跑出的召回/精确/误报是协议能力的可复跑证据；
真实案例的 findings 用同一 schema 产出，provenance 里同时给出基准成绩。

## 固定路径与运行契约

- 引擎：`/skills/weekly-skill/scripts/bench.py`（下文 `$BN`，`python3`，≥3.8，纯标准库）
- 基准：`/skills/weekly-skill/bench/`（p1.txt / p2.txt / p3.txt / key.json，**合成基准，
  非正式案例**）
- 参考：`/skills/weekly-skill/references/bench_protocol.md`（缺陷类型表、评分定义、
  协议校准方法）
- 输入：`/input/case.json`、`/input/task.md`、论文材料（PDF 先转文本）
- 工作区：`/app/work`；交付：`/app/output/result.json` + `report.md`
- `result.json` 必须含原 `case_id` 与 `output_contract` 全部字段；第 0 步先写骨架

## 执行协议

### 第 0 步：读契约、写骨架

读 case.json、task.md；立即写 result.json 骨架（全字段占位 + in_progress）。

### 第 1 步：基准自测（先证明，再上场）

对 bench/ 三篇各做一轮完整审查（与真实案例同一流程：逐句读、按 schema 出
findings、quote 逐字），然后评分：

```bash
for p in p1 p2 p3; do
  python3 $BN grade --bench /skills/weekly-skill/bench --paper $p \
    --findings /app/work/findings_$p.json --runs /app/work/runs.jsonl
done
```

- recall < 0.6（exit=2）：说明审查协议有系统性漏检——先对照 key.json 的
  `expect` 字段修协议（漏了哪类缺陷、为什么漏），重跑达标后再上真实案例。
- p3 的 false_alarms 是误报率：>0 说明反误报规则失效，同样先修。
- 再复跑一次 p1：runs.jsonl 给出 STABLE/DRIFT，证明协议可复跑。

### 第 2 步：真实案例审查（主战场）

```bash
python3 $BN anchor --paper /app/work/paper.txt --work /app/work
```

用与基准完全相同的流程审查真实论文。六类检查项（事实核验、引用支持、方法
设计、统计报告、论证链、学术规范）逐类过；每条 finding：type ∈ {事实错误,
证据不足, 规范问题, 建议, 待复核}、severity ∈ {critical, major, minor, info}、
sentence_id、逐字 quote、basis（判断依据，写清定级三问：是否影响主结论/
是否可修正/是否影响可复现）、suggestion（落到改哪句、补什么证据，≥15 字）。

### 第 3 步：交付门禁

```bash
python3 $BN verify --work /app/work --findings /app/work/findings_case.json
```

exit=4 按 bench_verify.json 逐条修正重跑；全过才能写 /app/output。

### 第 4 步：交付

result.json：output_contract 全字段 + case_id + findings + status（通过/问题/
待复核/未检查分列）+ uncertainty + provenance（**必须含基准成绩**：三篇
recall/precision/false_alarms、复跑稳定性、引擎版本）。report.md 按严重度
排序，附基准成绩小节——评审据此判断这份审查的可信度。

## 严重度判据

critical：主结论不成立（证据相反/无证据）。major：削弱论证但可救（口径
冲突、关键承诺未交付）。minor：局部问题。info：建议。禁止一律"中"。

## 反误报规则

1. 对照组、作者自注假设、转述他人观点（带引用标记）不计作者缺陷。
2. 基准 p3 的每条 false_alarm 都必须归因到哪条规则失效，并写进 uncertainty。
3. 拿不准 → 待复核 + 说明，不凭空补结论。

## 预算规划（64 次模型请求 / 900 秒）

工具不占模型预算。第 1 步基准三篇 ≤15 次（小论文，快）；不达标只允许修
协议重跑一轮，仍不达标则在 provenance 如实记录并继续（诚实优于满分）。
第 2 步 ≥30 次；第 3–4 步 ≥4 次。

## 异常处理

| 情况 | 处置 |
|-|-|
| 扫描版无文本层 | `未检查/no_text_layer` 交付 partial |
| 基准 recall 不达标 | 修协议重跑一轮；仍不达标如实记录，不隐瞒 |
| verify exit=4 | 按 bench_verify.json 逐条修正，禁止删字段绕过 |
| grade 输出文件被复跑覆盖 | 属预期：逐次成绩以 runs.jsonl 台账为准 |

## 不适用

文字润色、查重、参考文献格式规范、统计复算、投稿策略。

## 最小示例

`examples/minimal/`（**合成示例，非正式案例**）：演示全循环——合格 findings
三篇满分、复跑 p1 判 STABLE；弱 findings（漏报 2 条 + 误报 1 条 + 伪造 quote
1 条）被评分器标出 recall=0.33 与逐字违规（exit=2）；真实案例侧 anchor +
verify 门禁拦截伪造 quote。`sh examples/minimal/run_example.sh` 真实执行，
产物在 `examples/minimal/outputs/`。
