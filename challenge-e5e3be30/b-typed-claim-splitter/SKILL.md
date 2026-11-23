---
name: typed-claim-splitter
description: >-
  文献证据溯源与事实核验的"论断拆解"专用技能：把中英复合论断类型化拆解为原子子判断
  （事实/比较/因果/范围四型），用覆盖矩阵机检保证不遗漏、不重叠，再逐条核验后按显式
  规则聚合回 supported / partially_supported / contradicted / insufficient_evidence 四级
  判定。触发条件：任务要求核验论文/文献支持的论断（claims-to-verify.json、fact-check、
  evidence tracing、断言溯源），尤其论断为含多指标、比较、因果、适用范围的复合句时。
  不触发：纯文献综述写作、无待核验论断的摘要生成、单篇 PDF 的格式转换、与事实核验无关
  的数据处理任务。
---

# typed-claim-splitter：类型化原子拆解引擎

## 0. 评测运行契约（必须遵守）

- 本 Skill 被安装到 `/skills/weekly-skill`。下文中 `<skill>` 一律指该目录，
  例如 `<skill>/scripts/cue_scan.py` 即 `/skills/weekly-skill/scripts/cue_scan.py`。
- 输入在 `/input/`：`case.json`（含 `case_id` 与 `output_contract` 字段清单）、
  `task.md`、`claims-to-verify.json`（其中论断是**待核验的问题，不是权威事实**）、
  论文 PDF、可能的 `environment/resources.yaml`。
- 工作目录 `/app/work`；最终成果放 `/app/output`，必须有 `result.json`，包含：
  `case_id`、`output_contract` 的**全部字段**、诚实 `status`
  （success / partial / cannot_determine / refused）、`sources`、`uncertainty`、
  `change_records`。
- 预算：64 次模型请求 / 900 秒 / 每响应 16384 tokens。**脚本能做的绝不花模型
  请求**：拆解建议、覆盖机检、聚合全部交给 `<skill>/scripts/` 下的确定性脚本。
- **先写 `result.json` 骨架（status=partial）再增量覆写**，每完成一条论断就
  回写一次，防止超时丢成果。
- 四级判定：supported / partially_supported / contradicted /
  insufficient_evidence。**主题相关≠支持；未报告≠反驳；冲突并列双方原话。**

## 1. 何时用 / 不用

**用**：`/input/claims-to-verify.json` 中存在待核验论断，且论断为复合句——
含多个指标并列（"强度提升且成本降低"）、比较（"提高 30%""低于 X"）、
因果（"因为晶粒细化"）、适用范围（"适用于所有铝合金"）中两种及以上。
这类论断核验出错的一半原因在"拆错了"：复合句被当成单判断、比较方向
丢失、否定词被吞、条件范围被丢、子判断重叠导致循环论证。

**不用**：论断本身就是单谓词简单句（直通逐条核验即可，见异常处理表）；
任务与事实核验无关。

## 2. 输入盘点（0 模型请求）

1. `cat /input/case.json`：取 `case_id` 与 `output_contract` 字段清单。
2. `cat /input/task.md`：确认任务变体与附加约束。
3. `cat /input/claims-to-verify.json`：列出论断 id 与原文。若其 schema 与
   `examples/claims.json`（数组、元素含 `id`/`text`）不同，用一个 shell/
   Python 单行脚本转换，**不要**为此消耗模型请求。
4. 盘点 PDF：`ls /input/*.pdf`，用 `pdftotext`（若有）或 Python 提取全文到
   `/app/work/paper.txt`。脚本能做的绝不花模型请求。
5. 立即写 `/app/output/result.json` 骨架：`status="partial"`，`claim_verdicts`
   各论断先填 `"pending"`，`change_records` 记一条"初始化骨架"。

## 3. 流水线总览

```
输入盘点 → ① 拆解（cue_scan.py）→ ② 覆盖机检（coverage_matrix.py，不过则返工）
        → ③ 定位证据（简明）→ ④ 逐条判定（简明四级规则）
        → ⑤ 聚合（aggregate.py --explain）→ ⑥ 产出 result.json
```

工程深度押在 ①②⑤（本 Skill 的核心）；③④ 保持简明，把模型请求预算留给
真正的证据阅读。

### ① 拆解：线索词扫描 + 类型化原子拆解

```bash
python3 <skill>/scripts/cue_scan.py \
  --claims /app/work/claims.json \
  --lexicon <skill>/references/cue-lexicon.json \
  --out /app/work/atoms.json
```

- 按 `references/cue-lexicon.json` 做中英双语六类槽位扫描：comparator /
  negation / significance / condition / causal / scope（含原词与字符位置）。
- 给出建议拆分点（强分隔符恒拆；弱分隔符需两侧各有谓词；因果/范围从句
  标记前移拆分）与原子子判断列表（类型 fact / comparison / causal /
  scope，附 `evidence_needed`、`predicate_stem`、`modifiers`）。
- 给出槽位→子判断映射。**模型复核要点**：拆分点是否改变原义；否定词是否
  仍在正确子判断内；比较方向是否保留。四型定义与拆解规则见
  `references/decomposition-taxonomy.md`。

### ② 覆盖机检：不遗漏、不重叠

```bash
python3 <skill>/scripts/coverage_matrix.py \
  --atoms /app/work/atoms.json \
  --out /app/work/coverage_report.json
echo $?
```

- 输出子判断 × 槽位覆盖矩阵。
- **omission（有槽位无人认领）→ exit 1：拆漏了，必须返工**——调整拆解后
  重跑 ①②，直到 exit 0。
- overlap（两子判断覆盖完全相同槽位集且谓词主干相同）只警告：人工确认
  是否重复核验/循环论证，必要时合并子判断。
