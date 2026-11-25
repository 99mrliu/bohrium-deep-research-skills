---
name: refgraph-snowball-engine
description: 方向感知的多跳雪球引文追踪引擎。当任务要求从种子论文出发沿后向参考文献与前向施引文献做多层级扩展（citation tracing / snowballing / 关联文献发现），且输入为本地语料（Crossref/EuropePMC/OpenAlex 风格 JSON、JSONL、CSV/TSV 边表、edgelist、BibTeX）时触发。先建图、再分层 BFS 追踪（含分支剪枝与停止判据）、最后机器自查；离线、纯标准库。
---

# refgraph-snowball-engine：方向感知多跳雪球追踪

## 必须先按此顺序执行（三命令管线）

```bash
# 1) 建图：递归扫描语料根，规范化记录，构建有向引用图（含前向边反向恢复）
python3 scripts/refgraph.py --roots /input --workdir /app/work

# 2) 追踪：读 graph.json + case.json + task.md，分层 BFS 雪球扩展（剪枝全程记日志）
python3 scripts/snowball.py --case /input/case.json --task /input/task.md \
    --workdir /app/work --out /app/output \
    --max-depth 3 --max-nodes 250 --max-branch 40 --classic-citedby 1000

# 3) 自查：方向一致性、locator 门禁、契约镜像校验；必须输出 ok=true
python3 scripts/verify_trace.py --graph /app/work/graph.json \
    --result /app/output/result.json --trace /app/output/trace_graph.json \
    --case /input/case.json
```

顺序不可颠倒：snowball.py 依赖 refgraph.py 产出的 `<workdir>/graph.json`；
verify_trace.py 依赖前两步的全部产物。脚本位置无关（pathlib + argparse），
只用 Python 3 标准库，默认完全离线。

## 运行契约

- 输入：`/input/case.json` + `/input/task.md`；组织方材料可能在 `/input` 的子目录。
- 工作目录 `/app/work`：`graph.json` 落在此处。
- 最终交付 `/app/output/result.json`：含 `case_id`、诚实 `status`
  （ok/partial/failed）、`seed`（含全部解析尝试记录）、`candidates`、`edges`、
  `layers`、`pruning_log`、`stop_log`、`sources`、`evidence_records`、
  `uncertainty`，并**逐字段镜像** case.json 的 `output_contract` 全部字段
  （填不了的字段置 null 并在 uncertainty 说明，不允许丢字段）。
- 同目录另产出 `trace_graph.json`（带层级/方向标注的追踪子图）。
- 预算意识：900 秒 / 64 次模型请求。三命令管线是确定性的，一次跑完；
  若 snowball.py 返回 failed/partial，**先保留这份 honest partial 结果**，
  再视预算调整参数（如放宽 --max-branch、去掉 --year-min）重跑第 2、3 步。
- 来源定位：每条记录、每条边都带 `sources: [{file, pointer}]`，可回指复核。

## 输入

| 输入 | 位置 | 说明 |
|---|---|---|
| 语料文件 | `--roots` 指定根（可重复）；默认 `/input`、`/app/work`、cwd 中存在的 | 递归扫描 `.json/.jsonl/.csv/.tsv/.edgelist/.bib` |
| case.json | `--case`，默认 `/input/case.json` | 提供 case_id、种子（多字段鲁棒解析）、output_contract |
| task.md | `--task`，默认 `/input/task.md` | DOI 正则兜底找种子；提取关键词用于相关性剪枝 |

可解析格式：Crossref（`message.items`/单条 `message`）、EuropePMC
（`resultList.result`）、OpenAlex（`results`/`id`+`referenced_works`）、
通用"节点含 references/citations 列表"JSON、通用边表（source/target 等列名）、
edgelist（`citing cited` 每行一对）、BibTeX（仅节点）。

## 参数表（snowball.py）

| 参数 | 默认 | 含义 |
|---|---|---|
| `--max-depth` | 3 | BFS 最大层深 |
| `--max-nodes` | 250 | 全局节点预算（耗尽即停，记 stop_log） |
| `--max-branch` | 40 | 每个父节点、每个方向的分支上限（经典豁免） |
| `--year-min` | 无 | 早于此年份者剪除（被引≥阈值的经典豁免） |
| `--classic-citedby` | 1000 | 奠基经典判定的被引提示阈值 |
| `--graph` | `<workdir>/graph.json` | 上一步产图路径 |

refgraph.py 参数：`--roots`（可重复追加）、`--workdir`（默认 /app/work）。
verify_trace.py 参数：`--graph --result --trace --case`（默认值适配契约路径）。

## 输出

