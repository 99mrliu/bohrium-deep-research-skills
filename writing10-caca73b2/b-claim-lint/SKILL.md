---
name: claim-calibration-lint
description: 本 Skill 对中文或英文论文「结果与讨论」章节草稿进行确定性的静态语言审计：逐句扫描因果越界（把相关写成因果）、无检验的「显著」表述、结果段混入解释、讨论段引入未报告的新数据、幅度夸大、趋势无支撑、局限缺失与图表流水账等八类违规，按行号给出具体改写建议，并以 lint 是否通过（或显式豁免）作为定稿门禁，保证结果段只陈述观察事实、讨论段承担解释与文献对照，且语气强度与证据强度匹配。Use when drafting, revising, or finalizing the Results and Discussion sections of a Chinese or English research manuscript and you need a deterministic claim-calibration gate before submission.
---

# claim-calibration-lint：结果与讨论章节语言校准审计

## 解决的问题

基础写作代理在撰写结果与讨论章节时存在四类系统性偏差：其一，将相关关系表述为因果关系（如滥用「导致」「证明」「demonstrate」）；其二，在没有任何统计检验的情况下使用「显著」「significantly」；其三，结果段与讨论段互相顶替——解释、机制推测、文献对照混入结果段，或讨论段抛出结果段从未报告的新数据；其四，把微小波动夸大为「大幅改善」「急剧上升」。本 Skill 以显式规则包对草稿逐句进行确定性扫描，报告违规的行号、句子摘录与改写模板，并以「lint 通过或全部豁免」作为定稿前置条件，使「说得住」与「分得清」成为可检查、可复跑的工程约束。

## 何时使用 / 不适用

适用：

- 依据给定研究材料起草或修订结果与讨论章节时，作为定稿前的强制审计环节；
- 评审已有草稿的语言校准质量，定位因果、显著性、分节与语气问题；
- 草稿缺少分节标题时，先用 `section_split.py` 生成重组骨架再审计。

不适用：

- 不替代统计判断：本 Skill 只检查「表述是否有支撑标记」，不验证 p 值本身的正确性；
- 不适用于方法、引言等其他章节的专门审计（规则未覆盖其语体）；
- 非论文语体（新闻稿、科普文）的规则阈值未必合适。

## 运行契约

- 运行环境以实际挂载为准：输入为 `/input/case.json`、`/input/task.md` 及真实研究材料；工作目录为 `/app/work`；最终交付物与 `result.json` 置于 `/app/output`。
- `result.json` 必须包含：`case_id`（与 case.json 原样一致）、case.json 中 `output_contract` 声明的全部键（标准键为 `deliverable`、`preserved_facts`、`evidence_map`、`change_log`），以及如实填写的 `status`、`sources`、`uncertainty`。
- 若 lint 复检未通过且存在未豁免违规，则 `status` 只能为 `partial`，并在 `uncertainty` 中说明残留违规；不得在有未豁免 error 的情况下报告 `success`。
- 预算有限时应尽早落盘诚实的部分结果：先 `result_contract.py init` 写骨架，再随工作推进填充。

## 依赖

- Python >= 3.9，仅使用标准库（`argparse`、`re`、`json`、`sys`）。三个脚本均支持 `--help`，失败时以非零退出码返回。

## 工作流（按序执行）

- 步骤 0：读取 `/input/case.json` 与 `/input/task.md`，逐字抄下 `output_contract` 的全部键名与 `case_id`，作为后续组装的依据。
- 步骤 1：运行 `python3 scripts/result_contract.py init --case /input/case.json --out /app/output/result.json`，生成契约骨架（`status=partial`）。
- 步骤 2：依据研究材料起草结果段与讨论段（写入 `/app/work/draft.md`）；所有数值必须来自材料，不得凭记忆补数；结果段只写观察事实，解释与文献对照只放讨论段。若素材草稿无分节标题，先运行 `section_split.py` 预分节并人工复核。
- 步骤 3：运行 `python3 scripts/claim_lint.py --draft /app/work/draft.md --out /app/work/lint_report` 进行全量扫描，阅读报告中的行号与改写建议。
- 步骤 4：逐条修复违规；确属误报或有意保留者，使用 `--waive "规则号:理由"` 显式豁免，理由必须具体，并把该豁免写入 `change_log`。
- 步骤 5：复检通过后（退出码 0），组装 `result.json`（deliverable 指向终稿，preserved_facts 抄录与材料一致的关键数值，evidence_map 建立表述到材料出处的映射，change_log 记录全部修改与豁免），运行 `python3 scripts/result_contract.py check --case /input/case.json --result /app/output/result.json`，确认 PASS。

