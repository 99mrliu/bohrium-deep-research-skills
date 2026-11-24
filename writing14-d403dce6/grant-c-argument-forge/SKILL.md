---
name: grant-c-argument-forge
description: 基金申请书“立项依据必要性论证链＋创新点差异化定位＋修辞 Lint”技能，用于把口号式意义堆叠改写为可回检的论证链，并清除“首次/国际领先/填补空白”等不可核验修饰；Use when 需要根据给定科研材料撰写或返修基金申请书的立项依据与创新点章节稿，并对论证质量做机器可回检的自查。
---

# grant-c-argument-forge：论证链先行 · 创新点差异化 · 修辞 Lint

## 1. 运行契约

- 运行时输入为 `/input/case.json` 与 `/input/task.md`；可能存在 `/input/organizer-workorder.json`
  与 `environment/resources.yaml`。`output_contract` 字段必须在运行时从案例自身读取，不得硬编码。
- 在 `/app/work` 下工作，最终产物与可编辑稿件交付到 `/app/output`；其中必须有 `result.json`，
  包含原始 `case_id`、全部 `output_contract` 字段、诚实的 `status`
  （success/partial/unable_to_determine/refused）及原因、`sources`、`uncertainty` 与修改记录。
- 材料清单一出来就先落一份诚实的 partial（写清已完成与缺口），再在预算内就地迭代改进；
  预算上限：64 次模型请求、900 秒、每次响应 16384 tokens（含 reasoning）。
- 只依据实际读到的材料写作（PDF 须实际 pdftotext 读取），绝不按文件名或领域标签补造内容；
  组织方已声明申请人证据缺失时按缺失处理，研究基础只写材料中确有内容，缺失项列入缺口清单。

## 2. 聚焦问题

本技能只解决一个问题：**论证质量**——立项依据必须构成必要性论证链（领域现状 → 关键瓶颈 →
已有进展 → 差距 → 切入点 → 团队凭据 → 时机），而非政策口号堆叠；创新点必须点名具体已有工作
并写清差异、难点与可行性凭据；全文清除“首次/国际领先/填补空白”一类不可核验修饰。

对应基础 Agent 的三类真实失败模式：

1. **口号式意义**：以“符合国家战略”“势在必行”“具有重要意义”替代事实与引文，评审无法核验；
2. **空泛创新**：创新点只说“提出一种新方法”，不点名与谁不同、难在哪、凭什么做得成；
3. **无差异定位**：用“国际领先”“填补空白”自我拔高，替代与具体已有工作的逐项对比。

## 3. 写作方法：论证链先行，评审人视角自检

**论证链先行**：先写链、后成文。不要在成稿后再回头补论证；应先用 `argument_map.py` 的
九类角色（现状/瓶颈/已有进展/差距/切入点/团队凭据/时机/口号/未分类）把材料中的证据卡片
排成链，确认必要角色 现状→瓶颈→差距→切入点 齐备且次序合理，再按链扩写成段落。每个事实类
句子落笔时必须同步写下引文标记；写不出引文的句子要么找到来源，要么降级为切入点类的主观
陈述，要么删除。

**创新点四要件**：每条创新点按 references/innovation_guide.md 的模板写作：新在哪（差异标记）→
与谁不同（点名作者年份/《成果名》/文献编号）→ 为什么难 → 凭什么成（已完成凭据）。先用
`innovation_diff.py generate` 依据材料中梳理出的已有工作清单生成“差异定位表”，逐行填实，
再从表格提炼成创新点条目。

**评审人视角自检**：成稿后把自己当作评审人问四个问题——这件事为什么值得做？别人做到哪一步
（能否指出具体工作）？还差什么（差距是否可核验而非“尚有不足”）？为什么是你们、为什么是
现在（凭据是否区分了已完成与拟开展）？四个问题任一答不出，即对应脚本的一类 error，回到
对应链条环节修补，不得用形容词搪塞。

## 4. 工作流程

1. **读入与落 partial**：读取 `/input/case.json`、`/input/task.md` 及可能的工单文件；登记
   材料清单与 `output_contract`；立即向 `/app/output/result.json` 写入 status=partial 的
   骨架结果，列出材料缺口。
2. **抽取证据卡片**：从材料（PDF 用 pdftotext 实际读取）中抽取可引用事实：数据、方法、
   结论、已有工作（名称/作者/年份/方法/局限）、申请人前期证据；逐条记录来源页码或段落，
   存为 `/app/work/evidence_cards.md`；无法核实来源的标“未核验”。
3. **梳理已有工作清单**：把外部已有工作整理为
   `{"existing_works":[{"name","method","limitation"}]}` 结构（limitation 须为材料原文），
   存 `/app/work/existing_works.json`。
4. **生成并填写差异定位表**：
   `python3 scripts/innovation_diff.py generate /app/work/existing_works.json -o /app/work/diff_table.md`；
   逐行填写“本研究差异/难点/可行性凭据”；填毕运行
   `python3 scripts/innovation_diff.py check /app/work/diff_table.md`，空单元格 error
   （退出码 1）必须补齐后重跑至退出码 0。
