---
name: export-review
description: 面向科研阅读成果的结构化导出与人工复核工程技能。把断言集合按严格 schema 校验后导出 JSONL/CSV/Markdown 复核单/自包含 HTML 预览与清单，并用独立脚本回读所有格式交叉核验一致性与哈希。适用于 Nanopublication 的结构化导出、结果复核复用、下游程序消费。不适用：上游 PDF 解析与断言拆解本身、交互式数据库发布。
---

# export-review — 读得懂：多格式导出与回读自证

**核心立场：导出不是最后一道工序，而是第一等交付物。机器格式必须无需人工清洗即可
解析，人工格式必须逐条可勾核；两者由独立回读证明一致。**

本技能的重心在**结果导出与复核复用**：断言拆解、证据绑定、来源记录由 Agent 按通用
契约完成，本技能保证导出形态合规、可解析、可勾核。全部脚本仅用 Python 3.9+ 标准库。

## 运行契约（平台评测环境）

1. 先读 `/input/case.json`、`/input/task.md` 与 `environment/resources.yaml`（如存在），
   记录 `case_id` 与 `output_contract` 要求的文件、格式与字段。**任务 schema 与其要求的
   序列化形态优先**：契约要求什么格式就交什么格式，本技能的导出集是缺省而非替代。
2. 工作区 `/app/work`，交付区 `/app/output`；`result.json` 含原 `case_id` 与全部契约
   字段，并在状态、不确定项、变更记录上保持诚实。
3. 预算 64 次模型请求 / 900 秒：先写 result.json 草稿（诚实 partial）再迭代；
   导出与校验脚本不耗模型请求。
4. 本技能目录记为 `SKILL_DIR`；脚本以 `python3 SKILL_DIR/scripts/...` 调用，绝对路径。

## 工作流（Agent 逐步执行）

### 第 1 步：组织断言集合

按 task.md 完成阅读与拆解后，把断言集合写为 `/app/work/claims.json`
（schema 见 [references/export-contract.md](references/export-contract.md)）：

```json
{"case_id": "…", "source": {"title": "…", "identifier": "…"},
 "claims": [{"id": "…", "text": "…", "subject": "…", "relation": "…",
             "object": "…", "qualifiers": [], "polarity": "positive",
             "modality": "asserted", "status": "asserted",
             "evidence": {"quote": "…", "location": {"page": 1}},
             "confidence": {"level": "high", "rationale": "…"}}]}
```

### 第 2 步：校验并导出全格式

```
python3 SKILL_DIR/scripts/export_bundle.py \
  --claims /app/work/claims.json --outdir /app/output/export
```

脚本先做 schema 校验（必填、类型、枚举、ID 唯一、asserted 必有引文），失败即列出
全部违例并退出 1；通过后导出：`claims.jsonl`、`claims.csv`、`review.md`
（人工复核单）、`review.html`（自包含预览）、`export-manifest.json`（逐文件
SHA-256 与条数）。

### 第 3 步：回读自证

```
python3 SKILL_DIR/scripts/check_exports.py \
  --claims /app/work/claims.json --export-dir /app/output/export \
  --out /app/output/export/export-check.json
```

独立回读：重新解析 JSONL 与 CSV、核对条数与 ID 集合、验证 manifest 哈希、检查
review.md/html 覆盖全部 ID。任一不一致 → FAIL 并退出 1。**导出未过回读不得交付。**

### 第 4 步：交付与状态

- 按契约把导出文件放到位；`result.json` 引用真实路径，不引用不存在的产物。
- 人工复核流程与勾核字段见 [references/review-workflow.md](references/review-workflow.md)：
  review.md 每条断言一行勾核位，复核结论可回填。
- 状态：契约产物齐 + 回读 PASS → `success`；有未覆盖区域/未决冲突 → `partial` 并说明。

## 异常处理

| 情形 | 处置 |
|-|-|
| schema 违例 | 列出全部违例行与原因，修复后重跑；不允许带病导出 |
| 任务要求其他格式（如 TriG） | 按契约直接产出该格式并自解析验证，本工具链不阻塞 |
| 字段含换行/逗号/引号 | CSV 用 RFC 4180 引号规则；HTML 全量转义；JSON 标准转义 |
| 空断言集 | 导出空集合并显式 status=partial + 原因，不伪造条目 |
| 下游要求列序/键序 | manifest 记录列序；键序按 export-contract 固定 |

## 本地最小示例（合成）

`examples/minimal/`：20 条合成断言（同时是本技能的 20 条断言样例）→ 全格式导出 →
回读自证。**合成示例，非正式案例结果。** 运行方式与本机真实产物见该目录 README 与
`expected/`。

## 边界与限制

- 本技能保证格式正确性与跨格式一致性，不保证断言内容真实性（前置流程职责）。
- HTML 是静态自包含预览，不含交互逻辑；正式案例若要求可编辑文档（Office 等），
  按契约另行产出并附真实渲染预览。
- CSV 是扁平化有损视图（qualifiers 拼接为分号串）；无损交换格式是 JSONL。
