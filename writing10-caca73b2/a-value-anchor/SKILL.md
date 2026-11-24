---
name: value-anchor-rd
description: >-
  本 Skill 面向"结果与讨论"章节写作中的上游数据真实性问题：先由确定性脚本扫描随案材料（表格、统计输出、图注文本）构建机器可读的数值台账（values.json），撰写正文时每个数字必须携带台账锚点 [Vnn]，再由审计脚本逐句核对"数字—锚点—台账值"三者一致，从而杜绝凭肉眼读图猜数与无来源数字，并保证每个数值可回溯至具体文件、行或表格行列。Use when writing or auditing Results/Discussion sections that must be anchored to verifiable numeric evidence from supplied research materials.
---

# value-anchor-rd：数值台账与正文数字锚定审计

## 解决的问题

基础代理在撰写结果与讨论章节时的典型失败模式是"凭肉眼读图猜数"：从位图图表上估读数值并当作精确值写入正文，或直接生成没有任何来源的数字、P 值与样本量。此类错误无法被事后人工快速核验，直接损害章节的可信度。本 Skill 将数值的进入通道收敛为一条可机器审计的链路：材料 → 数值台账 → 带锚点的正文 → 机器审计，使"读得准"与"核得了"成为强制约束而非写作习惯。

## 何时使用

- 任务要求依据随案提供的研究材料（数据表、统计软件输出、图注文本）撰写或修订结果与讨论章节。
- 交付物中的数值必须可回溯、可审计，或评估方强调数值真实性。
- 需要将多个来源（表、统计输出、图注）的数值统一登记并交叉核对。

## 何时不适用

- 材料仅为位图图像且无任何文字层、又无配套数据表时：本 Skill 不提供图像数字化能力，此时应仅作方向性描述并在 uncertainty 中声明，不得估读后冒充精确值。
- 纯文献综述、无原始数值材料的写作任务。
- 需要领域知识判断统计方法适用性的任务（本 Skill 只做数值一致性审计，不判断方法学对错）。

## 运行契约

1. 必须实际读取 `/input/case.json` 与 `/input/task.md` 的内容，不得按文件名猜测任务要求；`case_id` 在 result.json 中原样保留，不做任何改写。
2. 中间产物（values.json、values_report.md、文稿草稿、audit_report.md 等）一律写入 `/app/work`；最终交付物与 result.json 写入 `/app/output`。
3. result.json 必须包含 `case_id` 以及 case.json 中 `output_contract` 列出的全部键。标准键为：`deliverable`（可编辑目标文稿/结构化产物）、`preserved_facts`（不可凭空改变的数字、条件、术语、来源）、`evidence_map`（关键论断到来源定位的映射）、`change_log`（修改动作、原因、人工确认项、未解决问题）；另须含诚实的 `status`、`sources`、`uncertainty` 字段。
4. 诚实 partial 原则：凡存在未决 gap（材料缺失、数值冲突未解、锚定审计未通过），`status` 只能是 `partial`（或失败时 `failed`），不得标注 `complete`；先保存诚实的部分结果，再在预算内增量改进。

## 依赖

- Python >= 3.9，仅标准库（argparse、csv、json、re、os、sys、datetime）。
- 可选：系统 `pdftotext`（poppler）。仅当材料含 PDF 且需提取图注/表格文字层时用于预转换；缺失时跳过 PDF 并在 result.json 的 uncertainty 与台账 skipped 段中声明，流程降级不中断。

## 工作流（严格按序）

