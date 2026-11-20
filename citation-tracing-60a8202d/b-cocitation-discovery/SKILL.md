---
name: cocitation-parallel-discovery
description: 用共被引与文献耦合信号发现"不直接引用种子但属于同一方法脉络"的平行工作，每个候选附可复核的关联证据。当任务要求从种子论文出发找关联/平行文献、说明关联依据、并控制高被引噪声时使用；适用于 /input/case.json + task.md 的 Harbor 运行契约。
---

# 共被引／文献耦合平行工作发现（cocitation-parallel-discovery）

## 用途与适用条件

从种子论文出发，用**结构性关联信号**发现平行工作：共被引（与种子被同一批文献引用）、文献耦合（与种子共享参考文献），辅以作者重叠与期刊/主题词信号。候选按定义**排除**直接引用或被引种子的邻居（那些交给引文追踪）；每个候选都带产生它的具体施引文献/共享参考文献及其数据源定位。

不适用：直接引文边追踪（方向 1）、跨库身份合并（方向 5）、关键词检索。

## 输入

- `/input/case.json`：含 `case_id`、种子标识（DOI/arXiv/标题）、`output_contract`。
- 本地语料：组织方提供的 Crossref/EuropePMC/出版方响应与保留引用图（`.json/.jsonl/.csv/.tsv`），脚本自动发现于 `/input`、`./environment`、`/app/work`、当前目录。

## 调用方式

```bash
# 1. 发现
python3 scripts/codiscover.py --case /input/case.json --out /app/output --workdir /app/work
# 2. 自查（必须；失败项写入 result.json 的 uncertainty）
python3 scripts/verify_discovery.py /app/output /app/work
```

可选参数：`--top`（默认 40）、`--min-support`（结构信号最少条数，默认 1；噪声大时建议 2）、`--roots` 追加语料目录。

## 输出（/app/output）

- `result.json`：`case_id`、`status`、`seed`、`candidates`（每个含排名、元数据、`score` 与 `score_parts`、`association_evidence`：逐条共被引/耦合证据及定位）、`direct_neighbors`（排除说明）、`sources`、`evidence_records`、`uncertainty`，镜像 `output_contract` 全字段。
- `evidence_table.md`：人读排名表。运行日志 `/app/work/run_log.json`，自查报告 `/app/work/verify_report.json`。

## 关键方法（详见 rules/signal_spec.md）

1. **共被引（S1）**：凡引用种子的文献也引用候选 W，计一次共被引；得分用 Ochiai 归一（候选自身被引数已知时）或保守的 √n_citers 归一，抑制"高被引=高相关"假象。
2. **文献耦合（S2）**：候选与种子共享的参考文献数／两者参考文献并集（Jaccard），方法脉络的直接结构证据。
3. **次级信号（S3/S4）**：共享作者姓氏、共享显著主题词、同刊，只做加权微调（合计 ≤0.2/项），**单独不能**使候选入选——没有 S1 或 S2 的记录一律不入选。
4. **方向诚实**：共被引依赖"谁引用了种子"，本地库只给参考文献列表时用反向索引确定施引者；证据里同时记录"施引者引用种子处"与"施引者引用候选处"两个定位。
5. **空结果诚实**：达不到阈值时交付空候选集并注明"真实空结果"，不放宽标准凑数。

## 异常处理

| 情况 | 处置 |
|-|-|
| 种子未找到 | `status=partial`，`candidates=[]`，记录全部解析尝试 |
| 种子无施引记录（新预印本） | 仅靠耦合信号仍可产出；在 `uncertainty` 说明 S1 不可用 |
| 候选元数据缺失 | 保留标识与定位，缺失字段为 null，不推测 |
| 语料文件损坏 | 跳过并记录于 sources/uncertainty |
| 重复运行 | 确定性算法，同语料同参数输出一致 |

## 自查方法

`verify_discovery.py` 检查：候选均非种子直接邻居、均有结构信号与定位、得分=分项和、排名单调、定位文件存在。失败项如实写入 `uncertainty`。

## 最小调用示例

见 `examples/example_walkthrough.md`（合成数据，**非正式案例结果**）。
