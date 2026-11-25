---
name: version-chain-lifecycle
description: 文献实体生命周期管理 Skill。把同一研究成果的预印本→正式发表→修订版→勘误/撤稿声明识别为一条版本链（version chain），裁决每条链的当前生命周期状态（preprint_only / published / revised / corrected / expression_of_concern / retracted），并把窗口内变化分类为 new_work / version_update / retraction_notice / correction_notice 四种预警语义：预印本与正式版不重复预警，撤稿最高优先级且不可被去重吞掉，每条裁决带可回放证据（文件名+JSON 指针）。不做窗口调度、提醒投递频率控制、失败重试、质量打分、源数据哈希审计。
---

# version-chain-lifecycle（文献实体生命周期管理）

## 适用场景与边界

适用：跟踪窗口内的题录快照（Crossref / Europe PMC / arXiv / 出版商 API 响应的
本地 JSON 固化件），需要回答"这些记录里，哪些是真正的新成果、哪些只是已有
成果的版本推进、哪些是撤稿/勘误事件"的场景。

核心语义：

- **版本链**：同一研究成果的全部实体形态（预印本各版本、正式发表版、修订版、
  撤稿/勘误/关注声明）合并为一条链，链是预警的最小单位。
- **不重复预警**：一条链在窗口内至多产出一条预警。预印本随后被正式接收，
  是 `version_update` 而不是第二个 `new_work`。
- **撤稿优先**：链内出现撤稿信号时，链状态为 `retracted`，预警
  `retraction_notice`，优先级 `critical`，排在所有预警之前，任何去重/合并
  逻辑都不得吞掉它。
- **可回放**：每条状态裁决、每条链接决策、每条预警都带 locator
  （材料文件相对路径 + RFC 6901 风格 JSON 指针），可逐条回到原始快照核对。

明确**不做**（这些方向由其他 Skill 负责，此处不重复实现）：
窗口调度与补抓、提醒投递频率控制/合并抑制、失败重试与幂等导入、结果质量
打分、源数据哈希与完整性审计。

## 运行契约

- 输入：`/input/case.json` 与 `/input/task.md`。
  - `case.json` 至少含 `case_id`、`materials_dir`（或默认 `materials`）、
    `output_contract`（结果必须覆盖的字段名列表）、可选 `window`。
- 材料定位：**不假设固定布局**。用 `find` / `os.walk` 在 case 目录及
  `materials_dir` 下递归定位 `*.json` 快照，再按文件名提示与结构嗅探
  （`message.items` → Crossref，`resultList.result` → Europe PMC，
  `feed.entry` / 顶层 list / `entries` → arXiv 风格）识别来源。找不到材料
  时诚实降级，不得猜测路径以外的内容。
- 工作目录：`/app/work`（中间产物：records.json、chains.json、alerts.json）。
- 最终输出：`/app/output/result.json`，必须包含 `case_id` 与
  `output_contract` 列出的**全部字段**；任何字段无法填充时补 `null` 并把
  `status` 降级为 `"partial"`。绝不编造文献、DOI、元数据或检索结果。

## 编号工作流程

确定性逻辑全部交给 `scripts/` 下的脚本完成，模型只做复核与写作
（任务复述、异常解释、notes 措辞），不得凭印象手写文献事实。

1. **读取 case**：解析 `/input/case.json`，取 `case_id`、`materials_dir`、
   `output_contract`、`window`；字段缺失时记入 notes 并继续。
2. **定位与抽取**：运行 `scripts/common.py` 的 `extract_records`（或参考
   `scripts/run_minimal_example.py` 的主流程），得到统一题录记录列表与
   材料异常清单。空材料 → chains/alerts 为空数组、如实写 notes。
3. **版本链构建**：`scripts/chain_link.py` 按 R1（DOI relation 字段）→
   R2（update-to）→ R3（arXiv id+版本号）→ R4（标题归一化+第一作者后备，
   confidence=low）合并记录为链，每条决策落证据。
4. **生命周期裁决与预警分类**：`scripts/lifecycle.py` 对每条链裁决状态并
   产出至多一条预警；撤稿信号永远优先；元数据贫乏的链进入 `unresolved`。
5. **装配结果**：`scripts/assemble_result.py` 强制校验 `output_contract`
   字段齐全，缺失补 `null` 且 `status=partial`；存在 `unresolved` 或材料
   异常时同样降级。
6. **模型复核**：对照 `references/lifecycle-state-machine.md` 与
   `references/retraction-correction-signals.md` 抽查若干链的裁决与证据，
   确认无重复预警、撤稿置顶，然后撰写 notes 中的自然语言摘要。
7. **写出**：`/app/output/result.json`（UTF-8、`ensure_ascii=False`）。

端到端示例（在 bundle 根目录）：

```bash
python3 scripts/run_minimal_example.py
```

## 异常处理（诚实降级）

- **空材料目录 / 无 JSON**：chains、alerts 为空数组，notes 说明，
  status 视 contract 填充情况定为 partial。
- **字段缺失**（无 DOI、无标题、无作者）：不强行成链；记录进入
  `unresolved` 并注明原因，status 降为 `partial`。
- **版本关系缺失**：仅有标题+第一作者相似时按 R4 低置信链接，证据中
  标注 `confidence=low`，不得表述为确定同一成果。
- **布局无法识别**：文件记入 `material_anomalies`，不静默丢弃。
- **contract 字段无法填充**：补 `null`，status 降为 `partial`。

## 输出契约（result.json）

| 字段 | 含义 |
| --- | --- |
| `case_id` | 来自 case.json |
| `status` | `complete` / `partial` |
| `window` | 跟踪窗口（原样透传） |
| `chains` | 版本链列表：chain_id、members、lifecycle_state、state_evidence(locator)、representative_title/locator、link_decisions、signals |
| `alerts` | 预警列表：alert_type、priority、chain_id、lifecycle_state、title、reason、evidence；按 critical→high→normal 排序 |
| `unresolved` | 无法可靠成链的记录及原因与 locator |
| `material_anomalies` | 无法识别/读取的材料文件及原因 |
| `notes` | 说明列表（含合成数据声明、降级原因） |

## 自查清单

- [ ] result.json 覆盖 output_contract 全部字段，缺失项为 null 且 status=partial
- [ ] 同一链在 alerts 中至多出现一次；预印本+正式版只产出 version_update
- [ ] 含撤稿信号的链状态为 retracted，预警 retraction_notice/critical 且排在首位
- [ ] 每条链的 state_evidence、每条 link_decision、每条 alert 的 evidence 均含 file+pointer
- [ ] unresolved 与 material_anomalies 如实非空，无静默丢弃
- [ ] notes 含合成数据声明（若 case.synthetic 为 true）
- [ ] 无任何凭模型记忆写入的文献事实
