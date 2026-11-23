---
name: provenance-ledger
description: 面向科研阅读的来源元数据与可追溯链路技能。为每个来源建立身份记录（标题/作者/年份/标识符/版本/SHA-256），断言以内容寻址 URI 落账，跨来源去重合并、版本链与冲突全部留痕，并导出 nanopub 风格 TriG/JSONL。适用于 Nanopublication 的来源追溯、去重合并、版本对照。不适用：无来源材料的纯问答、图像级数据提取。
---

# provenance-ledger — 来源身份与可追溯断言台账

**核心立场：断言可以被复制，来源链路不能丢。任何一条结论都要能回答「谁、在哪一版、
哪个文件、哪一处」说出它的。**

本技能的重心在**来源元数据与追溯**环节：断言拆解与证据形态按通用契约完成，但每条
断言必须以台账方式绑定来源身份与内容指纹。全部脚本仅用 Python 3.9+ 标准库。

## 运行契约（平台评测环境）

1. 先读 `/input/case.json`、`/input/task.md` 与 `environment/resources.yaml`（如存在），
   记录 `case_id`、`output_contract` 字段与要求的产物路径。**任务 schema 优先**。
2. 工作区 `/app/work`，交付区 `/app/output`；`result.json` 含原 `case_id` 与全部契约
   字段（断言、证据、来源元数据、置信度依据、状态、不确定项）。
3. 预算 64 次模型请求 / 900 秒：先建来源台账并写 result.json 草稿（诚实 partial），
   再逐条补断言；台账脚本不耗模型请求。
4. 本技能目录记为 `SKILL_DIR`；脚本以 `python3 SKILL_DIR/scripts/...` 调用，用绝对路径。

## 工作流（Agent 逐步执行）

### 第 1 步：为每个来源建立身份记录

对每个输入文件（论文、补充材料、数据文件、旧版本）填写来源记录（schema 与标识符优先
级见 [references/provenance-schema.md](references/provenance-schema.md)）：

- `title/creators/year`：从材料实际读出；读不到就标 `unavailable`，**不得猜**；
- `identifier`：DOI > arXiv ID > 其他稳定标识；都无则给 `title-hash` 派生标识并注明；
- `version`：版本号/修订日期/预印本 vN；同一论文不同版本是不同来源记录，
  用 `supersedes` 链接；
- `path`：文件实际路径；`sha256` 由脚本计算，不手填。

把来源表写到 `/app/work/sources.json`。

### 第 2 步：拆解断言并绑定来源

按 task.md 覆盖范围读材料。每条断言：自足原子句、受控关系、限定保留、逐字引文与
页/段定位，并给出 `source_id` 绑定。多来源佐证同一断言时保留全部绑定。归属纪律：
被引既往工作的结论主体是被引工作，用 attribution 限定，不记成本论文的新实验。

### 第 3 步：落账、去重与版本对照

```
python3 SKILL_DIR/scripts/mint_nanopubs.py \
  --claims /app/work/claims.jsonl \
  --sources /app/work/sources.json \
  --outdir /app/output/nanopubs
```

脚本执行（规则细节见 [references/dedup-and-versioning.md](references/dedup-and-versioning.md)）：

- 重算每个来源 `sha256` 并与声明值比对，不一致即报告错误；
- 按语义键（主体+关系+客体+限定+极性+模态）去重合并，合并保留全部来源绑定；
- 为每条唯一断言铸造**内容寻址 URI**（本地方案，非注册、非 Trusty URI）；
- 沿 `supersedes` 链做版本对照：仅旧版有、仅新版有、两版共证分别列出；
- 检测冲突：同主体同关系同限定、客体不同 → 冲突项，不自动裁定；
- 导出 `nanopubs.jsonl`（合并断言+完整来源链）、`nanopubs.trig`（每条
  head/assertion/provenance/pubinfo 四命名图）、`provenance-report.json`（指纹核验、
  合并日志、冲突、版本对照）。

### 第 4 步：交付与状态

- `result.json` 写入契约字段；来源记录原样进入来源字段（或按契约引用）。
- 状态：覆盖完成、指纹核验通过、无未决冲突 → `success`；指纹不一致、有未裁定冲突、
  元数据缺失但断言可用 → `partial` 并说明缺口；材料不可得 → `blocked`。
- 「读不到的元数据」标 `unavailable` 并说明尝试过的读取位置，不丢弃有效断言。

## 异常处理

| 情形 | 处置 |
|-|-|
| 无 DOI/标识符 | 用 title-hash 派生标识，注明派生方式，不伪造 DOI |
| 同名不同文件 | 以 sha256 区分，分别建来源记录 |
| 文件被替换（指纹变化） | 报 E_SOURCE_MISMATCH，锚定结论按新材料重核 |
| 跨版本结论变化 | 两版断言都保留，版本对照标明仅旧/仅新，不擅自取新 |
| 冲突断言 | 双方保留并各自带来源，标 conflict 交人工 |

## 本地最小示例（合成）

`examples/minimal/`：同一虚构论文的两个版本（v1/v2）与 6 条断言，演示指纹核验、
跨版本去重合并、版本对照与一条冲突检出。**合成示例，非正式案例结果。** 运行方式与
本机真实运行产物见该目录 README 与 `expected/`。

## 边界与限制

- 内容寻址 URI 只是本地确定性标识：未做 RFC 规范化变换，不在任何注册表登记，
  不构成 Trusty URI；跨组织复用时按任务要求替换命名空间。
- 去重键不含证据与来源，语义键相同但证据不同的断言保留各自证据绑定；
  冲突检测是机械规则，语义冲突（措辞不同、含义相反）仍须人工判读。
- 本技能不做断言粒度核验与引文复定位；证据质量由任务流程前置保证。
