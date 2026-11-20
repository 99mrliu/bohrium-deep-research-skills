---
name: patent-number-family-resolver
description: 以确定性脚本管线完成专利号定位、著录字段抽取与同族归并。当任务给出公开号、申请号、授权号或优先权号需要定位专利、规范号码格式、从 USPTO/WO/EP 传真件抽取首页著录项、或按简单族/扩展族口径归并同族时使用；兼容 /input/case.json + task.md 的 Harbor 运行契约，也适用于任何专利号码解析与族关系核对任务。
---

# 专利号定位与同族归并确定性管线（patent-number-family-resolver）

## 用途与适用条件

把"号码规范化 → 语料匹配 → 传真字段抽取 → 同族归并"做成**模型之外的确定性脚本管线**：Agent 只负责编排、解释与写作，所有号码解析、匹配、归并均由脚本完成并可被他人按记录复跑。

适用：号码类检索（公开号/申请号/授权号/优先权号定位）、USPTO/WO/EP 传真首页著录字段抽取、简单族与扩展族双口径归并、OCR 粘连号码的合规处置。

不适用：侵权判定、自由实施分析、专利价值评估；本 Skill 不输出法律意见。

## 运行时契约（必须遵守）

1. 先读 `/input/case.json` 与 `/input/task.md`，提取 `case_id`、查询号码/主题、`output_contract`。**读真实文件内容**，不按文件名标签臆测。
2. 工作文件放 `/app/work`；最终交付放 `/app/output/result.json`，必须含 `case_id`、诚实的 `status`、`sources`、`uncertainty`，并**镜像 `output_contract` 的全部字段**。
3. 预算有限（约 64 次模型请求 / 900 秒）：**先跑通主管线落盘诚实的 partial 结果，再迭代改进**；不要把时间花在逐条手工阅读上，重活全部交给脚本。
4. 绝不编造号码、族关系或法律状态；解析不出的内容保留原文并写入 `uncertainty`。

## 调用方式（按顺序执行）

```bash
S=/skills/weekly-skill/scripts   # 或本 SKILL.md 所在目录的 scripts/

# 0. 落盘骨架（诚实 partial，含 case_id 与契约镜像；随后每次改进都重写它）
python3 $S/scaffold_result.py --case /input/case.json --out /app/output --status partial

# 1. 建号码索引（语料根目录按实际位置给，常见为 /input 与 /app/work）
python3 $S/scan_corpus.py index --roots /input /app/work --out /app/work/num_index.json

# 2. 按查询号匹配（号码来自 case.json / task.md；多个号码一次给全）
python3 $S/scan_corpus.py query --index /app/work/num_index.json \
    --numbers "US10293847B2" "WO2019/123456" --out /app/work/query_hits.json

# 3. 对语料中的传真 PDF 抽取首页著录字段（逐件执行）
python3 $S/extract_facsimile.py --pdf /input/<facsimile>.pdf --out /app/work/fields_<n>.json
#    若 pdftotext 失败：先用 OCR/pdf 渲染工具产出文本，再 --text <txt> 走同一管线

# 4. 同族归并（records JSON 由第 2/3 步结果汇总而成，格式见 templates/result_fields.md）
python3 $S/merge_family.py --records /app/work/records.json --out /app/work/family.json

# 5. 汇总填充并重写 result.json（fill.json 汇总 candidates/families/sources 等）
python3 $S/scaffold_result.py --case /input/case.json --out /app/output \
    --fill /app/work/fill.json --status ok   # 未完成部分保持 partial 并写明界限
```

## 输出（/app/output/result.json）

`case_id`、`status`（ok/partial/failed）、`candidates`（候选记录，每条带规范化键与定位）、`families`（simple/extended 双口径 + scope_note）、`extracted_fields`（传真著录字段 + evidence_events）、`evidence_records`（file+locator+原文摘录）、`sources`（文件名/库名/查询日期）、`uncertainty`、`change_records`、`output_contract`（镜像）。字段口径见 `templates/result_fields.md`。

## 关键方法

1. **号码规范化**（`scripts/patent_numbers.py`，规则人读版见 `rules/number_formats.md`）：去分隔符后按模式表匹配 US/WO/EP/CN/JP/KR 的公开/授权/申请号；命中多个模式时给出歧义警告并列出备选解释，**不静默二选一**；非法号码返回 `ok=false`，不猜测。
2. **OCR 粘连处置**（规则见 `rules/ocr_boundary.md`）：仅在"唯一可行边界"才拆分粘连号码并记录 `ocr_split` 事件；多解或无解一律保留原样 + 警告，交人工核对原文影像。WO 合并 OCR 的边界保留原样呈现。
3. **传真字段抽取**（`scripts/extract_facsimile.py`）：pdftotext -layout → 按 INID 码切段；申请号无国别码时按文献国别回退并记录 `cc_fallback` 事件；日期解析为 ISO，失败保留原文；重复 INID、无法解析字段全部入 `evidence_events`。
4. **双口径同族归并**（`scripts/merge_family.py`，口径定义见 `rules/family_scope.md`）：简单族 = 优先权集合完全相同；扩展族 = 共享至少一项优先权的连通分量；两口径并列输出并标注。无优先权的记录单列并告警；结果**仅基于观察到的链接**，不得声明完整同族或等效权利要求范围。
5. **法律状态纪律**：本管线不核验法律状态；凡涉及状态，一律标注"官方登记未核验（查询日期：当天）"，详见 `rules/family_scope.md` 末节。

## 案例路由

| 案例类型 | 走法 |
|-|-|
| 号码定位/族归并（本方向主场景） | 主管线 0→5 |
| 技术主题检索 | 降级模式：`scan_corpus.py query --keywords ...` 做字面匹配召回，逐条命中附定位；在 `uncertainty` 明确标注"无语义扩展、无分类号组合，方法局限"，再用主管线处理命中记录的号码与族 |
| 权利要求/法律状态 | 只做字段级事实摘录（INID 字段 + 原文摘录 + 定位）；权利要求版本以来源定位呈现，不做范围解释；法律状态一律标注未核验 |

## 异常处理

| 情况 | 处置 |
|-|-|
| 号码非法/不识 | `ok=false` + 警告，不猜测；写入 uncertainty |
| 裸 8 位 US 号等歧义格式 | 给出主解释 + alternatives + 歧义警告，需人工核对著录项 |
| 语料目录为空 | exit 2，`warnings` 说明；result.json 保持 partial |
| 查询零命中 | 正常交付，标注零命中与已扫描范围；不补造候选 |
| 同序号不同种类号码（公开↔授权↔申请） | 列入 `related_hits` 并提示以著录项为准 |
| pdftotext 缺失/失败 | exit 2 + 说明；改用 OCR 工具产文本后 `--text` 重入管线 |
| OCR 粘连多解/无解 | 保留原样 + 警告事件；禁止猜测拆分 |
| 优先权缺失 | 记录单列，族归属不确定，warning 明示"非完整同族" |
| 同号不同题名等字段冲突 | 双方 locator 保留，列入 conflicts 与 uncertainty |
| 法律状态被问到 | 标注"官方登记未核验 + 查询日期"，不引用转载页 |

## 自查方法

交付前运行 `python3 scripts/selfcheck.py`（25 项断言，含正例全链路与负例拦截），须 exit 0。再人工确认：每条候选都有 `file+locator`；`status` 与实际完成度一致；`output_contract` 字段无遗漏（未填充项已列入 uncertainty）。

## 最小调用示例

见 `examples/example_walkthrough.md`（合成玩具语料，仅说明接口，**示例输出为示意，非正式案例结果**）。
