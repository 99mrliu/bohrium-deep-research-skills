---
name: slr-claim-backlink
description: >
  系统性文献综述的论断回链审计 Skill。触发场景：综述正文里的事实、推断与
  不确定论断需要逐条回链到可机器解析的原文位置（span），或需要核验引用片段
  是否为原文逐字子串、论断强度是否越界、证据是否悬空。差异化能力：以 span
  （文件+定位+原文片段）为单位建确定性索引，论断先登记为 claims.jsonl 再写
  正文，脚本机械核验 C1–C7（schema、verbatim 回链、悬空引用、fact 无证据、
  inference 断定词、uncertain 原因、孤儿证据），并生成论断×文献覆盖矩阵与
  冲突证据矩阵；审计不通过的论断不许出厂。边界：机器只保证字面回链与措辞
  边界，论断与证据的语义匹配属模型职责；不替代检索执行、质量评价打分与学术
  审查，这些环节以 references 协议与 result.json 字段承载。
---

# slr-claim-backlink：综述论断回链审计

## 1. 适用场景与边界

**适用**：围绕固定研究问题完成系统性综述时，要求每条综述论断都能回链到
具体文献的具体位置；评测或同行需要按"论断 → span → 原文 quote"逐条复核；
需要区分事实（fact）、推断（inference）、无法确定（uncertain）三类论断并
防止措辞越界；需要呈现冲突证据与研究空白。

**边界**：
- 机器核验仅限字面（quote 是否为 span 的 verbatim 子串、span 是否存在、
  词表是否命中）；**论断与证据语义是否匹配、证据是否足以支撑论断，是模型
  的职责**，必须在 result.json.checks 中如实声明已做语义复核。
- 不替代数据库检索、不替代质量评价的专业判断、不做统计合并（meta 分析）。
- 示例数据（examples/）全为合成示例，不得冒充正式案例结果。

## 2. 运行环境

- Python 3（仅标准库）。脚本位于 `$SKILL/scripts/`。
- 脚本定位兜底（安装路径不确定时）：
  `find / -maxdepth 5 -name "audit_claims.py" -path "*slr-claim-backlink*" 2>/dev/null | head -1`，
  找到后以该文件所在目录的上一级为 `$SKILL`；评测环境通常为
  `/skills/weekly-skill`。
- 退出码约定（全部脚本一致）：**0=通过；2=输入/材料不足（诚实降级，错误码
  E-INPUT）；3=校验失败（发现违反规则，错误码 C1–C7）**。argparse 用法错误
  由 argparse 自身以 exit 2 报出。每个脚本支持 `--help`。
- PDF 现场解析：`pdftotext -layout` 优先；扫描件用 OCR 工具；得到 UTF-8
  文本后再建索引（见 references/localization.md）。

## 3. 工作流程

工作目录 `/app/work`，最终交付 `/app/output/result.json`。一切可确定性做的
（解析、索引、核验、计数、矩阵渲染）交给脚本，模型只做判断、解读与写作。

1. **读案例**：读 `/input/case.json` 与 `/input/task.md`，运行
   `parse_case.py --case /input/case.json --out /app/work/case_summary.json`，
   确认 case_id、研究问题、材料清单与 output_contract。
2. **保底脚手架**（必须早期落盘）：
   `scaffold_result.py --case-summary /app/work/case_summary.json --out /app/output/result.json`，
   得到 status=partial 的骨架，之后各环节增量填充。
3. **材料解析与 span 索引**：材料中的 PDF 先转文本（`pdftotext -layout`），
   题录清单整理为 records.json/JSONL；运行
   `index_sources.py --sources <材料目录> --out /app/work/spans.json`。
   重跑逐字节一致；材料变更后必须重建索引并全量重审。
4. **研究问题结构化拆解**（模型）：按 PICO/PECO 拆出人群、干预、对照、结局
   与时间语言限制，写入 `/app/work/question_frame.md`，并回填 result.json
   的 counts/checks。