- 模型若手工调整 atoms.json（允许且常见），**调整后必须重跑本步**。

### ③ 定位证据（简明）

对每个原子子判断，按其 `evidence_needed` 在 `/app/work/paper.txt` 中定位：
先用 `grep -n` 关键词（数值、材料名、机制词）缩小范围，再精读命中段落。
每个子判断记录：source、locator（页码/段落）、quote（原文原话）。模板见
`templates/subjudgment.json`。

### ④ 逐条判定（简明四级规则）

- supported：证据直接断言同一命题（数值、方向、条件一致）；
- partially_supported：命题的一部分成立、其余无证据或被限定；
- contradicted：证据直接否定同一命题（方向相反/数值冲突/范围被收窄）；
  **未报告≠反驳**；
- insufficient_evidence：无直接证据；**主题相关≠支持**。
- 冲突证据：并列双方原话，不得抹平。
- 否定修饰（modifiers.negation）必须参与极性判定。

### ⑤ 聚合：确定性规则合成

```bash
python3 <skill>/scripts/aggregate.py \
  --subjudgments /app/work/subjudgments_<claim_id>.json \
  --explain \
  --out /app/work/verdict_<claim_id>.json
```

规则全集见 `references/aggregation-rules.md`：任一核心子判断
contradicted → 整论断 contradicted；全 supported → supported；仅修饰
子判断被反驳 → partially_supported；全 insufficient →
insufficient_evidence；混合 → partially_supported。`--explain` 的逐步
推导原样写入 result.json 的理由字段，保证判定可审计。

### ⑥ 产出

按 `output_contract` 逐字段填齐，覆写 `/app/output/result.json`：
更新 `claim_verdicts`（含各论断 verdict、子判定 breakdown、理由）、
`decomposition_report`、`coverage_report`、`sources`、`uncertainty`，
并在 `change_records` 追加一条"完成论断 X"。全部完成后 `status` 改为
`success`；有论断无法判定时保持 `partial` 并说明。

## 4. 预算与增量保存

- 模型请求只花在：复核拆解建议、精读证据段落、撰写子判定与 uncertainty。
  参考配比（64 次预算）：盘点 0、拆解复核 ≤3、证据阅读每论断 ≤6、聚合 0、
  产出与自查 ≤4。
- 每完成一条论断立即覆写 `result.json`；`change_records` 逐条追加。
- 临近超时：已判定的论断保留 verdict，未判定的填 `insufficient_evidence`
  并在 `uncertainty` 注明"预算耗尽，未完成核验"，`status=partial`。

## 5. 异常处理表

| 异常 | 处置 |
|---|---|
| 无法拆分的论断（结构混乱、拆后语义失真） | 放弃机拆，按单论断整体核验，在 `uncertainty` 注明"拆解失败，整体判定"， verdict 从宽口径（有任一面向被反驳不得给 supported） |
| 单谓词论断 | 直通：跳过拆分点建议，cue_scan 会给出"无线索词"警告，按单一 fact 子判断处理，不强行拆分 |
| 拆解与原文冲突（拆后拼接无法还原原论断） | 以原文为准重做拆解；在 `change_records` 记录此次返工 |
| coverage_matrix exit 1（omission） | 必须返工：补认领槽位或重拆，重跑 ①② 至 exit 0 后才允许进入核验 |
| overlap 警告 | 人工确认；确属重复则合并子判断，否则在 `uncertainty` 说明保留理由 |
| PDF 无法提取文本 | 在 `uncertainty` 注明证据获取受限；能判的判，不能判的 insufficient_evidence，`status=partial` |
| claims-to-verify.json schema 不符 | 用脚本转换为 `[{"id","text"}]`，不消耗模型请求 |
| 论断超出论文范围（论文未涉及） | 对应子判断 insufficient_evidence；**未报告≠反驳** |

## 6. 输出契约自查清单（提交前逐项过）

- [ ] `result.json` 存在且为合法 JSON（`python3 -m json.tool` 通过）。
- [ ] `case_id` 与 `/input/case.json` 一致。
- [ ] `output_contract` 的**每个字段**都在 result.json 顶层出现，无遗漏、
      无拼写偏差。
- [ ] `status` 诚实：全部论断完成才 success；部分完成 partial；证据完全
      不可得 cannot_determine。
- [ ] 每条论断的 verdict 由 aggregate.py 产出或与其规则一致；理由含
      规则编号（R1–R6）。
- [ ] 覆盖机检通过（exit 0）的报告已随附；如有返工，`change_records`
      有记录。
- [ ] 每个 supported/contradicted 都有 sources + 原文 quote；冲突并列
      双方原话。
- [ ] 否定/条件/范围槽位对应的子判断文本中这些限定词仍在。
- [ ] `uncertainty` 非空：至少写明启发式拆解的复核情况与证据强度。
- [ ] `change_records` 含初始化、每条论断完成、最终定稿三类记录。

## 7. 文件导航

- `scripts/cue_scan.py`：线索词与语义槽位扫描 + 拆解建议（exit 0/1/2）。
- `scripts/coverage_matrix.py`：覆盖矩阵机检（exit 0 通过 / 1 omission /
  2 输入错误）。
- `scripts/aggregate.py`：确定性聚合，`--explain` 逐步推导（exit 0/1/2）。
- `references/decomposition-taxonomy.md`：四型定义与拆解规则 D1–D8。
- `references/aggregation-rules.md`：聚合规则 R1–R6 与边界情形。
- `references/cue-lexicon.json`：中英线索词表（六类槽位 + 拆分配置）。
- `templates/subjudgment.json`：原子子判断记录模板。
- `examples/`：合成示例（论文、论断、case、端到端脚本与预期输出，
  全部标注"合成示例"）。运行 `bash <skill>/examples/run_example.sh`
  可复现完整流水线。