## 规则总表

| 规则 | 名称 | 严重级 | 触发条件（概要） | 处置建议 |
| --- | --- | --- | --- | --- |
| R01 | 因果越界 | error | 句子含因果动词（导致/促使/引起/证明/证实/决定了/demonstrate/prove/cause/drive），全稿无有效随机或干预设计标记，且句内无对冲语（提示/可能/suggest 等） | 改写为「相关」「提示」级表述；「未随机化」等被否定的标记不算数 |
| R02 | 无检验显著 | error | 句子含「显著/significant(ly)」，同句及同段均无 p 值、置信区间或检验统计量；否定形式（不显著/not significant）不触发 | 补检验结果，或改为「较高/较低」等描述性表述；缺检验就降语气，不得编造 p 值 |
| R03 | 结果段混入解释 | warn | 结果节内句子含解释标记（表明……机制/可能是由于/其原因/与既往研究一致/这提示我们等） | 移至讨论段 |
| R04 | 讨论段新数据 | error | 讨论节内出现带单位的数值词，且该数值从未在结果节文本中出现 | 先在结果段报告，再入讨论 |
| R05 | 幅度夸大 | warn | 幅度词（大幅/显著改善/急剧/dramatic/substantial）所在句无效应量数字（%、倍、fold） | 同句补效应量，或改中性表述 |
| R06 | 趋势无支撑 | warn | 趋势/剂量依赖表述（趋势/随……升高/dose-dependent），同句同段无趋势检验或相关系数 r，且无「未达显著/未进行趋势检验」类边界对冲 | 补检验或加边界对冲 |
| R07 | 局限缺失 | warn | 存在讨论节，但全稿无「局限/不足/limitation」表述 | 讨论段末增设局限段落 |
| R08 | 流水账 | info | 结果节单段图表引用超过 4 处且段首无分组主题句 | 段首补主题句，按主线分组叙述 |

各规则的原理、正例反例、豁免条件与误报处理详见 `references/lint-rules.md`；推断强度词表与有边界写法模板见 `references/inference-lexicon.md`。

## 红线

- 不得通过删除不利结果来消除违规；不利结果必须保留并如实陈述。
- 豁免必须给出具体理由，豁免条目连同理由必须写入 `change_log`；无理由的豁免工具拒绝接受。
- 不得编造 p 值或统计量来满足「显著」规则；材料中没有检验时，只能降低语气强度（如改为「较高」「提示」）。
- 不得修改材料中的数值以迎合行文；草稿数值与材料不一致属于事实性错误，不属于可豁免项。

## 异常处理

| 异常情形 | 降级策略 |
| --- | --- |
| 中英文混写 | 规则包同时维护中英文模式，混写草稿照常逐句扫描；英文句切分避开小数点与 Fig. 等缩写 |
| 草稿无分节标题 | 报告中标注降级警告，R03/R04/R07/R08 自动跳过；先用 `section_split.py` 生成重组骨架并人工复核后再全量审计 |
| 材料无统计输出 | R02 触发的句子一律改为描述性语气，禁止编造检验；在 `uncertainty` 中说明「材料未提供统计检验」 |
| 组合标题（如「结果与讨论」同节） | 该节视为 combined：R03 不适用，R04 以全节文本为结果语料，R07 照常检查 |
| 豁免规则号拼写错误或理由为空 | 工具拒绝启动并以退出码 2 报错 |

## 限制

- 规则是保守启发式，存在误报。典型误报：讨论段局限句中的样本量数字触发 R04（样本量来自方法节而非结果节）；固定术语如「显著性水平」触发 R02。处理流程：确认误报后使用 `--waive "规则号:具体理由"` 豁免并写入 `change_log`，不得为消除误报而改写材料事实。
- R01 的设计标记检查只看草稿文本：若研究确为随机设计但草稿未写明，请在草稿中明示设计，而非直接豁免。
- 本 Skill 不验证数值与材料的一致性（该职责由 evidence_map 的人工核对承担），也不评估论证的学术质量。
