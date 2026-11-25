---
name: c-evidence-audit-loop-kg
description: 文献知识图谱构建的"独立审计-有界修复"质控闭环。模型只写两份小 JSON（抽取草案 + 针对修复队列的补丁），脚本机械地逐条审计（引文精确子串、地址存在性、根元数据归属、合并纪律、段落覆盖度），产出带理由码的逐项裁决、只含失败项的 repair_queue.json、至多 2 轮的复审，以及可度量的 audit_certificate.json（引文精确率/地址有效率/归属正确率/段落覆盖率及迭代间增益），让"审计 vs 不审计"的质量差可直接从数字读出。适用于 /input 提供 case.json + 双论文 JATS 段落 JSON 的运行环境。
---

# c-evidence-audit-loop-kg：审计-修复过程质控闭环

## 1. 用途与适用条件

把"模型抽取 → 直接建图"的一次性流程，升级为"**草案 → 独立机械审计 → 只修失败项 →
有界复审 → 建图/查询/交付**"的可度量质量闭环。核心思想：审计器不依赖模型自评，
所有判定都来自脚本的机械检查（字符串包含、集合成员、键存在性），因此每项指标都可复核。

适用条件：

- 输入在 `/input`：`case.json`（含 `output_contract`、可选 `query_specs`、根书目元数据——
  **只属于第一篇主论文**）、`task.md`、`material.json`、`primary-material.json`、
  可选 `secondary-material.json`、可选 `corpus-manifest.json`、
  可选 `secondary-publisher.xml`（只登记存在，永不解析）。
- 段落定位使用组织方的 JATS `paragraph_id`；**本包没有 PDF 页码，禁止编造页码**。
- 仅有 Python 3.9+ 标准库；无网络、无第三方包。

不适用：需要全文 PDF 像素/图表数据、或需要跨案例增量图谱的场景。

## 2. 模型 vs 脚本的分工（预算关键）

| 阶段 | 执行者 | 产物 |
|---|---|---|
| 0 发现输入 | 脚本 `discover.py` | `/app/work/corpus.json` |
| 1 抽取草案 | **模型**写唯一一份 `/app/work/extraction.draft.json` | 逐项 node/edge/merge/nonmerge/unreported/note |
| 2 审计（第 1 轮） | 脚本 `audit.py` | `audit_report.iter1.json` + `repair_queue.json`（只含失败项） |
| 3 定向修复 | **模型**只读 `repair_queue.json`，写小文件 `/app/work/repairs.json` | 仅队列内 id 的补丁 |
| 4 复审（第 2 轮，封顶） | 脚本 `audit.py --iteration 2` | `audit_report.iter2.json`；仍失败 → `quarantine.json` |
| 5 建图 | 脚本 `build_graph.py` | 只采纳 accept 项 → `graph.json` |
| 6 查询 | 脚本 `query.py` | 自动执行 case.json 的 query_specs → `queries.json` |
| 7 组装 | 脚本 `assemble.py` | `/app/output/result.json` + `audit_certificate.json` 等 |

**模型全程只写 2 个 JSON 文件**（草案 + 修复补丁），其余全部机械化；
在 64 请求 / 900 秒预算下通常 6–10 次模型请求即可完成。

## 3. 精确命令序列（可直接照抄）

```bash
python3 scripts/discover.py --input /input --work /app/work --output /app/output
# → 模型阅读 /app/work/corpus.json 与 references/extraction_schema.md，
#   写 /app/work/extraction.draft.json（schema 见 references/）
python3 scripts/audit.py --work /app/work --draft /app/work/extraction.draft.json --iteration 1
# → 模型只读 /app/work/repair_queue.json，写 /app/work/repairs.json
#   （只修队列内条目；修不了的条目用 {"id": ..., "drop": true, "drop_reason": "..."} 撤回）
python3 scripts/apply_repairs.py --work /app/work \
    --base /app/work/extraction.draft.json \
    --repairs /app/work/repairs.json \
    --out /app/work/extraction.repaired.json
python3 scripts/audit.py --work /app/work --draft /app/work/extraction.repaired.json --iteration 2
python3 scripts/build_graph.py --work /app/work
python3 scripts/query.py --work /app/work
python3 scripts/assemble.py --work /app/work --output /app/output
```

**修复环最多 2 轮**（`audit.py --iteration` 只接受 1 或 2）。第 2 轮仍失败的条目
被 reject 进 `quarantine.json`，不再进入图谱——诚实降级优于带病入库。

## 4. 证据规则（不可妥协）

- 每个实质 node/edge/merge/nonmerge 必须带 `evidence`：`source_id` + `paragraph_id`
  + 逐字短引 `quote`；`quote` 必须是所引段落 `text` 的**精确子串**（脚本机械验证）。
- 根元数据（case.json 的 doi/title/authors）**只属于 primary**；
  把根标题/DOI 安到 secondary 证据上会被判 `ROOT_META_MISATTRIBUTION`。
- 跨篇合并（merge）必须有 `normalized_key` + `reason`；同名不同对象必须显式
  nonmerge 并给出理由；**同一指标不同数值的 claim 禁止合并**（`INVALID_NUMERIC_MERGE`），
  数值冲突以 `conflicts-with` 边保留双方。
