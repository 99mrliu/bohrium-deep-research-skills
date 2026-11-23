---
name: corpus-provenance-knowledge-graph
description: >-
  面向多来源文献语料（primary/secondary）的溯源知识图谱构建技能。核心不是通用建图教程，
  而是语料真实性与证据地址确定性：每个实质性节点/边必须携带 source_id + JATS paragraph_id
  + 原文精确短引文；DOI/title/authors 等根元数据只归属 primary；跨论文合并须有规范化键与
  显式理由，同名≠同一实体必须留下显式 nonmerge；来源冲突与未报告信息原样保留。
  提供宽容输入归一化、严格证据校验、确定性查询执行与合同镜像装配四类脚本，
  适用于阅读15等文献知识图谱构建赛题。
---

# corpus-provenance-knowledge-graph（语料溯源知识图谱）

## 1. 技能定位

本技能解决**文献知识图谱构建**任务中的上游可信性问题，中心是：

1. **语料真实性（corpus authenticity）**：任何图谱对象必须能机械回溯到
   归一化语料中的具体来源与具体段落，引文为原文逐字符子串；
2. **证据地址确定性（evidence-address determinism）**：地址为
   `(source_id, paragraph_id)` 二元组，禁止 PDF 页码式地址（本任务语料无页码），
   重复段落地址视为歧义不可用；
3. **合并纪律**：跨论文 merge 需规范化键与显式理由；通用术语相同不等于同一
   物理对象/模型/数据集；条件、样本、数值不同绝不并入同一结论；
4. **诚实披露**：来源冲突原样保留（resolution=preserved），未报告信息进入
   unreported，合同键不可产生时置 null 而非省略。

本技能**不是**通用 KG 建模教程；节点类型体系刻意保持小而刚性
（paper / sample / method / condition / metric / claim），以换取可机械校验性。

## 2. 官方运行时契约

- 技能安装位置：`/skills/weekly-skill`（本 bundle 即该目录内容）。
- 输入：`/input/`
  - `case.json`：含 `case_id`、`output_contract`（结果键契约）、可选 `query_specs`；
  - `task.md`：任务书；
  - `material.json`：聚合索引（容忍列表 / `{"materials":[...]}` / 映射三种形态）；
  - `primary-material.json`、`secondary-material.json`：JATS-like 原始语料；
  - `corpus-manifest.json`：来源清单（role/doi/title 交叉核对依据）；
  - 可选 `secondary-publisher.xml`：旁挂文件，**只登记不解析**。
- 工作目录：`/app/work`（中间产物：normalized_corpus.json、verify_report.json）。
- 输出目录：`/app/output`，必须包含：
  - `result.json`：含 `case_id` 与 output_contract 声明的**全部原始键**
    （动态镜像精确键集合；无法产生的键置 null 并在 ledger 说明，绝不省略）；
  - `graph.json`、`graph.jsonl`、`queries.json`、`verify_report.json`、
    `ledger.json`（溯源台账）、`preview.dot`、可读的 `preview.svg`。

## 3. 角色分工：模型 vs 脚本

| 环节 | 执行者 | 说明 |
| --- | --- | --- |
| 语义抽取（节点/边/合并/冲突的候选） | **模型** | 产出 candidate extraction JSON（格式见 references/corpus-schema.md §4） |
| 语料发现与归一化 | 脚本 `normalize_input.py` | 容忍包装形态；缺失段落 id 自动编址；重复 id 登记为歧义 |
| 证据/归属/合并/覆盖度校验 | 脚本 `verify_evidence.py` | 只机械判定：引文精确子串、地址存在且唯一、根元数据归属 primary、merge/nonmerge 纪律、冲突保留、覆盖度统计 |
| 图谱构建 | 脚本 `build_graph.py` | 确定性排序、source_ids 冗余、统计只计数不臆造分数 |
| 查询执行 | 脚本 `query_graph.py` | neighborhood / by-type / path，遍历顺序确定，结果子图带完整证据 |
| 结果装配 | 脚本 `assemble_result.py` | 动态镜像 output_contract、生成 ledger/DOT/SVG；验证失败时诚实输出 partial |

**红线**：模型不得伪造引文（脚本会对每条 quote 做原文子串匹配）；
不得臆造分数或置信度；不得把不同条件/样本/数值合并成单一结论；
不得把“第 1 页”之类自制页码当作原始地址；内联公式一律线性化为文本。

