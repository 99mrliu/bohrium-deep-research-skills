---
name: evidence-graph-structurer
description: 把文献阅读产物结构化为可查询的证据图谱：每个结论沿稳定 ID 回溯到源文锚点（"查得回"），跨源冲突是显式边而非文字备注，覆盖率/孤儿论断/冲突清单由机器算出。支持 T1 阅读问答与 T2 benchmark-DRAFT 出题工单，统一入图并输出 evidence_graph.json、graph_map.md、契约驱动的 result.json 与 failure_analysis.md。Use when you need to structure reading-comprehension or benchmark-drafting deliverables into a queryable evidence graph with verbatim evidence verification, cross-source conflict edges, orphan detection and machine-computed coverage metrics.
---

# evidence-graph-structurer — 证据图谱结构化器

## 1. 用途与适用条件

将阅读产物组织成**证据图谱**而非普通答案文件：

- 每个结论（Claim）沿稳定 ID 经 Evidence → Anchor → Source 走回源文锚点；
- 证据逐字核验（NFKC、连字、断词、空白归一化），supports 边带
  pass/fail/degraded 结论；
- 跨源冲突是显式 ConflictEdge（numeric_mismatch / negation）；
- 覆盖率、孤儿论断、冲突清单、逐题 0/1/2 分均为图指标的确定函数。

适用：Bohrium Playground 挑战 benchmark-a1d81ca4 的 T1（阅读问答/
解析/翻译/抽取）与 T2（benchmark-DRAFT 出题）工单。本技能包**不含
任何预制答案**；examples/ 全部为合成示例（SYNTHETIC EXAMPLE）。

## 2. 运行时契约

1. 平台将本技能装在 `/skills/weekly-skill`；官方 DeepSeek Harness 在
   3 个隐藏固定案例上各跑 3 次。
2. 每个案例输入：`/input/case.json`（含 `case_id` 与
   `output_contract` 字段集——**运行时动态读取**，不得硬编码字段
   名）、`/input/task.md`、`/input` 下源材料（真实 PDF 或段落/表格
   文本 txt/md/json；revision2 案例为段落/表格文本）。
3. 工作目录 `/app/work`；最终交付 `/app/output`，含 `result.json`：
   `case_id` + `output_contract` 全部字段（填不了置 null 并记入
   uncertainty，**不得编造**）+ 诚实 `status`（成功 / 部分完成 /
   无法判断 / 拒答 + `status_reason`，partial 必须指明局限）+
   `sources` + `uncertainty` + `change_records`。
4. 预算：64 次模型请求、900 秒。**必须先尽早写合法部分
   result.json**（流程第 0 步），再增量完善。
5. 技能包约束：≤50 个 UTF-8 文本文件、单文件 ≤500KB、总 ≤2MB、
   无符号链接；不得包含隐藏案例预制答案。
6. python3 脚本只允许标准库（3.8+）；pdftotext 可选，缺失时 PDF
   源降级为无锚点节点（status=degraded），不崩溃。

## 3. 依赖

- Python ≥ 3.8，仅标准库（argparse/json/re/os/sys/hashlib/
  unicodedata/tempfile/shutil/subprocess）。
- 可选外部命令 `pdftotext`（poppler）：缺失时 PDF 自动降级。
- 脚本：`scripts/graph_init.py`、`graph_link.py`、`graph_query.py`、
  `graph_export.py`（均 `--help` 可用，确定性，原子写）。
- 参考文档：`references/graph_schema.md`（模式）、
  `references/query_cookbook.md`（9 个预置查询）。

## 4. 两类工单识别

`graph_init.py` 自动判定：task.md 含「出题 / 题卡 / benchmark /
DRAFT / 草拟 / 4 道 / 四道」任一关键词 → **T2**，否则 **T1**。

- **T1**：编号问题 → Task 节点（q1…qn）；agent 起草的论断与证据
  按「问题-答案-论断-证据」入图。
- **T2**：题卡条目 → Task 节点（item1…item4）；agent 起草的题卡
  （任务/材料范围/参考答案/评分规则/证据锚点/难度/授权）按
  「题卡-参考答案-评分规则-证据」入图，RubricRule 节点经
  governed_by 边约束题卡。

## 5. 工作流程

**0. 尽早写合法部分 result.json（预算安全网）**

```bash
python3 scripts/graph_init.py --case /input/case.json \
  --task /input/task.md --materials /input \
  --out /app/work/graph.json \
  --init-result --result-out /app/output/result.json
```