- 未报告项用 `unreported` 条目登记（附支持其"未报告"的原文引文，如有）；
  源内冲突保留（resolution=preserved），不静默消解。
- 行内公式/上下标一律线性化为纯文本。
- ≥3 个真实执行的查询：优先使用 case.json 的 `query_specs`，类型支持
  `neighborhood` / `edges_by_relation` / `conflict_check`；每个查询返回结果子图、
  支撑证据与显式的 undetermined 列表；查询为空要如实说明。

## 5. 审计检查项与理由码（详见 references/audit_codes.md）

逐项检查：结构字段（`MISSING_FIELD`/`UNKNOWN_OP`）、引文（`QUOTE_NOT_SUBSTRING`/
`QUOTE_TOO_SHORT`）、地址（`SOURCE_UNKNOWN`/`ADDRESS_UNKNOWN`）、归属
（`ROOT_META_MISATTRIBUTION`）、边端点（`ENDPOINT_UNKNOWN`）、合并纪律
（`MERGE_MISSING_KEY`/`MERGE_MISSING_REASON`/`MERGE_MEMBER_UNKNOWN`/
`INVALID_NUMERIC_MERGE`）。

度量指标（写入 `audit_certificate.json`，逐轮对比）：

- **quote-precision %**：引文为所引段落精确子串的比例；
- **address-validity %**：source_id+paragraph_id 双存在的比例；
- **attribution-accuracy %**：无根元数据错配的条目比例；
- **paragraph-coverage %**：被 accept 项引用的语料段落覆盖率；
- `baseline_vs_final` 给出首轮（未修复基线）与末轮的百分点增益——
  **未走审计环的基线流程相当于直接交付基线数字**，增益由此可证。

## 6. result.json 与交付

`assemble.py` 动态镜像 `case.json` 的 `output_contract`：声明的每个键都出现；
产不出的键置 `null` 并在 `uncertainty` 记录原因，绝不静默省略。`status` 取
`success` / `partial` / `unable` / `refused` 并附原因。`discover.py` 在流水线开始时
就写入一份诚实的 partial `result.json`，随后逐步完善。确定性要求：所有分级产物
无墙钟时间戳（唯一时间戳在 `result.json → run_meta`），键与数组均排序输出。

`/app/output` 交付：`result.json`、`graph.json`、`queries.json`、
`audit_certificate.json`（签名产物）、`audit_report.json`、`repair_queue.json`、
`quarantine.json`。

## 7. 异常处理

- 缺 `secondary-material.json` → 单论文案例，记 warning 继续；缺 `case.json` 或
  `primary-material.json` → discover 以退出码 2 终止并写明原因。
- `material.json` 为 list / `{"materials": [...]}` / 映射三种形态均可容忍；
  `corpus-manifest.json` 的 doi/title/sha256 与加载源不一致 → 记入 warnings 与
  uncertainty，不中断。
- 草案 JSON 无法解析 / 无 `items` 列表 → audit 退出码 2；个别非法条目按
  `ITEM_NOT_OBJECT` 判 repair。
- 修复补丁引用不在队列中的 id → `apply_repairs.py` 拒绝并 warning（防止顺手改坏
  已通过项）。
- 查询无结果 → 该查询 `status=executed`、空子图 + undetermined 说明，不伪造答案。
- 审计第 2 轮仍有失败 → 这些条目隔离进 `quarantine.json`，`status=partial`，
  图谱只用干净条目构建。

## 8. 预算感知降级方案（64 请求 / 900 秒）

1. **时间紧**：压缩草案规模——优先 claim/metric/paper/material 与 query_specs 需要的
   关系；researcher/method 等可少抽。草案越小，审计与修复越快。
2. **更紧**：跳过可选 note 条目；合并候选只保留最有把握的 1–2 个。
3. **极限**：若第 1 轮审计后无时间修复，直接以 `--iteration 2` 复审原草案：
   失败项被隔离，仍能交付一份"干净子图 + quarantine + 诚实证书（基线数字）"的
   partial 结果——比交付未审计图谱更可核验。
4. 任何情况下都先保证 `result.json` 已写入（discover 阶段已落盘 partial）。

## 9. 合成示例

`examples/` 含完整合成示例（**SYNTHETIC，非真实论文，非正式案例答案**）：
`python3 scripts/run_minimal_example.py` 一键跑通全闭环，stage-1 草案故意埋入
3 个缺陷（错误引文、坏 paragraph_id、根元数据错配），可观察到审计指标从
93.9%/97.0%/96.7% 提升到 100%/100%/100%。详见 `examples/README.md`。

## 10. 文件导航

- `scripts/`：discover / audit / apply_repairs / build_graph / query / assemble /
  run_minimal_example（均 `--help` 可用，stdlib-only）。
- `references/extraction_schema.md`：抽取草案 schema（模型写作规范）。
- `references/audit_codes.md`：理由码语义与处置建议。
- `references/metrics.md`：证书指标定义与解读。