5. **搭论证链、写立项依据**：按 references/argument_patterns.md 的范式组织句子角色，
   写成“立项依据”小节初稿；运行
   `python3 scripts/argument_map.py /app/work/proposal_sections.md -o /app/work/am_out`，
   链不完整或事实句引文覆盖率 < 0.8（可用 `--threshold` 调整）时退出码 1，按
   `argument_map.json` 中的缺失角色与未分类句清单修补。
6. **写创新点并全文 Lint**：按差异定位表写成创新点条目；运行
   `python3 scripts/rhetoric_lint.py /app/work/proposal_sections.md -o /app/work/lint_out`，
   按 `lint_report.json` 与 `lint_annotated.txt`（带行号标注）逐条消除 error（L1–L4），
   warning（L5–L6）酌情处理；重跑至退出码 0。
7. **交付**：把通过全部检查的章节稿写入 `/app/output`（满足 output_contract 的可编辑格式），
   附要素对照说明与事实—来源映射；更新 `result.json`：status、sources、uncertainty、
   修改记录、脚本各次运行退出码摘要。

## 5. 事实与来源红线

- 四态标注贯穿全文：**已完成[申请人，有材料证据]**／**外部工作[原论文/既有成果，归外部
  作者]**／**拟开展[本研究计划]**／**待确认[材料缺失需人工确认]**。
- 不新增材料之外的事实；数字、结论、政策口径必须可回溯到材料中的具体位置。
- 引用无法核实的，标注“未核验”，不得假装已核实。
- 差异定位表中“其局限”一栏必须引材料原文（加引号），不得概括拔高别人的缺陷。

## 6. 异常处理表

| 异常 | 处置 |
|---|---|
| PDF 加密/无文本层 | 尝试渲染后 OCR；仍不可读则声明不可读，按 partial 交付并列入缺口 |
| 材料缺失（如无前期成果） | 以【待申请人确认：…】占位，写入缺口清单；绝不虚构凭据 |
| 材料冲突（两处数字不一致） | 两处均保留并标注冲突来源，优先采用更直接支持论断的一处，记录于 uncertainty |
| 超长输入 | 先抽取证据卡片再分节写作；立项依据优先，确保 partial 可先交付 |
| 格式冲突（模板与案例要求不一致） | 以案例 `output_contract` 与 task.md 为准 |
| 七要素清单与默认不同 | 以案例给定清单为准；默认清单：立项依据、科学问题、研究目标、研究内容、技术路线、创新点、研究基础与可行性 |
| 创新点小节标题不含“创新点” | L4 报 error；改用含“创新点”的小节标题，或将该类小节内容并入正式小节 |
| 口号句确有政策依据 | 补引文标记（来源+年份）后 L2 自动豁免；否则删除或改写为事实句 |

## 7. 脚本与资源清单

脚本（Python3 标准库，确定性输出，`--help` 可用，失败退出码非零）：

| 脚本 | 功能 | 退出码 |
|---|---|---|
| `scripts/rhetoric_lint.py` | 章节稿修辞 Lint：L1 禁用词（references/banned_phrases.txt，`--extra` 追加）、L2 无引文口号句、L3 绝对化表述、L4 创新点四要件、L5 修饰词窗口重复（warning）、L6 中英标点混用（warning）；产出 `lint_report.json` 与带行号 `lint_annotated.txt` | 0 通过；1 存在 error；2 用法/IO 错误 |
| `scripts/argument_map.py` | 解析“立项依据”小节为角色句序列，判定必要性链 现状→瓶颈→差距→切入点 完整性与次序，统计事实句引文覆盖率，列出未分类句；产出 `argument_map.json` | 0 链完整且覆盖率达标；1 链不完整或覆盖率 < 阈值（默认 0.8）；2 用法/IO 错误 |
| `scripts/innovation_diff.py` | `generate` 由已有工作清单 JSON 生成差异定位表模板；`check` 校验已填表空单元格/占位符；产出 `innovation_diff_report.json` | 0 成功/通过；1 校验 error；2 用法/IO/JSON 错误 |

资源：`references/banned_phrases.txt`（不可核验修饰词表）、`references/role_cues.md`
（句子角色线索词表与判定优先级，机器可读）、`references/argument_patterns.md`（论证链范式
与 3 组口号版/论证版对照）、`references/innovation_guide.md`（四要件写法与反例）。

最小示例（合成示例，非正式案例结果）见 `examples/`：陷阱版章节稿触发 L1×2、L2×2、L4×1
且论证链缺“差距”，修复版三项检查全部通过；命令、退出码与关键输出的真实运行记录见
`examples/README.md`。

## 8. 版本与维护

- 版本：1.0.0（2026-11）。
- 依赖：Python 3（仅用标准库）；处理 PDF 材料时 pdftotext 可选（缺失时按异常处理表降级）。
- 适用范围：基金申请书（自然科学基金类）立项依据与创新点章节的撰写与返修；角色线索词表
  面向中文科技写作，其他语种需替换 `references/role_cues.md` 与禁用词表。
- 限制：角色分类与口号检测基于线索词启发式，存在误判可能——未分类句清单必须人工过目；
  Lint 通过不等于论证充分，最终判断责任在写作者；脚本不核验引文真伪，只核验引文标记存在性。
- 维护：新增禁用词直接追加 `references/banned_phrases.txt`（一行一个）或用 `--extra` 临时
  追加；调整角色线索词编辑 `references/role_cues.md` 的机器可读块，保持格式不变。
