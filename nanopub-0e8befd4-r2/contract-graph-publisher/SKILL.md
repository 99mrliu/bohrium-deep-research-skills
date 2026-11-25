---
name: contract-graph-publisher
description: >-
  当任务要求把已给出的 claims、evidence、sources 按随案原始 output_contract 自适应发布为精确键 JSON/JSONL，或显式请求具有独立 Head、assertion、provenance、pubinfo named graphs 的 nanopublication TriG 与 JSON-LD 时触发；尤其适用于字段映射、原 case_id 与 ID 引用保持、负/条件/hedged 断言 reify、sources/uncertainty/change_records 和契约回读。任务若是版面设计、覆盖矩阵、数值计算、竞赛裁决、从文献自行抽取主张、注册 nanopublication、生成 Trusty URI，或未给出契约却想自行发明 schema，则不触发。
---

# Contract Graph Publisher

将**已经规范化的知识记录**发布为下游契约要求的文本产物。唯一重心是契约保真、引用完整与合格的 nanopublication 图结构；不做版面、覆盖矩阵、数值计算或裁决。

## 何时使用与停止使用

使用本 Skill 时必须具备随案原始 `output_contract`、通用 `claims/evidence/sources`，以及声明实际输出字段和请求格式的 `manifest`。原始契约不可用时应报告阻塞，不能自行发明 schema。

以下情况停止并诚实报错：manifest 增加契约外字段、必需字段无诚实值、ID 重复或引用悬空、请求格式未声明、非 RDF 请求却要求附带 RDF、缺少资源限制、试图把本地 IRI 当作注册/Trusty URI，或要求猜测创建者与 license。

## 固定平台接口

- `/input/case.json` 与 `/input/task.md`：先读取原始任务事实、材料路径和 output_contract。**真实 case 可能只有 PDF/草稿路径，不能假定平台同时给出规范化记录和 manifest。** 原契约无论以散文、字段表、机器 JSON 或 JSON Schema 表达都优先于通用命名、manifest 便利声明和默认格式；工具不从散文自行猜测字段。
- 原文到工具输入的桥接：Agent 先按原任务阅读材料并形成准确的原子 claims、最小充分 evidence 与真实 sources，再创建 `/app/work/adapted/case.json`，原样复制 case_id/output_contract，填入这些实际记录及忠实 manifest；同时创建 `/app/work/adapted/task.md`，承载从原任务逐项转写的机器可读契约。适配记录原始路径和字段映射，不增删 EXACT 顶层键、不制造科学事实，也不把适配文件写回 `/input`。若原 case 已符合工具输入形状，可直接使用，不再复制。
- `environment/resources.yaml`：本 Skill 的限制文件；若平台提供 `/input/environment/resources.yaml` 或其他实际 resources.yaml，先读取并在命令中显式改传。上限为 64 requests / 900 sec。发布工具本身不发网络请求；Agent 前文阅读产生的外部请求仍计入预算。
- `/app/work`：尽早保存 `result.partial.json`、候选结果、适配记录和错误记录；partial 不宣称完成。
- `/app/output`：只放最终协商产物，并按原 `/input/task.md` 再核对一次，而非只核适配副本。不使用个人绝对路径，不依赖网络或个人 Python 环境。

详细输入形状、字段映射和优先级见 `references/schema-mapping.md`。RDF 图结构见 `references/rdf-structure.md`，不可宣称的验证范围见 `references/review-boundaries.md`。

## 不可破坏的发布规则

1. `result.json` 顶层必须逐键等于原始 `output_contract.fields`，保留原始 `case_id`，不能加 `status`、`errors`、`debug`、评分、报告路径等辅助键。验证信息独立写入 `validation-report.json`，不混入结果。
2. `manifest.output_fields` 必须与原始字段列表完全相同；它不是扩写契约的入口。自定义输出名通过显式 `field_mapping` 映射到规范流，未知必需字段只能由 `contract_values` 中已有诚实值提供。
3. 保留 `claim_id → evidence_ids → source_ids` 全链。RDF 的 publication 记录也必须只引用实际 claim ID。`sources`、显式/派生的限定性 `uncertainty`、阶段化 `change_records` 按契约输出；若原契约不允许这些键，不得擅自补入。
4. `manifest.request_format=json`：仅输出基础 JSON 结果和独立验证报告，不生成 TriG、JSON-LD 或 JSONL。
5. `jsonl`：除契约要求的 `result.json` 外输出 `claims.jsonl`，每行一条 claim，并独立回读逐条比对。绝不附带 RDF。
6. `rdf`：同时输出 `nanopubs.trig` 和 `nanopubs.jsonld`，二者由同一四图模型生成并回读核对。不得只给其中一种格式。
7. 所有 claim 采用 `rdf:Statement` reification；负面、条件、hedged 断言额外保留限定信息，绝不泄露为无条件 subject-predicate-object 三元组。
8. 本地 URN/IRI 只用于可复现图连接，**不表示已注册或已生成 Trusty URI**。未显式提供 creator、license、created 就省略相应元数据。