- `/app/work/graph.json`：nodes（规范化记录，含 stub 标记）+ edges（方向、语义、
  direction_restored、来源定位）+ stats + registry（逐文件解析状态注册表）。
- `/app/output/result.json`：见"运行契约"。
- `/app/output/trace_graph.json`：追踪子图（节点带 layer/directions/stub/classic）。
- 三个脚本均向 stdout 打印一行 JSON 摘要；verify_trace.py 末行 `ok=true|false`。

## 关键方法

1. **建图与身份合并基线**：DOI 规范化（小写、去 resolver 前缀）精确匹配 +
   标题规范化（小写、去标点、坍缩空白）匹配；两键皆缺者保持独立。解析不出的
   引用目标保留为 stub（只有原始指针与定位，绝不补造元数据）。
2. **方向语义**：reference 边 = citing→cited（backward）；citation 边 =
   cited→citing（forward）。只给参考文献列表的数据源，用全语料反向索引恢复
   前向边并标 `direction_restored: true`。详见 references/direction_semantics.md。
3. **方向感知 BFS**：同一层内，后向分支沿 references、前向分支沿 citations
   同时扩展；逐层记 layers 统计。
4. **剪枝流水线**（决策全部写 pruning_log，含保留/剪除）：年份下限（经典豁免）→
   任务关键词相关性（零重叠剪除，stub 与经典豁免）→ 分支上限（经典豁免）→
   全局节点预算。规则全文见 references/traversal_policy.md。
5. **停止判据**（写 stop_log）：层深上限、节点预算耗尽、或整层零新增。

## 异常处理表

| 异常 | 行为 |
|---|---|
| 单个语料文件解析失败 | 记入 graph.json 的 registry（format/status/error），继续扫描其余文件，不中断 |
| case.json 缺失/不可读 | status=failed 或 partial，uncertainty 说明；仍写出 result.json 骨架 |
| task.md 缺失 | 关键词剪枝自动停用（视为全通过）并在 uncertainty 声明 |
| 种子解析不到 DOI | seed.parse_attempts 记录全部尝试；status=failed，stop_log 记 no_seed |
| 种子在图中无节点 | 尝试标题键匹配；仍无则 status=failed，不编造种子 |
| 引用目标不在语料 | 保留为 stub 节点（仅 locator），pruning_log 记 kept_stub |
| 数据源无前向引用 | 反向索引恢复，边标 direction_restored:true，并在 uncertainty 提示其可靠性边界 |
| 预算/深度触顶 | stop_log 记 node_budget / depth_limit，uncertainty 说明未探索部分 |

## 自查方法

跑第 3 条命令 `verify_trace.py`：校验每条边有 source.file（locator 门禁）、
方向一致（无既 forward 又 backward 的矛盾边、forward 边在图中有 backward 镜像）、
无悬空/不可达节点、result.json 含 case_id 且镜像 output_contract 全字段、
层级统计自洽、status 诚实。输出 `ok=true`（退出码 0）方可交付；
`ok=false` 时按 defects 清单逐项修复后重跑。

## 最小示例指引（合成示例 / SYNTHETIC）

`examples/` 内置 8 篇虚构文献（DOI 形如 `10.0000/synth.*`，**非真实论文**）：

```bash
python3 scripts/refgraph.py --roots examples/corpus --workdir examples/run_out
python3 scripts/snowball.py --graph examples/run_out/graph.json \
    --case examples/case.json --task examples/task.md \
    --out examples/run_out --workdir examples/run_out \
    --max-depth 4 --max-branch 2 --year-min 2000 --classic-citedby 1000
python3 scripts/verify_trace.py --graph examples/run_out/graph.json \
    --result examples/run_out/result.json --trace examples/run_out/trace_graph.json \
    --case examples/case.json
```

该示例演示：三层扩展、关键词剪枝、分支上限剪枝、奠基经典例外、stub 保留、
前向边反向恢复（direction_restored:true）、整层零新增停止。详解见
examples/walkthrough.md；`examples/run_out/` 保留了该合成示例的真实运行产物。

## 限制

- 仅离线遍历本地语料：语料里没有的引用关系无法发现（结果受语料覆盖度限制，
  已在 uncertainty 声明）；不提供共被引/文献耦合等间接关联信号。
- 反向恢复的前向边只断言"某记录在参考文献中提及目标"，不等于目标被正式施引
  索引收录；可靠性讨论见 references/direction_semantics.md。
- 关键词相关性为词面子串匹配，不做语义理解；主题边缘文献可能被误剪
  （pruning_log 可复核）。
- 身份合并只做 DOI/标题双键基线；预印本-期刊版等跨版本合并不在本 Skill 范围。
