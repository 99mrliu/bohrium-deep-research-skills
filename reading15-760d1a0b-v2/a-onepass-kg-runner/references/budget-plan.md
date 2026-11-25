# 预算计划与降级策略（64 次模型请求 / 900 秒 / 16K tokens）

本 bundle 的设计目标：**让 harness agent 以最少模型请求跑完全程**。
全部机械工作（发现、校验、建图、查询、装配、渲染、报告）由
`scripts/kg_run.py` 完成；模型只写**一个文件** `extractions.jsonl`。

## 请求预算分配（建议 ≤ 3 次）

| # | 请求 | 内容 | 可否省 |
|---|------|------|--------|
| 1 | 读入+抽取 | 读 `/input/task.md`、两篇 material 与 `case.json`，一次性写出 `/app/work/extractions.jsonl`（可先 `--seed` 之外的方式直接写） | 不可省 |
| 2 | 修复（可选） | 看 `verify_report.json` 的 quarantine，**只补写**出错行（追加新行即可） | 时间紧可省 |
| 3 | 终检（可选） | 快速浏览 `result.json` 与 `run_report.json` | 可省 |

脚本侧耗时为秒级，900 秒预算几乎全部由这一次抽取的写作时间构成。

## 按剩余时间的降级路线

1. **时间充裕（>50%）**：正常单文件抽取；每篇论文尽量覆盖摘要/方法/结果；
   冲突、alias、同名陷阱、unreported 全部写出。
2. **中等（20–50%）**：先保证 `node`/`edge` 主干（实体+关系+证据三元组）；
   `merge`/`nonmerge` 优先写跨篇 alias 与同名陷阱（评分点）；`note` 全省。
3. **紧张（<20%）**：只写每篇最核心的 claim 节点与 `contradicts` 冲突边 +
   1 条 `unreported`；即使如此也要保持**引文逐字符精确**（否则 verify 必拒）。
   `query`/`assemble` 永远自动执行，不会增加请求。
4. **extractions 完全没写成**：`kg_run.py all` 仍会写出诚实的
   `status=partial/unable` 的 `result.json`（合同键动态镜像，缺失置 null），
   平台至少拿到结构化交代而非空白。

## 快速重跑 / 断点续跑

- 每个阶段写 `/app/work/checkpoint_<stage>.json`；重跑时已有 checkpoint
  的阶段自动跳过（`--force` 强制重算）。
- 修复抽取后只需：`kg_run.py verify --force && kg_run.py build --force
  && kg_run.py query --force && kg_run.py assemble`（apply 会自动重读
  变更后的 jsonl，`--force` 全套最保险）。
