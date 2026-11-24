---
name: skill-a-evidence-anchor
description: 学术规范与合规审查中的"原文锚定工程"：当需要对论文/科研材料出具带逐字定位（文件+页码+章节+quote）的审查报告时使用。脚本机械核验每条 finding 的 quote 是否逐字出现在抽取文本的声称页，锚定失败者自动降级 verdict_status=待复核，从根上杜绝"编定位"。适用于 /input/case.json + 论文 PDF/TXT 材料的审查类任务。
---

# skill-a-evidence-anchor：原文锚定工程

## 1. 用途与新增价值
对科研材料做质量/引用/事实/方法/规范审查时，评审要求每条 finding 都能指回原文具体位置
（文件+页码+章节+逐字摘录）。本 skill 的新增价值在于把"定位真实性"从 Agent 自觉变成
**脚本机械保证**：

- `extract_text.py` 把材料（PDF 经 pdftotext，或 TXT/MD 直读）切成带页码与全局偏移的
  `pages.json`，并粗切分常见章节；
- `quote_bind.py` 对每条 finding 的 `location.quote` 做 exact → normalized → 跨页拼接
  三级机械匹配；匹配不上（`match_level=none`）的 finding **自动**把
  `verdict_status` 改为 `待复核` 并追加理由"锚定核验未通过"——编造的页码、凭印象改写
  的 quote 在交付前被强制拦下；
- `audit_skeleton.py` 开工即落合法的 partial `result.json` 骨架，任何时刻中断都有诚实保底。

## 2. 适用条件与不适用情况
**适用**：/input 下有 case.json + 论文（PDF 或纯文本）材料；case 要求逐条 finding 带原文
定位；需要"报出的每个问题真实成立并能指回原文"。

**不适用 / 需配合**：
- 扫描版 PDF（pdftotext 抽出空文本）——本 skill 不做 OCR，应在 uncertainty 中如实说明并
  按 partial 交付；
- 外部事实核验（Crossref/DOI 查证）不是本 skill 重心，脚本只做本地锚定；外部核验结论
  只能记录实际检索到的内容，检索不到标待复核；
- 多文件材料需逐文件各跑一次 extract_text，再按文件分别绑定 findings。

## 3. 运行时契约与路径
- 输入：`/input/case.json`、`/input/task.md`、`/input/<materials>`（如 paper.pdf）；
- 工作区：`/app/work`（中间产物 pages.json、findings 草稿都放这里）；
- 交付：`/app/output/result.json`（必须含 case.json 里 `output_contract.required_fields`
  的全部字段）+ 人读报告；
- 本 skill 安装于 `/skills/weekly-skill`，脚本路径 `/skills/weekly-skill/scripts/*.py`；
- 脚本仅 Python3 标准库、确定性、支持 `--help`、缺键不崩（exit 0 并输出 partial/警告）。

## 4. 工作流（编号步骤，命令可直接复制）

```bash
# 0. 保底先行：从 case.json 生成合法 partial result.json（已存在则不覆盖）
python3 /skills/weekly-skill/scripts/audit_skeleton.py \
  --case /input/case.json --out /app/output/result.json

# 1. 抽取分页（每个材料文件一份 pages.json）
python3 /skills/weekly-skill/scripts/extract_text.py \
  /input/paper.pdf --out /app/work/pages_paper.json
# 若提示缺 pdftotext：把 PDF 文本另存为 .txt 后重跑同一命令，并在 result.json 记 warning

# 2. Agent 读 pages.json 做全部审查面（review facets）的审查，
#    手写 findings 草稿 /app/work/findings_draft.json：
#    每条含 id/type/severity/location{file,page,section,quote}/evidence/suggestion/
#    verdict_status；quote 一律从 pages.json 复制（规则见 references/anchoring_rules.md）

# 3. 机械锚定核验（失败自动降级）
python3 /skills/weekly-skill/scripts/quote_bind.py \
  --pages /app/work/pages_paper.json \
  --findings /app/work/findings_draft.json \
  --out /app/work/findings_bound.json \
  --stats /app/work/anchor_stats.json

# 4. 处理降级：对 downgraded_ids 逐条用 anchor.found_on_pages 修正 page/quote，
#    重跑步骤 3 直至仅剩真正无法定位者（保持 待复核 交付，不得硬改回 确认）

# 5. 汇总：把 findings_bound 写入 result.json 的 findings，anchor_stats 原样附上，
#    覆盖不全的审查面写入 not_reviewed 并说明原因，更新 status 与 change_log
```

## 5. 输出契约（result.json 与 findings 要素）
`result.json`：以 case.json 的 `output_contract.required_fields` 为准，一个不缺；
常见字段 `case_id / status(complete|partial|blocked) / findings / not_reviewed /
uncertainty / sources / change_log`，本 skill 额外附 `anchor_stats`（verified/downgraded
计数与 downgraded_ids）。

每条 finding（与其他 bundle 一致的统一要素）：
`id`、`type`（fact_error / insufficient_evidence / norm_issue / suggestion）、
`severity`（critical/major/minor/info）、`location{file,page,section,quote 逐字}`、
`evidence`（本地规则名/外部来源+实际检索内容）、`suggestion`（可执行）、
`verdict_status`（确认 / 待复核+理由）。本 skill 为每条 finding 追加 `anchor` 对象
（match_level / found_on_pages / cross_page 等机械核验证据）。

## 6. 失败模式与止损表

| 失败模式 | 信号 | 止损 |
| --- | --- | --- |
| pdftotext 缺失/失败 | extract_text 输出 warnings，pages 为空 | 改喂 .txt；不行则在 result.json 记 blocked 面 + partial 交付 |
| 扫描版 PDF | 页文本几乎为空 | 不做 OCR；uncertainty 如实说明，相关面进 not_reviewed |
| 大面积 match_level=none | anchor_stats.downgraded 占比高 | 先怀疑页码口径（物理页 vs 印刷页）或 quote 被改写；逐条用 found_on_pages 修正后重跑 |
| case.json 缺键/坏 JSON | 脚本 warnings | 按默认字段集落骨架，warnings 写进 result.json，继续审查不中断 |
| absence finding 被当确认交付 | quote 为空却标 确认 且无人工复核记录 | 按 anchoring_rules.md 第 4 节补关键词检索+人工确认，否则标待复核 |

## 7. 降级策略（honest partial）
- 任何时候中断：步骤 0 的骨架保证 /app/output/result.json 合法存在，status=partial；
- 材料不可读：对应审查面进 `not_reviewed` 并写原因，status=partial；
- 锚定失败的 finding：保留在 findings 中（verdict_status=待复核+理由），不删除、不美化；
- 外部核验未做/失败：相关 finding 标待复核，uncertainty 写明"未联网/未核验"。

## 8. 预算意识
- 先存 partial 再迭代：开工第一件事跑 audit_skeleton；每完成一个审查面就把 findings
  草稿落盘到 /app/work，再统一跑 quote_bind；
- 机械工作全部交脚本：分页、章节切分、锚定核验、统计都由脚本完成，Agent 只做需要
  判断力的部分（读原文、定类型/严重度、写 suggestion）；
- quote_bind 可反复重跑（幂等、秒级），修 location 的成本远低于一次模型往返；
- 单文件 ≤500KB、产物尽量精简：pages.json 只放 /app/work，交付物只带 findings 与统计。
