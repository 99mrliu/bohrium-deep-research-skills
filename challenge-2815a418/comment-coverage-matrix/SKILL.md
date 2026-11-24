---
name: comment-coverage-matrix
description: 审稿返修场景的意见拆解与逐条覆盖回应——当需要根据 reviewer-comments 与基线稿件交付逐条回复信、修订稿、修改定位与证据清单，且必须保证每条意见的每个子要求都有明确裁决、不答漏、信稿一致时使用。
---

# comment-coverage-matrix：意见拆解与逐条覆盖回应

## 用途

面向「审稿回复与论文修改」任务：把 reviewer-comments（意见摘要）拆成**覆盖矩阵**（每条意见 → 若干原子子要求 → 每个子要求有类型/严重程度/动作/裁决/理由/证据状态），再由脚本**按构造**生成逐条回复信，最后用机器核验「矩阵 ↔ 回复信 ↔ 稿件改动」三对齐。本 Skill 的第一公民是覆盖矩阵：回复信里每个子要求编号必然出现，从机制上杜绝「笼统致谢、只答一半」。修改落稿由内置最小锚点引擎完成。

适用：组织方基线摘要（manuscript-baseline.md）+ 意见摘要（reviewer-comments.md）的受控修订演练。不适用：完整原稿排版、真实实验执行、多语言全文翻译。

## 运行契约（必须遵守）

- 输入：`/input/case.json`、`/input/task.md`；材料在 `/input/materials/manuscript-baseline.md` 与 `/input/materials/reviewer-comments.md`（若路径不同，先 `ls /input` 确认真实路径，读实际文件，不要按名字臆测内容）。
- 工作目录 `/app/work`；最终产物与 `result.json` 放 `/app/output`。
- `result.json` 必须含原始 `case_id` 与案例 `output_contract` 的**全部字段**（字段名以 case.json 为准），并含诚实的 `status`、`sources`、`uncertainty`、修改记录。部分完成必须写明界限。
- **第一条命令就要落一个合法的部分 result.json**（防超时零产出），之后增量改进、最后再覆盖成完整版。
- 预算：64 次模型请求、900 秒。**机械工作全部交给脚本，Agent 只做判断**（核对矩阵、写裁决理由、写替换文本）。
- 事实红线：只修订指定基线；逐条处理实际给出的意见；实质性修改必须真实落进基线文本；**不得**冒称真实审稿人逐字要求、真实补做实验、原作者已改稿、编辑部已接收；不得新增材料外事实。

## 快速路径（与 cwd 无关）

```bash
SKILL=/skills/weekly-skill
mkdir -p /app/work /app/output
ls /input /input/materials   # 确认真实输入路径

# 0. 立刻落一个合法的部分 result.json（最重要，先跑这条）
python3 $SKILL/scripts/make_result.py --case /input/case.json --status partial \
  --uncertainty "处理刚开始：意见已读取，矩阵与产物待生成" --out /app/output/result.json

# 1. 意见 → 覆盖矩阵骨架（防漏：子要求只多不少）
python3 $SKILL/scripts/decompose.py --comments /input/materials/reviewer-comments.md \
  --case /input/case.json --out /app/work/matrix.json

# 2. 【Agent 核心工作】读 matrix.json：合并误拆、补拆漏拆、逐子要求填
#    decision / decision_reason / response_summary / evidence（补做类必填）
python3 $SKILL/scripts/matrix.py validate /app/work/matrix.json   # 必须无 issues
python3 $SKILL/scripts/matrix.py stats    /app/work/matrix.json   # 总述用数字

# 3. 【Agent】写 edits.json（逐字锚点 + 替换文本），落稿
python3 $SKILL/scripts/apply_edits.py --manuscript /input/materials/manuscript-baseline.md \
  --edits /app/work/edits.json --outdir /app/output
#    检查 /app/output/apply_report.json：pending_review 非空则修锚点重跑

# 4. 矩阵（+改动）→ 逐条回复信 + 证据清单
python3 $SKILL/scripts/letter_build.py --matrix /app/work/matrix.json \
  --changes /app/output/changes.json --outdir /app/output

# 5. 三对齐机器核验，必须 PASS（exit 0）
python3 $SKILL/scripts/coverage_check.py --matrix /app/work/matrix.json \
  --letter /app/output/response-letter.md --changes /app/output/changes.json \
  --evidence /app/output/evidence-checklist.md --out /app/output/coverage_report.json

# 6. 覆盖写入最终 result.json（字段名以 case.json 的 output_contract 为准）
python3 $SKILL/scripts/make_result.py --case /input/case.json --status complete \
  --sources "/input/materials/manuscript-baseline.md,/input/materials/reviewer-comments.md" \
  --uncertainty "如实填写：无法补做项、待人工确认项、摘要非全文等界限" \
  --artifact revised_manuscript=/app/output/revised-manuscript.md \
  --artifact response_letter=/app/output/response-letter.md \
  --artifact change_locations=/app/output/changes.json \
  --artifact evidence_checklist=/app/output/evidence-checklist.md \
  --change-records /app/output/changes.json --out /app/output/result.json
```

## 工作流程（Agent 的判断职责）

