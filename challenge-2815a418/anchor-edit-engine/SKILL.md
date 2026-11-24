---
name: anchor-edit-engine
description: 审稿回复与论文修改场景的锚点定位引擎——基线编译为锚点图、修改只经锚点逐字落稿、回复信与改动三方核验；适用于需要可独立核对修改定位的返修任务。
---

# anchor-edit-engine：锚点落稿与三方核验的返修方案

## 用途与适用条件

针对「审稿回复与论文修改」任务：只修订组织方给定的基线（通常是摘要而非完整原稿），
逐条处理实际给出的意见，交付可编辑修订稿、回复信草案、修改定位登记、未到位证据清单。

本 Skill 的第一公民是**锚点**：

1. 基线先被编译成锚点图（每段一个锚点号：章节路径 + 段序 + 逐字 quote）；
2. 一切修改只能通过锚点落稿——锚点 quote 在稿件中逐字唯一匹配才应用，绝不猜位置；
3. 每处改动自动登记三要素定位（章节、段序、锚点 quote）并打 CHG 标记；
4. 最后由独立脚本做三方核验：回复信声称的每个定位必须能在修订稿与
   changes.json 中解析到真实改动；核验不过，result.json 不得标 success。

适用条件：基线为 Markdown 文本、段落以空行分隔、意见可拆成编号子要求。
不适用的情形：基线是 PDF/图片等不可逐字匹配的格式（先转成文本再进锚点流程，
并在 uncertainty 中声明转换损耗）。

## 运行契约

- 输入：`/input/case.json` 与 `task.md`；材料在 `/input/materials/manuscript-baseline.md`
  （基线摘要，非完整原稿）与 `/input/materials/reviewer-comments.md`（意见摘要，
  非逐字审稿报告）；可能有 `environment/resources.yaml`。
- 工作目录 `/app/work`；最终产物与 `result.json` 放 `/app/output`。
- `result.json` 必须含：原始 `case_id`（原样复制）、案例 `output_contract` 的
  **全部字段**（字段名以 case.json 为准，不得凭经验假设）、诚实的 `status`、
  `sources`、`uncertainty`、修改记录。部分完成必须说明界限（status=partial）。
- 预算：64 次模型请求、900 秒。**第一条命令就落一个合法的部分 result.json**；
  机械工作全由脚本做，Agent 只做判断与写作。

## 快速路径

```bash
export SKILL=/skills/weekly-skill
mkdir -p /app/work /app/output
```

**命令一（prepare，落合法部分 result + 编译锚点图）：**

```bash
python3 "$SKILL/scripts/make_result.py" --case /input/case.json \
  --out /app/output/result.json --status partial \
  --uncertainty "初始化：意见尚未处理" \
&& python3 "$SKILL/scripts/anchor_map.py" /input/materials/manuscript-baseline.md \
  --out /app/work/anchors.json --stats
```

**命令二（finish，落稿 → 三方核验 → 更新 result；核验失败则整条命令中止，
不会误标 success）：**

```bash
python3 "$SKILL/scripts/apply_edits.py" \
  --baseline /input/materials/manuscript-baseline.md \
  --anchors /app/work/anchors.json --edits /app/work/edits.json \
  --out /app/output/revised-manuscript.md \
  --changes /app/output/changes.json --report /app/work/apply_report.json \
&& python3 "$SKILL/scripts/locate_check.py" \
  --letter /app/output/response-letter.md --changes /app/output/changes.json \
  --revised /app/output/revised-manuscript.md --decisions /app/work/decisions.json \
  --report /app/output/locate_report.json \
&& python3 "$SKILL/scripts/make_result.py" --case /input/case.json \
  --out /app/output/result.json --status success \
  --artifact revised_manuscript=/app/output/revised-manuscript.md \
  --artifact response_letter=/app/output/response-letter.md \
  --artifact change_locations=/app/output/changes.json \
  --artifact evidence_checklist=/app/output/evidence-checklist.md \
  --changes /app/output/changes.json
```

注意：`--artifact` 的字段名必须照抄 case.json 里 `output_contract` 的键，
上面只是示例；若 locate_check 退出 1，改用 `--status partial` 单独重跑
make_result 并在 uncertainty 写明原因。两条命令均与 cwd 无关。

## 工作流程

1. **prepare**（上面的命令一）：部分 result.json 落盘，基线编译为
   `/app/work/anchors.json`。通读锚点图与意见摘要。
2. **意见拆解与决策**：Agent 手写 `/app/work/decisions.json`（列表，每条
   `{sub_request, decision: accept/partial/rebut, rationale, planned_action}`），
   逐条覆盖意见中实际出现的子要求编号（如 R1.1）。
