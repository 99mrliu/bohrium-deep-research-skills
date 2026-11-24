---
name: grant-e-contract-guard
description: 运行契约与预算鲁棒性守护——合同优先、先落保底 result.json、就地迭代、断点可恢复、异常分类处置。Use when 在 900 秒/64 请求预算下执行基金申请书写作任务，需要保证运行被截断也留下合法 result.json、预算近阈值自动降级保底交付、异常如实记录而非静默失败或编造完成状态。
---

# grant-e-contract-guard：运行契约与预算鲁棒性守护

## 运行契约（先读这段）

- 必读输入：`/input/case.json`、`/input/task.md`；若存在 `/input/organizer-workorder.json` 与 `environment/resources.yaml` 一并读。
- `output_contract` 的字段清单**运行时从 case.json 读取，不得硬编码**；每个案例的清单可能不同。
- 工作目录 `/app/work`；最终产物与可编辑稿件归 `/app/output`，其中必须有 `result.json`。
- `result.json` 必含：原始 `case_id`（逐字符一致）＋ 全部 output_contract 字段 ＋ 诚实 `status`（success/partial/unable_to_determine/refused）＋ `reason`（非 success 时）＋ `sources` ＋ `uncertainty`。
- **材料清单一出来 60 秒内先落 `status: partial` 的合法 `result.json`（保底），再就地迭代改进**；每次改进就地更新并留检查点。
- 预算：64 次模型请求 / 900 秒 / 每次响应 16384 tokens（含 reasoning）。
- 只依据实际读到的材料写作，绝不按文件名或领域标签补造内容；组织方已声明申请人证据缺失时按缺失处理（研究基础只写材料中确有内容，缺失项列缺口）。

## 聚焦问题

可靠体验：预算受限的长材料任务中，基础 Agent 的典型失败模式是——**超时后没有任何产出**、**result.json 缺合同字段**、**异常时静默失败或把 status 编造为 success**。本 Skill 的运行纪律是"合同优先、先落保底、就地迭代"：任何时刻被截断，`/app/output` 里都存在一份合同合法、边界诚实的 `result.json`；预算近阈值时自动降级为"保底交付"（已写部分 + 缺口清单）；异常按分类法处置并如实入账。

## 工作流程

设 `$SKILL=/skills/weekly-skill`（脚本与 references 均在 `$SKILL` 下）。

1. **启动与保底**：读 case/task 与工单；列材料清单。立即运行
   `python3 $SKILL/scripts/contract_probe.py --case /input/case.json --output-dir /app/output --now <当前时间ISO8601>`
   写出保底 `result.json`（status=partial、全部合同字段诚实占位）与 `plan.json`（要素清单＋交付文件计划＋预算分配建议）。
2. **建账**：`python3 $SKILL/scripts/budget_ledger.py init --ledger /app/work/ledger.json --budget-requests 64 --budget-seconds 900`。
3. **首个检查点**：`python3 $SKILL/scripts/checkpoint.py save --stage init --note "保底已落盘" --output-dir /app/output --store /app/work/checkpoints.jsonl --now <当前时间>`。
4. **读材料**（预算约 20% 请求/25% 耗时）：逐个实际读取材料（PDF 用 pdftotext），要点落 `/app/work/notes.md`，来源台账骨架落 `/app/output/sources.md`。每次模型请求后 `budget_ledger.py tick --kind model_request --elapsed <秒>`；本地处理 `tick --kind stage`。
5. **异常处置**：遇异常即写异常描述 JSON（类型见下表），运行
   `python3 $SKILL/scripts/triage.py --input <异常.json> --out /app/work/triage-<n>.json`，
   按输出的 actions 执行占位与缺口登记，并把 `result_json_update` 建议合并进 `result.json`。
6. **成稿**（约 45%/40%）：按 `plan.json` 要素清单逐章写 `/app/output/proposal_draft.md`；每完成一节：就地更新 `result.json`（deliverables/change_record 追加）→ `checkpoint.py save --stage <节名>` → `budget_ledger.py tick`。同步维护 `element_mapping.md`（要素对照说明）。
7. **回检与降级**（约 20%/20%）：tick 返回退出码 2（warn，≥70%）时停止非必要扩写；退出码 3（critical，≥90%）时**立即按 `references/budget_policy.md` 第 4 条保底交付**：未完成章节写【待申请人确认：…】占位并列缺口，result.json 更新为诚实的 partial，存检查点。
8. **交付**：`python3 $SKILL/scripts/contract_probe.py --validate --case /input/case.json --output-dir /app/output`，退出码 0 才可交付；退出码 1 按列出的问题逐条修复后重跑。最后 `checkpoint.py save --stage final`。
9. **断点续跑**：被截断重启后，`checkpoint.py list` 看时间线，必要时 `checkpoint.py restore --stage <名>` 恢复最近快照，从最近完成阶段的下一步继续（不重复已完成工作；脚本幂等、口径一致）。