1. **先读后拆**：通读 reviewer-comments 与 baseline 全文各一遍，再跑 decompose。
2. **核对骨架（必须）**：decompose 的输出是「宁多勿漏」的骨架，Agent 要：
   - 合并被连接词误拆、实为同一要求的碎片（保留一个 sub_id，其余删除并把它并回 raw_text）；
   - 补拆漏拆的子要求（一条意见里「同时/并且/另外/also/moreover」、疑问句、建议句各自成条）；
   - 修正预填的 type/severity/action 猜测。
3. **逐子要求裁决**：每个子要求填 `decision`（采纳/部分采纳/不采纳）+ `decision_reason` + `response_summary`（回复信用的那句话）；补做类（补实验/补数据/补文献/重做分析）强制填 `evidence.status`（到位/部分到位/无法补做），无法补做必须写 `alternative_explanation`。
4. **写 edits.json**：对要落稿的修改给出**逐字唯一锚点**与替换/插入文本；锚点必须能在 baseline 中唯一命中。
5. 让脚本生成回复信与证据清单；coverage_check 不过就回修矩阵或锚点，不要手改生成物（手改后必须重跑 coverage_check）。

## 拆解纪律

- **宁可多拆不可漏拆**：拆错可以合并，漏拆无法补救。骨架阶段子要求只多不少。
- 「同时 / 并且 / 另外 / 此外 / also / moreover / furthermore」是天然拆点；分号连接的两个谓语也是拆点。
- **疑问句与建议句都算子要求**（「为什么选 5？」「建议增加对比实验」各自成条）。
- 标注子要求间关系：`并列` / `前置依赖`（B 依赖 A 先做，写 `depends_on`）/ `互斥`（两条意见冲突时标明，见异常表）。
- 分类标准见 `references/taxonomy.md`；语气规范见 `references/letter_template.md`。

## 异常处理表

| 异常 | 处置 |
|---|---|
| 两条意见互相冲突 | 两条都保留，relation 标 `互斥`；取更合理一条采纳，另一条 `不采纳` 并礼貌反驳，response_summary 说明冲突与取舍 |
| 意见本身有误 | `不采纳` + 礼貌反驳：引用基线原文作证据，禁止攻击性措辞（见 letter_template 反驳档） |
| 无法补做（缺数据/无实验条件/基线为摘要） | decision 可为 `部分采纳`；`evidence.status=无法补做` + `alternative_explanation`（替代证据或局限声明）；**不得冒称已补做**；可执行的文本修改仍须落稿 |
| 意见含义不明 | 按两种解读各列一个子要求，`decision` 先填较稳妥解读，`decision_reason` 注明「两种解读，待人工确认」，result.json 的 uncertainty 同步写明 |
| 意见无法定位到基线对应段落 | 在 response_summary 中说明，edits 不做强行锚定；coverage_check 允许无 CHG 但要有 `no_change_explanation` |
| 多轮返修 | 子要求续编号不复用：第 2 轮从 `R{n+1}.1` 起编（如 R4.1），矩阵加 `"round": 2`，保留上一轮全部条目 |
| 锚点未命中/多命中 | 进 `apply_report.json` 的 pending_review；换更长逐字锚点重跑，禁止模糊替换 |
| 输入路径与预期不符 | 先 `ls /input` 按实际路径跑；找不到材料则 result.json 标 `partial` 并写明缺口 |

## 脚本清单（均为 Python 3 标准库）

| 脚本 | 作用 |
|---|---|
| `scripts/decompose.py` | reviewer-comments → matrix.json 骨架（按 R#/编号/段落分块，块内按连接词与句子建议拆分，预填 type/severity/action 猜测与逐字 raw_text） |
| `scripts/matrix.py` | `validate`（裁决/理由/回应/证据完整性校验，有问题列 issues 并 exit 1）；`stats`（按 type/severity/decision 统计） |
| `scripts/apply_edits.py` | 最小锚点落稿引擎：edits.json → revised-manuscript.md（带 CHG 标记）+ changes.json + apply_report.json；逐字唯一锚点，未命中进 pending_review |
| `scripts/letter_build.py` | matrix（+changes）→ response-letter.md（语言随意见语言；总述→按意见分节逐子要求→裁决统计表+证据状态表）+ evidence-checklist.md |
| `scripts/coverage_check.py` | 三对齐核验：子要求编号全出现且块非空、CHG 有归属、采纳的修改文本类有 CHG 或说明、信与矩阵裁决一致、证据清单与补做类一致；写 coverage_report.json，失败 exit 1 |
| `scripts/make_result.py` | 生成 result.json：case_id、status、sources、uncertainty、`--artifact 字段=路径`（自动对齐 output_contract 全字段）、change_records |

## 最小示例

`examples/` 含一组**合成示例（非正式案例结果）**：虚构基线短稿 + 3 条意见（R1 含 2 个子要求、R2 为无法补做的补实验、R3 为写作类）、填好的 `matrix.json`、`edits.json`、端到端 `run_example.sh`（decompose → validate → apply_edits → letter_build → coverage_check → make_result）。运行：

```bash
bash examples/run_example.sh   # 产物在 examples/output/
```