5. **检索式构造**（模型）：逐库给出检索式（数据库、字段、布尔逻辑、同义词
   与受控词、时间与语言限制），每段注明意图，写入
   `/app/work/search_strategy.md`；检索到的题录追加进材料目录后重建索引。
6. **条款化纳排标准**（模型）：纳入/排除逐条编号（研究类型、人群、时间、
   语言、全文可得性），写明条款间优先级与冲突处理，写入
   `/app/work/criteria.md`。
7. **两轮筛选留痕**（模型）：题录级与全文级逐条结论+排除理由+判定人，写入
   `/app/work/screening_log.jsonl`；纳入集须可据此重算。
8. **质量评价**（模型）：为纳入研究逐维度给出判定、依据位置（span_id）与
   总体等级，写入 `/app/work/appraisal.md`；等级如何影响论断强度须写明。
9. **证据提取登记**（模型+脚本）：从纳入研究提取证据片段，登记为
   `/app/work/extractions.jsonl`（每行 {record_id, span_id, quote, note,
   status:"extracted"}），quote 必须逐字取自 spans.json 对应 span。
10. **签名环节——先论断后正文**：
    a. 模型先写 `/app/work/claims.jsonl`：每行 {claim_id, text, strength,
       evidence:[{record_id, span_id, quote}], section, note?}；强度三分与词表
       见 references/claim_strength.md。
    b. 冲突证据登记 `/app/work/conflicts.jsonl`（格式见
       references/conflict_matrix.md），双方都必须有回链证据。
    c. 运行 `audit_claims.py --claims /app/work/claims.jsonl --spans
       /app/work/spans.json --out /app/work/audit_report.json --extractions
       /app/work/extractions.jsonl --conflicts /app/work/conflicts.jsonl`。
       **exit 3 时必须修复后重跑；审计全绿（exit 0）前禁止组装正文。**
    d. 审计通过后模型撰写综述正文：每段论断括注其 claim_id（如"……（CL-03）"），
       正文只许包含 claims.jsonl 中已登记的论断。
    e. `build_matrix.py --claims ... --spans ... --audit ... --out-dir
       /app/output/` 生成 evidence_matrix.csv、coverage.md、conflict_matrix.md。
11. **组装 result.json**：按第 4 节映射表填充全部 output_contract 字段，
    status 视完成情况改 complete/partial；孤儿证据、uncertain 论断、冲突对
    进 uncertainty。
12. **自查**：按第 6 节逐项核对后交付。

## 4. 输出合同映射表

| result.json 字段 | 来源 |
|---|---|
| case_id | case_summary.json（parse_case.py） |
| skill_name | 固定 `slr-claim-backlink`（scaffold_result.py） |
| status | 流程结束后人工设定：complete=全链走完且审计 exit 0；partial=写明界限；failed=写明原因 |
| product | 综述正文文件路径 + coverage.md 路径（正文每段括注 claim_id） |
| evidence_matrix | /app/output/evidence_matrix.csv 路径 + 论断×记录计数摘要（build_matrix.py） |
| sources | 纳入研究的 record_id 清单 + 题录（spans.json 中 records 部分）+ 检索记录 |
| uncertainty | uncertain 论断（claim_id+原因）+ C7 孤儿证据清单 + 冲突对（conflict_matrix.md）+ 质量评价保留意见 |
| change_records | 各环节增量填充记录（含审计不通过→修复→重跑的过程） |
| counts | 题录/纳入/排除计数、span 数、论断数（按 strength 分列）、违规数 |
| checks | 自查清单（第 6 节）+ 语义匹配边界声明（机器只保字面，语义已由模型复核） |

## 5. 异常处理

- **检索为空**：如实记录检索式与命中 0 的库；扩大同义词重检一次仍为空则在
  result.json 记 status=partial，结论区只写"未检索到合格证据"，禁止编造文献。
- **数据库或接口超时**：记录超时库与重试次数；已得题录照常建索引，缺失库
  列入 uncertainty。