## 4. 标准工作流（官方运行时）

```bash
# 0) 阅读 /input/task.md 与语料，模型完成语义抽取 -> /app/work/candidate_extraction.json
# 1) 语料归一化
python3 /skills/weekly-skill/scripts/normalize_input.py \
    --input /input --out /app/work/normalized_corpus.json
# 2) 严格校验（非零退出即存在硬错误，必须修正抽取后重跑）
python3 /skills/weekly-skill/scripts/verify_evidence.py \
    --corpus /app/work/normalized_corpus.json \
    --extraction /app/work/candidate_extraction.json \
    --out /app/work/verify_report.json
# 3) 建图
python3 /skills/weekly-skill/scripts/build_graph.py \
    --corpus /app/work/normalized_corpus.json \
    --extraction /app/work/candidate_extraction.json \
    --out /app/work/graph.json --jsonl /app/work/graph.jsonl
# 4) 查询（至少执行 3 条真实查询；优先执行 case.json 的 query_specs）
python3 /skills/weekly-skill/scripts/query_graph.py \
    --graph /app/work/graph.json --batch /input/case.json --out /app/work/queries.json
# 5) 装配（验证未过时也会如实生成 partial 结果并在 ledger 标记）
python3 /skills/weekly-skill/scripts/assemble_result.py \
    --case /input/case.json --corpus /app/work/normalized_corpus.json \
    --graph /app/work/graph.json --verify /app/work/verify_report.json \
    --queries /app/work/queries.json --out-dir /app/output
```

若验证失败且时间不足修正：仍执行第 5 步，`result.json` 以 `status=partial`
（或 ledger.honest_partial=true）如实披露，禁止交付静默错误结果。

## 5. CLI 速查

### normalize_input.py
- `--input DIR`：输入目录（官方为 `/input`）
- `--out FILE`：normalized_corpus.json 输出

### verify_evidence.py
- `--corpus FILE` / `--extraction FILE` / `--out FILE`
- 退出码：0 通过；2 存在 error（errors 数组含中文可读原因）

### build_graph.py
- `--corpus` `--extraction` `--out graph.json` `--jsonl graph.jsonl(可选)`

### query_graph.py（单条与批量）
- 单条邻域：`--query neighborhood --node n_method_fc --hops 1`
- 单条类型：`--query by-type --kind metric [--source-id S1]`
- 单条路径：`--query path --from n_paper_p1 --to n_paper_s1`
- 批量：`--batch case_or_specs.json --out queries.json`
  （接受裸查询列表、`{"queries":[...]}`、或含 `query_specs` 的 case.json）

### assemble_result.py
- `--case --corpus --graph --verify --queries --out-dir DIR`

## 6. 最小示例（SYNTHETIC，端到端可复现）

`examples/minimal/` 内含两篇**合成**论文语料（P1 primary、S1 secondary，
均带 SYNTHETIC 标识）、候选抽取、模拟 case.json/task.md。一条命令跑通全流程：

```bash
python3 scripts/run_minimal_example.py
```

产物写入 `examples/minimal/output/`：13 节点、10 边、1 条跨论文 merge
（freeze-casting 方法概念）、3 条显式 nonmerge（样品/孔隙率/烧结条件）、
1 条 preserved 冲突（20 vs 30 vol%）、2 条 unreported，4 条真实执行的查询
（结果子图含完整证据），以及 DOT 与纯代码生成的 SVG 预览。
该示例是合成的演示数据，**不构成任何官方赛题答案**。

## 7. 测试

```bash
python3 scripts/test_scripts.py
```

覆盖负例：引文不匹配、错源、段落张冠李戴、重复段落 id 歧义、缺证据、
同名节点对缺 nonmerge、数值不一致的 merge、边引用 merge member、
conflict 被消解、根元数据归属错误；正例：最小示例零 error、覆盖度 100%、
查询确定性与语义、装配器合同键精确镜像（未知键置 null 不省略）。

## 8. 进一步阅读

- `references/corpus-schema.md`：语料与抽取的 JSON 模式定义；
- `references/evidence-addressing.md`：证据编址规则与反例；
- `references/method-and-limitations.md`：方法说明与已知限制。