3. **设计改动**：Agent 手写 `/app/work/edits.json`（格式见
   scripts/apply_edits.py 文档字符串：change_id、sub_request、action
   新增/修改/删除、anchor、new_text、summary）。锚点号从 anchors.json 选取；
   拿不准用哪段时，用反查确认：
   `python3 "$SKILL/scripts/anchor_map.py" /input/materials/manuscript-baseline.md --find "逐字片段"`。
   好锚点的标准见 references/anchor_protocol.md。
4. **落稿**：跑 apply_edits。读 apply_report.json：凡 pending_review 的改动，
   修正 edits.json（换锚点、改用更长的定位段、补 new_text）后重跑，直至
   pending 清空或确属无法落稿（进证据清单）。
5. **写信**：Agent 撰写 `/app/output/response-letter.md`，逐条回复；每处改动
   配一条规范定位行（四件套：CHG 编号 ｜ 章节 ｜ 段序 ｜ 锚点 quote，格式与
   判定规则见 references/location_format.md）。写信时用 `--find` 反查锚点、
   用 changes.json 复制 quote，**不要凭记忆转写**。
6. **证据清单**：Agent 写 `/app/output/evidence-checklist.md`，登记所有未到位
   证据（无法补的实验/分析）及处置方式。
7. **finish**（上面的命令二）：三方核验通过才允许 status=success。

## 事实红线

- 不得冒称真实审稿人的逐字要求——只有意见摘要，信中写「根据意见摘要」；
- 不得冒称真实补做实验/统计分析——做不到就进证据清单并下调结论；
- 不得冒称原作者已改稿或编辑部已接收——交付的是修订草案与回复信草案；
- 修改必须真实落在基线文本中，空口承诺「已修改」而无 CHG 落稿视为违规；
- case_id 原样复制，output_contract 字段名照抄 case.json。

## 异常处理表

| 异常 | 处置 |
| --- | --- |
| 锚点未命中（anchor_not_found） | 进 pending_review；用 --find 按内容反查正确锚点，修正 edits.json 重跑；禁止改用模糊匹配强行落稿 |
| 锚点不唯一（anchor_not_unique） | 进 pending_review；该段 quote 在全文出现多次，说明基线有重复段——改选中包含更大上下文的相邻段做锚点，或在 uncertainty 声明后放弃该处改动 |
| new_text 为空（empty_new_text） | 进 pending_review；补齐文本重跑 |
| 意见之间相互冲突 | decisions.json 中说明冲突与取舍理由，回复信礼貌说明，uncertainty 登记 |
| 意见明显有误 | decision=rebut，礼貌反驳（引用基线原文为据），不落稿，信中仍需出现该子要求编号 |
| 无法补实验/补算 | decision=partial：证据状态进 evidence-checklist.md，局限性说明要真实落稿（如下调结论强度的 CHG），不得空口承诺 |
| 基线缺失/不可读 | 立即 `--status failed` 写 result.json 并说明，不编造内容 |
| 多轮返修 | CHG 编号续编不重用（上一轮到 CHG-05 则新一轮从 CHG-06 起）；锚点随新基线重新编译，旧锚点号作废，见 references/anchor_protocol.md |
| 三方核验 FAIL | 按 locate_report.json 的错误清单逐条修信或补落稿后重跑；核验不过一律 status=partial，不得 success |

## 脚本清单与依赖

全部只用 Python 3 标准库，无可选依赖，无降级路径。

| 脚本 | 作用 |
| --- | --- |
| scripts/anchor_map.py | 基线 → anchors.json；`--find` 反查锚点；`--stats` 段落统计 |
| scripts/apply_edits.py | edits.json → revised-manuscript.md + changes.json + apply_report.json（逐字唯一匹配才落稿，打 CHG 标记） |
| scripts/locate_check.py | 回复信 ↔ changes.json ↔ 修订稿 三方核验；FAIL 时 exit 1 并写 locate_report.json |
| scripts/make_result.py | result.json 写出/更新：case_id 原样复制、contract 字段补全、sources/uncertainty/change_records |

参考文档：references/anchor_protocol.md（锚点规范）、
references/location_format.md（定位行写法与核验判定）。

## 最小示例

`examples/` 内含完整可运行的合成示例（非正式案例结果）：合成基线、2 条意见
3 个子要求、填好的 decisions.json 与 edits.json、规范回复信、
`run_example.sh` 端到端跑通 anchor_map → apply_edits → locate_check →
make_result，产物在 `examples/output/`。复现：

```bash
bash "$SKILL/examples/run_example.sh"
```
