---
name: conditioned-relation-kg
description: 构建“条件化关系”文献知识图谱——证据绑定的关系记录区分 uses/evaluates/reports/derives_from/compares_with/outperforms/supports/contradicts/measured_on/cites_background，强制 author voice（primary-results/cited-background/interpretation/hypothesis）、比较必须带 metric/basis+comparator、数值必须带单位与条件作用域、跨篇共现不建边、冲突全部保留不静默解决；当任务要求从两篇论文抽取有证据、有方向、有条件的关系并执行真实查询时使用。
---

# conditioned-relation-kg：条件化关系图谱（连得对 · 关系审计）

核心立场：**一条关系不是一个三元组，而是一份带条件的证据记录。**
本 Skill 的中心是关系语义、方向、认识状态（author voice）与条件作用域，
不是通用实体链接。它强制：背景转述永远不得当作一手证据；比较必须带
指标/依据与比较对象（禁止全局赢家）；数值必须带单位且绑定条件；
跨篇共现不是直接关系；同源/跨源冲突全部保留、绝不静默仲裁。

## 运行契约（Runtime contract）

- 输入：`/input/` 下的 `case.json`、`task.md`、`corpus-manifest.json`、
  `material.json`、`primary-material.json`、`secondary-material.json`，
  可选 `secondary-publisher.xml`（仅供核对线性化公式，不作抽取来源）。
  **读真实文件**，不得凭标签臆测内容；`case.json` 根元数据
  （doi/title/authors）**只属于第一篇**，不得套用到第二篇。
- 立即创建 `/app/work`，并尽早写出 `/app/output/result.json` 的诚实
  部分结果（含原始 `case_id` 与 `output_contract` 全部键的占位镜像），
  随后增量改进。
- 每个节点/边必须有：`source_id` + 组织方 JATS `paragraph_id` +
  **逐字短引**；禁止 PDF 页码，禁止外推数据，未报告项如实保留。
- 最终 `result.json`：动态镜像 `output_contract` **全部原始键**，
  附 `status` / `sources` / `uncertainty` / `changes`；
  材料缺失、无法判断与运行失败分别说明。
- 不提交预制答案：所有节点、边、合并决定与查询结果都来自对真实输入的
  真实运行。

## 工作流（Workflow）

1. **引导**：`python3 scripts/case_bootstrap.py --input /input --out /app/output`
   写出早期部分 `result.json`（status=partial，contract 键占位）。
2. **抽取（Agent 完成）**：按 `references/relation-schema.md` 阅读两篇
   材料，在 `/app/work` 写 `nodes.json`、`relations.json`（含
   `cooccurrence_notes` 与可选 `extensions`）、`merge_decisions.json`、
   `queries_spec.json`（≥3 个查询）。author voice 判定规则见
   `references/voice-conditions.md`。
3. **校验**：`python3 scripts/relation_validate.py --relations ... --input /input --nodes ... --out /app/output/relation_audit.json`
   执行受控词表（允许案例扩展）、voice 必填、证据结构、**引文逐字命中**
   （`scripts/quote_check.py` 的鲁棒归一化匹配）、比较约束、数值作用域、
   cited-background 拒用等规则；有错误先修再继续。
4. **条件 lint**：`python3 scripts/condition_lint.py ...`
   缺 metric/basis 或 comparator 的比较 → `uncertain`；缺单位/作用域的
   数值 → 降级为 `unscoped_value_note`；条件缺失 → `partial`。
   **只降级，不补造。**
5. **冲突检测**：`python3 scripts/conflict_detect.py ...`
   K1 数值冲突 / K2 极性·方向冲突全部保留，边标 `in_conflict=true`，
   写入 `/app/output/conflicts.json`。
6. **建图**：`python3 scripts/graph_build.py --nodes ... --relations ... --merges ... --outdir /app/output`
   产出 `graph.json` / `graph.jsonl` / `merge_report.json`
   （跨篇合并与不合并决定显式记录依据）。
7. **查询**：`python3 scripts/query_run.py --graph /app/output/graph.jsonl --queries ... --out /app/output/queries.json`
   确定性执行 ≥3 个查询（DSL 见 `references/query-dsl.md`），
   每个结果都是带逐字证据的结果子图；无直接关系时诚实回答
   `no_direct_relation` 并附共现记录。
8. **预览**：`python3 scripts/graph_preview.py --graph ... --outdir /app/output`
   产出 `graph.dot`、`graph.svg`（纯 stdlib 生成）、中文可读
   `graph_preview.md`（冲突红色、背景转述虚线）。
9. **组装**：`python3 scripts/assemble.py --case /input/case.json --outdir /app/output`
   生成最终 `result.json`：动态镜像 output_contract 全部键，
   汇集 lint 降级、冲突与空结果查询到 `uncertainty`。

## 异常处理（Exception handling）

- 材料缺失/损坏：在 `result.json` 记 `partial` 并点名缺失对象；
  语料按 material.json 索引加载，缺失文件跳过并记录。
- 引文不匹配：校验器 R5 判错；要么回到原文取逐字短引，要么删除该边
  并在 uncertainty 说明，**不得改写引文凑匹配**。
- 同段冲突表述：两条都建边并触发冲突检测，不仲裁。
- 查询无结果：如实返回空子图与原因；共现不等于关系。
- 同名实体：merge_decisions.json 中显式记录不合并理由（如 TransB 与
  TransB-ft），不自动合并、也不强迫每个别名合并。

## 最小示例（SYNTHETIC —— 非平台案例，非证据）

`examples/minimal-example.md` + `examples/synthetic-case/`：两篇合成论文，
含直接条件化比较（TransA/DistilT 各自在 LowMT-100/BLEU/low-resource 下
优于 TransB）、一条只作背景转述的引用（TransB 在 WMT 的 41.2 BLEU，
`cited-background`，永不当一手证据）、一处表面冲突（29.8 vs 30.5，
全部保留）与一处不合并（TransB-ft）。运行
`python3 scripts/run_selftest.py --bundle .` 真实执行完整流水线与
负例测试（不匹配引文、无指标全局比较、cited voice 拒用、冲突标记），
产出 9 节点 / 9 边 / 4 个真实执行查询，18/18 检查通过，
报告见 `examples/synthetic-case/output/selftest_report.json`。

## 依赖与限制（Requirements & limitations）

Python 3.9+ 标准库，无第三方依赖、无二进制、无符号链接。
详细边界（脚本只校验结构与证据可回查、不判科学真伪；引文匹配是鲁棒
子串匹配；条件签名冲突检测的局限等）见 `references/limitations.md`。