## 事实与来源红线（四态标注）

- **已完成**[申请人，有材料证据]：材料中确有的申请人工作，可写为既有基础；
- **外部工作**[原论文/既有成果，归外部作者]：引用他人成果必须标明归属，不得写成申请人贡献；
- **拟开展**[本研究计划]：计划内容必须与"已完成"明确区分；
- **待确认**[材料缺失需人工确认]：统一占位 `【待申请人确认：…】` 并进缺口清单。
- 不新增材料之外的事实；引用无法核实的一律标注"未核验"，严禁编造 DOI、页码、文献条目。

## 异常处理表

| 异常类型 | 识别特征 | 处置要点 |
| --- | --- | --- |
| pdf_unreadable | PDF 加密/无文本层，pdftotext 输出空或乱码 | 重试并记录命令；渲染+OCR 或如实声明不可读，章节留占位，按 partial 交付 |
| material_missing | case/task 引用的文件不存在，或组织方声明证据缺失 | 【待申请人确认：请补充…】占位＋缺口清单，禁止编造申请人成果，继续其余章节 |
| material_conflict | 两份材料对同一事实矛盾 | 两说并录、标注来源、不擅自取舍，待申请人确认 |
| oversized_input | 材料超出单次可处理范围 | 切片读取、要点即时落盘、每步记账，未覆盖部分列缺口 |
| format_conflict | 案例格式/要素清单与默认不同 | 以案例 output_contract 与 task.md 为准；无法生成的格式交付可编辑源文件并说明 |
| citation_unverifiable | 论断/引用找不到出处 | 标"未核验"移入 uncertainty，不作为既定事实入正文 |
| budget_exhausted | 账本 warn/critical 或预算耗尽 | 立即执行保底交付动作清单（见 budget_policy.md 第 4 条） |
| 未知类型 | 不在上表 | 保守默认：标待确认＋列缺口＋继续其余部分；不静默失败、不编造完成状态 |

细则见 `references/exception_playbook.md`；`triage.py` 即按该表执行。

## 脚本与资源清单

脚本（Python3 标准库、确定性、`--help` 可用、失败退出码非零）：

| 脚本 | 功能 | 退出码 |
| --- | --- | --- |
| `scripts/contract_probe.py` | 探测：写保底 result.json＋plan.json；`--validate`：合同符合性校验 | 0 成功/通过；1 校验不通过；2 输入或环境错误 |
| `scripts/budget_ledger.py` | `init`/`tick`/`status`：预算账本与降级建议 | 0 正常；2 warn（≥70%）；3 critical（≥90%）；1 错误 |
| `scripts/checkpoint.py` | `save`/`list`/`restore`：检查点与快照恢复 | 0 成功；1 错误 |
| `scripts/triage.py` | 异常分类处置：输入异常 JSON，输出处置动作 JSON | 0 成功（未知类型走保守默认）；1 错误 |

参考资源：`references/runtime_contract.md`（合同全文与诚实 partial 判定）、`references/budget_policy.md`（分阶段预算与降级触发）、`references/exception_playbook.md`（七类异常处置细则）、`references/runbook.md`（启动到交付逐步 runbook）。

最小示例（合成示例，非正式案例结果）：`examples/` 下的 demo-001 案例演示完整生命周期——保底落盘 → 3 次 tick 到 75% 触发 warn（退出码 2）→ triage 处置 material_missing → 两个检查点 → 校验通过（0）；陷阱：删一个合同字段后校验退出码 1 并点名缺失字段，快照恢复后再通过；tick 超 100% 时 critical（退出码 3）。命令与真实输出见 `examples/README.md`。

## 版本与维护

- 版本：1.0.0
- 依赖：Python3 标准库；pdftotext/soffice 为可选外部工具，缺失时按 playbook 诚实降级（声明不可读/不可渲染）。
- 适用范围：预算受限、需保证交付合同合法的基金申请书写作运行守护；不生成实质学术内容本身，而是保证任何时刻的产出合法、诚实、可恢复。
- 限制：预算耗时由调用方估计传入（脚本不读墙钟，保证确定性）；`--validate` 校验合同结构与诚实性要件，不评判学术质量。
