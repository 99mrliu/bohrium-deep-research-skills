---
name: d-identity-resolution-kg
description: 跨篇文献知识图谱的实体归一与冲突档案技能。脚本确定性地生成候选别名对（归一化键、首提缩写检测、类型阻塞、同键异上下文陷阱），模型只裁决一个小 JSON；产出稳定实体 ID、merge_ledger、nonmerge_registry、conflict_registry，并机械校验逐字引用后建图、执行查询、装配 result.json。适用于 /input 内含 case.json、material.json、primary/secondary-material.json、corpus-manifest.json 的双论文知识图谱任务。
---

# d-identity-resolution-kg — 跨篇实体归一与冲突档案（identity engineering）

## 1. 用途与适用条件

本技能解决"阅读15｜文献知识图谱构建"中的**对得齐**问题：跨论文的别名 / 缩写 /
大小写 / 同名异物归一，以及跨篇数值冲突的**保留式**存档。核心分工：

- **脚本做候选生成**（确定性、可复算）：扫描归一化语料，产出全部候选别名对，
  模型**不**自己找别名。
- **模型只做裁决**：对每个候选对给出 merge / nonmerge + 一行理由 + 证据段落号，
  写入一个很小的 `adjudication.json`；另写一个小型事实文件 `extractions.json`
  （节点 / 边 / 数值声明，各带逐字 quote）。
- 脚本再做：并查集归一 → 稳定实体 ID（E0001…）→ 建图 → 数值冲突登记 →
  引用完整性机械校验 → 自动执行 case.json 的 query_specs → 装配 result.json。

适用条件：输入符合 §2 运行时契约（两篇 JATS 风格全文、段落级地址、无 PDF 页码）。
Python 3.9+，仅用标准库，无网络。

## 2. 运行时契约

- 输入：`/input/`（case.json、task.md、material.json、primary-material.json、
  secondary-material.json、corpus-manifest.json；`secondary-publisher.xml` 只登记、
  永不解析）。脚本**发现**实际文件，容忍缺失 secondary、段落数不同、额外文件、
  material.json 的 list / `{"materials": [...]}` / mapping 三种形态。
- 工作区：`/app/work`；最终交付：`/app/output`。
- `/app/output/result.json` 必须包含 `case_id` 和 case.json `output_contract`
  声明的**全部键**（动态镜像；产不出的键置 null 并记入
  `unproduced_contract_keys`，绝不悄悄省略）。`status` 诚实取值
  success / partial / unable + 原因。
- case.json 根部的 doi/title/authors **只属于 primary**，不得安到 secondary 头上。
- 内联公式 / 下标按文本线性化（归一化键会折叠 Unicode 下标与连字符变体）。

## 3. 证据规则（不可协商）

- 每个实质节点 / 边 / 声明必须带 `source_id` + `paragraph_id`（组织者的 JATS 段落
  ID；本包**没有页码，禁止编造**）+ 该段落文本的**精确子串** quote。
- `verify.py` 机械校验所有产出文件中的每一处 quote 与地址，失败则退出码非零。
- 跨篇合并需要归一化键 + 明确理由，记入 merge_ledger；同名异物记入
  nonmerge_registry（保守默认：未裁决的对一律不合并）。
- 不同条件 / 样品 / 数值**永不**并入同一结论：同一实体同一指标的冲突数值以两个
  独立声明节点保留，`conflicts-with` 边标注差异条件，conflict_registry 记
  `resolution="preserved"`。
- 未报告项进 unreported 列表；来源内部冲突保留，不静默消解。

## 4. 模型 vs 脚本分工

| 步骤 | 执行者 | 产物 |
|---|---|---|
| 发现与归一化语料 | 脚本 discover.py | work/corpus.json |
| 候选别名对生成 | 脚本 candidates.py | work/candidates.json |
| 候选对裁决（唯一身份判断） | **模型** | work/adjudication.json（小） |
| 事实抽取（节点/边/声明/未报告） | **模型** | work/extractions.json（小） |
| 归一、实体 ID、台账 | 脚本 adjudicate.py | entity_map / merge_ledger / nonmerge_registry |
| 建图、冲突登记 | 脚本 build_graph.py | graph.json / conflict_registry.json |
| 引用完整性审计 | 脚本 verify.py | verify_report.json |
| 执行 query_specs | 脚本 query.py | query_results.json |
| 装配 result.json | 脚本 assemble.py | output/result.json + 签名产物 |

模型全程只写 **2 个小 JSON**（adjudication.json + extractions.json），
schema 见 `references/adjudication_schema.md`。其余全部机械完成。

## 5. 命令序列（照抄即可；真实任务把路径换成 /input、/app/work、/app/output）

```bash
S=/skills/weekly-skill/scripts
python3 $S/discover.py    --input /input --work /app/work
python3 $S/candidates.py  --work /app/work
# —— 模型读 work/candidates.json，写 work/adjudication.json（17 对 ≈ 2KB）——
python3 $S/adjudicate.py  --work /app/work
# —— 模型读 work/entity_map.json，写 work/extractions.json ——
python3 $S/build_graph.py --work /app/work
python3 $S/verify.py      --work /app/work
python3 $S/query.py       --work /app/work
python3 $S/assemble.py    --work /app/work --output /app/output
python3 $S/verify.py      --work /app/work --output /app/output   # 复审最终交付
```

预算（64 请求 / 900s / 16384 tokens）下绰绰有余：脚本调用 9 次，模型只需
读 candidates.json + 写 2 个小 JSON + 读最终报告，约 5–8 次模型请求。

## 6. 异常处理与预算降级

- 缺 secondary：discover 正常继续，跨篇对自然减少，warnings 记录。
- adjudication.json 缺失 / 不可解析 / 个别决策非法：非法决策进
  adjudication_report.json 的 quarantine，相关对**保守默认不合并**，流程继续。
- extractions.json 缺失：build_graph 退出码 2；仍可 assemble 出 honest partial。
- 查询为空 / 类型不支持：query_results 中 status=empty/unsupported 并说明，
  进入 uncertainty。
- verify 失败：退出码 1；**不要**强行交付，先看 verify_report.json 的 failures
  逐条修 quote（常见原因：模型凭记忆改写引文——必须回原文复制精确子串）。
- 时间不够时的降级顺序：① 砍 extractions.json 中次要边（保留全部 claims 与
  未报告项）→ ② 只答部分 query（其余在 uncertainty 中声明）→ ③ 始终先运行
  assemble 落一个 partial result.json，再逐步完善。adjudication **不可省**
  （它是本技能的重心）；实在不够时只裁决 trap 标记与跨篇对，其余接受默认
  不合并（安全方向）。

## 7. 签名产物

- `merge_ledger.json`：每个被接受的合并（前后键、理由、证据段落）。
- `nonmerge_registry.json`：每个被拒绝的合并（含同名异物陷阱说明）。
- `conflict_registry.json`：跨篇数值冲突，双声明保留 + 差异条件 +
  resolution="preserved"。
- 另有 entity_map.json（稳定 E0001… ID）、verify_report.json（引用完整性）、
  query_results.json（≥3 个真实执行的查询）。run_meta.json 是唯一允许含
  墙钟时间的文件，不参与确定性比较。

## 8. 参考文档与示例

- `references/identity_model.md`：归一化键、阻塞、陷阱检测、ID 方案。
- `references/adjudication_schema.md`：两个模型 JSON 的 schema。
- `references/conflict_and_query.md`：冲突模型与查询类型。
- `examples/`：完整可运行的合成示例（SYNTHETIC，非真实论文），
  `python3 scripts/run_minimal_example.py` 一键复现全部产物。