- **步骤 0　读任务建工作区**：读取 `/input/case.json` 与 `/input/task.md`，逐字抄下 `output_contract` 的全部键名；在 `/app/work` 建立工作目录。若材料含 PDF 且系统有 `pdftotext`，先将 PDF 文本层导出为 .txt 放入工作区（不改动 /input）。
- **步骤 1　落骨架**：运行 `python3 scripts/result_contract.py init --case /input/case.json --out /app/work/result.json`，生成含全部契约键、`status="partial"` 的骨架，随后每完成一个阶段就地更新。
- **步骤 2　建台账**：运行 `python3 scripts/ingest_values.py --materials <材料目录> --out /app/work/values.json --report /app/work/values_report.md`。逐条阅读 values_report.md，确认 skipped 段中每个文件的跳过原因可接受。
- **步骤 3　精读台账与材料**：对照台账回读原始材料，理解每个数值的语境（组别、单位、误差类型、检验方法）；必要时用 `pdftotext -f -l` 定位 PDF 图注页复核。发现冲突或缺失时按异常处理表登记，不得擅自取舍。
- **步骤 4　撰写带锚点的正文**：按 references/writing-from-ledger.md 的规则撰写结果段与讨论段；每个进入正文的数字必须在同句携带 `[Vnn]` 锚点；读数优先级、误差类型、语气强度规则见下。
- **步骤 5　机器审计**：运行 `python3 scripts/anchor_audit.py --manuscript <文稿> --ledger /app/work/values.json --tol 0.02 --report /app/work/audit_report.md`。审计 FAIL 必须修复文稿或台账后重审，不得绕过、不得删除锚点凑数、不得放宽 tol 掩盖错误。
- **步骤 6　终检组装**：填写 result.json 全部契约键，运行 `python3 scripts/result_contract.py check --case /input/case.json --result /app/output/result.json --output-dir /app/output`。check PASS 后方可交付；FAIL 按打印原因逐项修复。

## 读数优先级规则

1. 表格/统计输出中的文字值（confidence=high）——优先采用。
2. 图上的文字标注值（图注、图内标签）——次之，注意区分标注值与坐标刻度。
3. 数字化估读值——仅在前两类缺失时允许，正文必须写"约"并在台账记 confidence=low。
4. 方向性描述（"升高""降低"）——无任何数值来源时只允许方向性表述。
5. gap——方向也无法确定时留空并记入 uncertainty，不得编造。

同一数值多来源冲突时，以优先级高者为准，冲突本身记入 change_log 的未解决问题。

## 红线

- 不编造任何数值、P 值、样本量 n、文献条目；没有来源的内容不得进入正文。
- SD、SEM、95% CI 三者含义不同，不得互换、不得混写；误差棒含义材料未注明时，正文写"误差棒含义未注明"。
- 无统计检验支撑的组间比较不得使用"显著"及其同义强表述；有检验支撑时按 references/figure-reading.md 的模板转写统计量。
- 无台账记录的数字不得进入正文；审计 FAIL 未修复不得交付。
- 不得修改 /input 下任何文件；不得虚构脚本输出，result.json 中引用的审计结论必须来自真实运行。

## 异常处理表

| 异常 | 处理动作 |
|------|----------|
| 材料缺失（清单列出的文件不存在或为空） | 台账 skipped 段登记；正文相应论断降级为方向性描述或删除；uncertainty 声明；status 保持 partial |
| 表格解析失败（乱码、编码错误、非 UTF-8） | 尝试 utf-8-sig 重读；仍失败则 skipped 登记并降级，绝不崩溃中断 |
| 数值冲突（表与统计输出不一致、图注与表不一致） | 正文采用读数优先级高者；冲突双方数值、来源、取舍理由记入 change_log 未解决问题；uncertainty 声明 |
| 估读置信度低（仅图像来源、刻度模糊） | 写"约 X"；台账 confidence=low；语气降为方向性表述；列入人工确认项 |
| 锚定审计 FAIL | 定位 FAIL 行号，核对台账值与正文数字；属笔误则改正文，属台账错漏则回步骤 2/3 修正台账；修复后重审至 PASS |
| PDF 无文字层且无 pdftotext | 该 PDF 数值整体视为不可得；正文仅作方向性描述；uncertainty 声明降级原因 |

## 自查方法

交付前依次确认：result_contract.py check 输出 PASS；anchor_audit.py 输出 PASS 且 fail=0；values_report.md 的 skipped 段每项均有对应 uncertainty 声明；result.json 中 status 与实际完成度一致；change_log 含全部人工确认项与未解决问题。示例见 examples/minimal_example.md，其中包含端到端真实运行记录与阴性测试。

## 限制

- 本 Skill 不从位图图像中数字化取数；图像仅支持方向性解读。
- 台账正则覆盖常见统计量写法（p、t、F、r、n、mean ± SD、95% CI、alpha），不覆盖全部统计软件输出格式；未识别格式会进入 skipped 或被遗漏，需步骤 3 人工精读兜底。
- 审计只验证"数字与台账一致"，不验证统计方法适用性、不验证结论的科学合理性。
- 表格解析假定规则的二维表；合并单元格、多级表头的复杂表格需人工转写为简单 CSV 后再扫描。
