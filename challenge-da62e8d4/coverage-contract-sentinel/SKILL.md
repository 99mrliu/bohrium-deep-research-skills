---
name: coverage-contract-sentinel
description: 为带 output_contract 的研究/数值答题任务建立需求—证据—字段矩阵，增量产出 result.json，并在交付前做合同、双向覆盖与降级状态机检。适用于 /input/case.json 与 task.md、真实 PDF、多候选数值方法、材料不完整或运行失败场景；不用于纯文学写作或无结构合同任务。
---

# Coverage Contract Sentinel

把正式问题拆成**每一问、每一顶层合同字段、每一要求产物**的可定位证据映射，持续保存 `coverage.json`、`coverage.md`、`result.json` 与 `coverage.svg`。这是交付质量审计，不是 run-supervisor 状态机变体：**不得用本 Skill 执行、调度或重试候选命令**；只登记实际运行产生的日志、哈希和定位信息。

## 何时触发与不触发

触发：存在 `/input/case.json` / `task.md`、`output_contract`、需逐字段交付的研究问答；真实论文/PDF 数值溯源；两个候选数值方法；证据缺失或候选失败需诚实降级。

不触发：纯文学写作、创意改写、无结构合同且无需证据矩阵的普通任务。不要把所有写作机械地 JSON 化。

## 平台契约与边界

- 输入位于 `/input/case.json`、`/input/task.md`（以平台实际挂载为准）。先做三个终端动作：`init` 立即落盘、`register` 每次新增证据/答案落盘、`finalize` 编译和机检。
- 总预算按 **900 秒**规划，优先在开头生成诚实 partial 骨架，之后增量覆盖；不要等到最后一问才保存。失败、超时或中断也必须保留已有部分结果。
- 从 `init` 骨架到 failed/passed final，`result.json` **顶层始终平铺** `case_id`、`status`、`sources`、`uncertainty`、`change_records`、合同要求的答案字段及 `delivery`。绝不要把答案或这些标准字段嵌套进 `output_contract`，也不要只交一个合法空 JSON。每个合同答案字段二选一：实质 `answer_fragment`，或带具体原因及缺失材料/下一步的结构化 `unavailable`。空串、`N/A`、`TODO`、`未知` 等占位不能通过。
- 顶层 `status` 只能是 `success`、`partial`、`unable`、`refused`；本工具按科学状态映射 `complete -> success`、`degraded -> partial`、`unavailable -> unable`（没有科学 refusal 输入时不自动产生 `refused`）。该字段不能替代或改变 `delivery.contract_status`、`delivery.coverage_status`、`delivery.scientific_status` 三轴。合同 PASS 不表示覆盖 complete，更不表示科学成功；科学状态不能被 coverage success 覆盖。缺材料、未运行、任一候选失败或结论部分不可用时，科学状态必须降级（degraded 或 unavailable），并在 notes/答案中说明。
- `sources` 只由已登记的真实 evidence 生成，每项含 `id/path/hash/locator/kind`，其中 `hash` 等于 evidence 的工具计算 SHA256。`uncertainty.scientific_notes`、`uncertainty.unavailable_reasons`、`uncertainty.coverage_gaps` 分别汇总科学限制、字段不可用原因和全部覆盖查漏数组。`change_records` 按 sequence 记录实际成功的 `init`、每批 `register` 和 `finalize`，每项的 `atomic_state` 与当次原子写入的合同/覆盖/科学/顶层状态一致。
- 若用户合同本身也要求 `case_id/status/sources/uncertainty/change_records/delivery`，这些名字由上述标准结果字段满足，不再重复变成答案字段；final exact-key 校验同时允许并要求它们。`output_contract` 仍是保留名，不能作为结果答案字段。
- 组织方合成内容不等于作者原始代码或独立复现；未取得原始数据仓库时必须显式保留 unavailable/限制说明，不能用合成结果冒充作者结果。
- 工具只检查结构、文件、SHA256、引用和 locator 非空。`paper` 等 kind **不等于语义支持**。agent 必须阅读原文，核对数值、单位、上下文、假设和结论，并把语义判断写入 answer fragment / notes。

## 证据登记硬要求

每条 evidence 都有唯一 `id`、真实文件 `path`、工具计算的 `sha256`、非空 `locator`、`kind`、`fields` 和可选 `artifacts`/`command`。kind 只能是 `paper`、`environment`、`parameter`、`run`、`comparison`、`attribution`、`artifact`。

- **论文值必须给页码以及段/表/图定位**：例如 `{page: 7, paragraph: 2, table: "Table 2", row: ...}` 或 `{page: 5, figure: "Fig. 3", panel: "b"}`。PDF 文件只有路径不够；摘录文件也必须保持原 PDF 页码定位。
- 环境、参数、运行分别登记，不相互替代。运行日志 locator 指明日志行段/关键段，`command` 原样记录已执行命令；本工具不执行该命令。
- 比较证据明确两个候选、指标、单位和差异归因；**事前容差**必须在看结果之前登记，不能用事后容差宣布一致。
- 两个候选及差异归因都不能漏。一个失败也要登记失败日志和退出/错误定位，科学状态降级，不得悄悄删除失败候选。
- `required_artifacts` 是正式问题要求的日志、表格、参数记录等语义名称；由 evidence 的 `artifacts` 认领。字段有答案不代表要求产物已交付。

## 增量操作

```bash
python scripts/coverage_contract.py init \
  --case /input/case.json --workdir /path/to/audit
python scripts/coverage_contract.py register requirements \
  --payload requirements.json --workdir /path/to/audit
python scripts/coverage_contract.py register evidence \
  --payload evidence.json --base-dir /path/to/audit --workdir /path/to/audit
python scripts/coverage_contract.py register answers \
  --payload answers.json --workdir /path/to/audit
python scripts/coverage_contract.py finalize --workdir /path/to/audit
```

`init` 支持 list、dict/field mapping 和常见 JSON Schema，只提取顶层必需答案字段并自动补齐标准字段。初见 900 秒任务就先运行它，骨架是 `status=unable`、DRAFT/partial/unavailable 且答案含占位，**占位 finalize 必败**。requirements 由 agent 阅读 `task.md` 后逐问登记，不能由字段名自动生成或略过复合小问。详见 [references/contract-and-evidence.md](references/contract-and-evidence.md)。

每批 `register` 原子替换所有四个文本产物，并把实际操作和状态快照追加到 `change_records`；加 `--with-png` 时若已有 matplotlib，也生成 PNG。每次 finalize 重新核对真实文件和 SHA256，成功或失败都记录 finalize 操作及实际退出码。写失败或 final 失败仍保留最后部分结果；失败 final 会原子写入带具体错误的 `result.json`，返回非零，不得手工改成 PASS。

## 矩阵双向查漏与最终停机检查

`coverage.md` / JSON / preview 同时报告：

1. 无答案字段、unavailable 字段、无证据字段；
2. 无证据 requirement、无证据 required artifact；
3. 无字段 evidence、未被任何 requirement/answer 使用的孤儿 evidence；
4. 未知证据引用、字段标签不匹配、文件丢失或哈希改变。

finalize 前逐项读 `task.md` 回查原文。机检 PASS 只代表所有字段有非空实质回答或具体 unavailable 且 answered field 有证据。若仍有 unavailable、漏问、漏产物、孤儿证据或任何引用问题，coverage 必须 partial；把未闭环项、缺失材料、未运行/失败候选写入交付，而非假 success。

可运行 `examples/minimal/run_example.sh` 查看完整合成示例及缺证据负例；示例生成器生成的日志都明确标为 synthetic，不是真实科学运行。