**1. 建图**：同上命令（Source 含 sha256；Anchor 按空行切分为
doc{n}.para{k}；Task 从 task.md 编号行抽取）。

**2. agent 起草 claims/items**：写 `/app/work/agent_answers.json`。
T1 用 `claims`（task/text/evidence:[{anchor,quote}]/honest），quote
必须逐字摘自锚点原文；T2 用 `items`（question/reference_answer/
rubric/evidence/difficulty/license）。

**3. 核验 + 冲突检测**：

```bash
python3 scripts/graph_link.py --graph /app/work/graph.json \
  --answers /app/work/agent_answers.json \
  --report /app/work/link_report.json
```

逐字核验每条 evidence → supports 边 verdict；正则抽数值+单位做
跨锚点冲突检测 → ConflictEdge；孤儿检测（无 supports 边的非诚实
claim）。

**4. 修复孤儿 / fail**：孤儿必须补证据重跑 link，或改诚实标记
（honest=true + honest_reason）；fail 按 `link_report.json` 的
reason 修复（核对锚点 ID / 回到原文逐字引用）。

**5. 覆盖率与分数**：

```bash
python3 scripts/graph_query.py --graph /app/work/graph.json \
  --out-json /app/work/query_report.json \
  --out-md /app/work/query_report.md
```

9 个预置查询（定义见 query_cookbook.md）：孤儿、覆盖矩阵、证据
复用、冲突清单、证据链、未引用锚点、逐题 0/1/2 分数、诚实标记、
汇总指标。

**6. 导出交付**：

```bash
python3 scripts/graph_export.py --graph /app/work/graph.json \
  --case /input/case.json \
  --work-file /app/work/result_fields.json --outdir /app/output
```

产出 `evidence_graph.json`（完整图+指标）、`graph_map.md`（人类可
读图谱）、`result.json`（动态读 output_contract 字段名，从工作文件
同名键拷贝；缺失置 null）、`failure_analysis.md`（孤儿与 fail 边的
题目 ID、摘录、原因、修法）。存在孤儿或 fail 边时**门禁拦截**
（退出码 2，`--force` 可跳过，但 result.json 仍记部分完成）。

## 6. 异常处理表

| 异常 | 行为 |
|---|---|
| case.json 缺失/畸形 | 按空对象继续，case_id 置 null，不崩溃 |
| task.md 无编号行 | 回退为单一 Task（q1/item1） |
| 源材料为 PDF 且无 pdftotext | Source status=degraded，无锚点，其余照常 |
| 源文件读不出 | 记 degraded:read-error，继续处理其他源 |
| answers 文件非 JSON object | 报错退出码 1，graph.json 不被写坏 |
| evidence 锚点不存在 | verdict=fail(anchor_not_found)，进 link_report |
| 引文不在锚点内 | verdict=fail(verbatim_mismatch) |
| 孤儿 > 0 或 fail > 0 时导出 | 门禁拦截（退出码 2），failure_analysis.md 给出修法 |
| 数值/单位解析失败 | 跳过该条记录，不影响其余冲突检测 |

## 7. 交付前自查

1. `q_metrics`：孤儿 = 0（或全部诚实标记）、fail = 0；
2. 图谱指标非退化：节点/边计数 > 0、锚点覆盖率 > 0；
3. `q_conflict_list` 中每条冲突已在对应答案字段中显式并列报告；
4. `result.json`：output_contract 字段无编造，null 字段均已写入
   uncertainty；status 与 status_reason 诚实一致；
5. `evidence_graph.json` 与 `graph_map.md` 已落盘 /app/output；
6. （自检确定性）重跑 graph_init，graph.json sha256 不变。

## 8. 限制

- 冲突检测基于**数值+单位与否定词的启发式**：同义词、单位换算、
  语义等价/矛盾的判断靠 agent 标注，不在脚本职责内；可能漏报
  （不同措辞的同量冲突）或误报（语境不同的同属性数值）。
- 锚点粒度为空行切分的块，过长段落会放大逐字核验的命中范围；
  起草案引文仍须逐字。
- 逐题 0/1/2 分是图指标的确定函数，只代表"证据完备性下界"，不
  取代内容质量评审。
- T2 题卡的任务/材料范围/难度/授权等元信息由 agent 在 items 中
  给出，脚本只负责结构化挂接与核验，不自动生成题目。
