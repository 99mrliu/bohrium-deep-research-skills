---
name: evidence-recall-sentinel
description: 用两阶段多通道高召回检索、全页搜索审计、逐候选审查状态与无证据证书核验论文问题；重点防止漏检，检索命中不等于支持。
---

# Evidence Recall Sentinel

对待核验的**问题**做证据检索，不能先把问题当事实。四级 verdict 为 `supported / partially_supported / contradicted / insufficient_evidence`。语义裁决由 Agent 完成；脚本只负责页面、查询计划、候选融合、状态、审计与契约验证。

## 运行边界

- Skill 位于 `/skills/weekly-skill`；输入默认为 `/input/case.json`、`/input/task.md`、`/input/claims-to-verify.json` 和实际论文 PDF/文本。结果写 `/app/output/result.json`。
- 请求/时间预算上限分别为 64 / 900 秒。无网络；本地脚本只含 stdlib。若 `environment/resources.yaml` 存在则读取。
- 先落 partial 骨架，再处理文档。缺 `pdftotext` 遇到 PDF、抽取失败、预算不足或验证失败时诚实保持 partial。
- 全程保留所有 Retrieved candidates，不 top-k 截断；详细协议见 [references/retrieval-protocol.md](references/retrieval-protocol.md)。

## 执行步骤

### 1. 扩展查询族

读取 claims 和任务，先做实体/原始词检索计划，再做用于查漏的同义词、数值、图表、限制词扩展。每条 family 指定 kind，每个 variant 可限制通道。字段见 [references/field-schema.md](references/field-schema.md)。

若输入已经含有充分 `query_families`，直接使用。否则把补全后的 claims JSON 写到 `/app/work/planned-claims.json`，下一步加 `--claims /app/work/planned-claims.json`。仅有脚本自动 bootstrap 时，不允许签发 no-evidence certificate。

### 2. 立即生成 partial 与实际检索工件

```bash
python3 /skills/weekly-skill/scripts/recall_sentinel.py prepare \
  --input /input \
  --work /app/work \
  --output /app/output/result.json
```

此命令先写 result 骨架，然后生成：

- `/app/work/pages.jsonl`：所有成功抽取页及全文；PDF 通过实际 form-feed 分页。
- `/app/work/sources.json`：实际来源、页数和抽取方式。
- `/app/work/retrieval-plan.json`：所有族与变体、全页范围、预算使用。
- `/app/work/search-audit.jsonl`：每个变体的完整扫页与各通道命中；命中无 verdict。
- `/app/work/candidates.jsonl`：跨 exact/token/numeric 通道融合的所有候选，初始逐条 unreviewed，并记录 origin family。

检查 audit 判断是否发生阶段二新增召回。若某族或变体遗漏，补全计划并重新 prepare；不要用主题相关性替代检索。

### 3. Agent 写独立语义审查

读取 pages 全文、candidates 和 audit，为每个候选写 `reviewed/unreviewed`、relevant 和具体排除理由。为每个问题写 verdict、rationale、evidence candidate IDs、conflicts 与 uncertainty 到 `/app/work/review.json`。

- 检索命中只表示候选；确认实体、终点、数值、比较、限制条件的语义后才裁决。
- 未报告不等于 contradicted；冲突双方候选 IDs 都保留。
- 结论为 insufficient 时，必须扫描全部文档页，执行足够查询族，并清零未审候选；任何暂留候选必须说明，结果保持 partial。
- output_contract 中额外业务字段可在 review 的 `result_overrides` 填入；不要删除动态骨架字段。

### 4. 合并、约束并验证

```bash
python3 /skills/weekly-skill/scripts/recall_sentinel.py finalize \
  --case /input/case.json \
  --work /app/work \
  --output /app/output/result.json \
  --review /app/work/review.json

python3 /skills/weekly-skill/scripts/recall_sentinel.py validate \
  --case /input/case.json \
  --result /app/output/result.json \
  --work /app/work
```

每个 insufficient 自动内嵌 no-evidence certificate：族充分性、变体执行、全文档页清单、候选状态与排除解释均须通过。缺证书或审计不完整会写 partial、退出 1。complete 只表示本次合同与审计流程完成，不表示所有问题 supported。

### 5. 可选召回覆盖图

```bash
python3 /skills/weekly-skill/scripts/recall_sentinel.py coverage-svg \
  --work /app/work \
  --output /app/output/recall_coverage.svg
```

图来自真实运行工件，柱高表示候选数，不表示支持。

## 可执行合成示例

```bash
bash /skills/weekly-skill/scripts/run_example.sh
```

示例位于 `examples/synthetic/`：S1 初检窄族零命中，第二 synonym/table 族找回 18.0% 表格；S2 真正未报告 pediatric 36-month end point，获得证书。脚本真实生成 pages、candidates、search audit、review、final result 和 SVG，并将只有一族的坏例跑到 finalizer 的预期 exit 1。全部标注 **SYNTHETIC / 合成示例**，不是官方答案；示例 reviewer 只是固定模拟 Agent，不能用于生产自动裁决。