- **全文不可得**：题录可入 spans.json 并在筛选记录中标注"全文不可得"；相应
  论断只能引用题录 span 或登记为 uncertain，禁止凭摘要断言全文数据。
- **术语同义歧义**：同义词表写进检索式与 question_frame.md；quote 匹配失败
  若源于术语差异，回原文重取 quote，不得改写原文凑匹配。
- **纳排条款冲突**：按 criteria.md 中的优先级裁定并在筛选记录写明引用条款；
  无优先级约定的冲突列入 uncertainty。
- **纳入证据互相矛盾**：双方论断都保留（不擅自取舍），登记 conflicts.jsonl，
  双方均有回链证据才入冲突矩阵；可能解释（人群/剂量/随访期差异）写入综述
  讨论与 uncertainty。
- **材料无法建索引**（目录为空、无 .txt/.md/.json/.jsonl、PDF 未转文本）：
  index_sources.py 以 exit 2 报 E-INPUT；先补做文本提取，勿绕过索引手写
  span_id。
- **quote 找不到（C2，exit 3）**：错误信息附该 span 内最相似行提示；必须
  **回到原文重取 quote，禁止凭记忆改写 quote**；确属 OCR 噪声时重提文本重建索引。
- **悬空 span_id（C3）**：材料变更后旧定位失效；重建索引并更新 claims 后重审。
- **inference 含断定词（C5）**：改用推断词（提示|可能|关联）或降级为
  uncertain 并说明原因，见 references/claim_strength.md 改写范式。
- **论断与证据语义不匹配但 quote 字面命中**：机器无法发现，属模型职责；
  模型须逐条做语义复核并在 checks 声明该边界；发现不匹配即更换证据或改写论断。
- **权限不足**（无法写 /app/output 等）：降级写到可用目录并在 result.json
  说明实际路径；不要伪造已写入状态。
- **预算/超时风险**：骨架已于第 2 步落盘，各环节增量填充；时间不足时优先
  保证索引、claims、审计与矩阵完成，正文可 partial 交付并写明界限。

## 6. 自查方法

1. `python3 $SKILL/scripts/selfcheck` → exit 0（正例全过、埋雷负例 exit 3、
   空输入 exit 2、索引重跑逐字节一致、py_compile 全过）。
2. 正式运行后核对：audit_report.json 的 claims_failed=0；孤儿证据已逐条
   人工处置（提取冗余 or 补登记论断）；冲突对双方均有证据。
3. 抽 3 条论断手工复核：按 span_id 打开原文，确认 quote 逐字一致且语义支撑
   论断（机器只保字面，此步是语义边界的人工兜底）。
4. result.json 字段对照第 4 节映射表无空缺；status 与实际情况一致；
   无越界结论、无编造元数据。

## 7. 最小调用示例

```bash
SKILL=/skills/weekly-skill   # 或用第 2 节 find 兜底定位
cd $SKILL/examples
python3 $SKILL/scripts/parse_case.py --case input/case.json --out /tmp/case_summary.json
python3 $SKILL/scripts/scaffold_result.py --case-summary /tmp/case_summary.json --out /tmp/result.json
python3 $SKILL/scripts/index_sources.py --sources sources --out /tmp/spans.json
python3 $SKILL/scripts/audit_claims.py --claims claims.jsonl --spans /tmp/spans.json \
  --out /tmp/audit_report.json --extractions extractions.jsonl --conflicts conflicts.jsonl
python3 $SKILL/scripts/build_matrix.py --claims claims.jsonl --spans /tmp/spans.json \
  --audit /tmp/audit_report.json --out-dir /tmp/products
# 预期：5 条命令全部 exit 0；audit 打印 1 条 C7 孤儿警告与 1 对冲突登记。
# 埋雷演示（各应 exit 3）：
python3 $SKILL/scripts/audit_claims.py --claims negative/claim_bad_quote.jsonl --spans /tmp/spans.json --out /tmp/n.json
```

（以上基于 examples/ 合成示例，仅演示接口与流程。）