## 完整平台命令

从本 Skill 根目录运行，要求 Python 3.9+，只用标准库。先完成原文阅读与忠实适配；仅当原输入已经符合工具形状时才直接传 `/input`：

```bash
mkdir -p /app/work /app/output
PYTHONDONTWRITEBYTECODE=1 python3 scripts/publish.py \
  --case /app/work/adapted/case.json \
  --task /app/work/adapted/task.md \
  --resources environment/resources.yaml \
  --work /app/work \
  --output /app/output
```

若资源文件位于 `/input/environment/resources.yaml`，仅将 `--resources` 的参数改为该路径。每个成功用例的基础产物：

- `/app/output/result.json`：精确契约结果；
- `/app/output/validation-report.json`：键、case_id、引用、耗时、requests 和按需格式检查；
- `/app/work/result.partial.json`：输入规范化前和引用规范化后两次覆盖保存的早期 partial；
- `/app/work/result.candidate.json`：发布前独立回读过的候选；JSONL/RDF 还分别保留对应 candidate 文件，候选通过后才发布。

按 manifest 追加：`claims.jsonl`（仅 `jsonl`），或 `nanopubs.trig` + `nanopubs.jsonld`（仅 `rdf`）。契约未通过时可能只有 `/app/work/publish-error.json`，不伪造最终结果。连原始字段都无法确定时，连 partial result 也不安全，因此仅保存错误记录。每个 case 应使用新建或为空的 output 目录；工具不会把其他 case 的旧文件冒充本次产物，也不会擅自清理用户目录。

## 可复现的真实示例

所有 examples 都是 **SYNTHETIC 合成测试，非正式结果**。

### 1. 最小 JSON：生成 expected 并复跑 actual

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/publish.py \
  --case examples/minimal-json/input/case.json \
  --task examples/minimal-json/input/task.md \
  --resources environment/resources.yaml \
  --work examples/minimal-json/work \
  --output examples/minimal-json/expected
PYTHONDONTWRITEBYTECODE=1 python3 scripts/publish.py \
  --case examples/minimal-json/input/case.json \
  --task examples/minimal-json/input/task.md \
  --resources environment/resources.yaml \
  --work examples/minimal-json/work \
  --output examples/minimal-json/actual
cmp examples/minimal-json/expected/result.json examples/minimal-json/actual/result.json
```

实际保留的 `expected/result.json` 由上述真实运行生成。`actual/result.json` 与它一致；actual 中没有 RDF。

### 2. 显式 RDF 请求：20 条合成 claims

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/publish.py \
  --case examples/rdf-request/input/case.json \
  --task examples/rdf-request/input/task.md \
  --resources environment/resources.yaml \
  --work examples/rdf-request/work \
  --output examples/rdf-request/actual
```

真实产物为 `actual/result.json`、`actual/nanopubs.trig`、`actual/nanopubs.jsonld`、`actual/validation-report.json`，另有 work partial/candidate。报告记录四图计数和子集回读结果；这不是完整 W3C 验证。

### 3. EXACT 额外字段负例

```bash
set +e
PYTHONDONTWRITEBYTECODE=1 python3 scripts/publish.py \
  --case examples/negative-contract/input/case.json \
  --task examples/negative-contract/input/task.md \
  --resources environment/resources.yaml \
  --work examples/negative-contract/work \
  --output examples/negative-contract/actual
status=$?
set -e
test "$status" -eq 2
test ! -e examples/negative-contract/actual/result.json
test ! -e examples/negative-contract/actual/nanopubs.trig
test ! -e examples/negative-contract/actual/nanopubs.jsonld
```

负例故意让 manifest 多出 `debug_status`；工具退出 2，在 `work/publish-error.json` 留下拒绝原因，不输出带辅助键的结果。

## 限制与资源纪律

- 不含网络注册、签名、Trusty 算法、外部 RDF 库或完整 W3C 验证。TriG 使用严格受限生成器与解析器；JSON-LD 使用展开 named-graph 子集回读，并做图形计数和限定断言泄漏检查。
- 通用工具接受当前文档规定的 claims/evidence/sources 形状；复杂 JSON Schema 条件、任意嵌套转换或从散文自动构造 schema 不在边界内。
- 总量约束：本 bundle 全部文件为 UTF-8 文本，无符号链接、无二进制；不超过 50 个文件，每个文件小于 500 KB，总体小于 2 MB。运行本地 Python 时设置 `PYTHONDONTWRITEBYTECODE=1`，避免额外二进制缓存。
- 不做 git commit 或 push，不联系注册服务。
