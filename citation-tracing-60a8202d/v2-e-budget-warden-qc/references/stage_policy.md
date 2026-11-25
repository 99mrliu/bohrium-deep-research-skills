# 阶段划分、checkpoint 格式与预算降级规则

本文档是 warden.py 的方法学说明，面向需要理解或维护阶段策略的读者。

## 1. 阶段划分

| 阶段 | 名称 | 动作 | 落盘产物 | 设计理由 |
|---|---|---|---|---|
| stage0 | contract | 解析 case.json（case_id、seed、output_contract），立即写 honest partial result.json | result.json（partial，空候选）+ stage0 checkpoint | 平台可能在任意时刻收割产物；先交付骨架再迭代是预算治理的第一原则。即使后续全部失败，case_id + 契约镜像 + 诚实 uncertainty 也已可评。 |
| stage1 | ingest | 递归扫描候选根（`--roots` > /input > /app/work > cwd），嗅探 Crossref / EuropePMC / OpenAlex / 通用 JSON / JSONL / CSV / TSV / edgelist / bib，身份合并（DOI 规范化键 + 标题规范化键），写来源注册表（sha1、格式、记录数、解析成败） | stage1 checkpoint（含全部语料记录与裸边） | 语料格式与位置未知，必须先物化一份带 locator 的规范化语料，后续阶段才能纯离线、确定性重放。 |
| stage2 | shallow | 种子解析（DOI/标题键命中语料）+ 第 1 层 BFS 扩展（reference 边 citing→cited，反向索引恢复 citation 边并标 `direction_restored: true`） | 增强 result.json（status 仍 partial，注明仅 1 层）+ stage2 checkpoint（含图） | 第 1 层扩展性价比最高：即使预算耗尽于此后，"种子 + 一层邻居"已是可用的最小综述起点。 |
| stage3 | deepen | BFS 加深至 `--max-depth`（默认 2，建议 2–3），DOI/标题去重合并，候选/边/证据最终落盘 | 最终 result.json（ok 或诚实 partial）+ stage3 checkpoint（摘要 + result sha1） | 多层扩展是"顺藤摸瓜"的核心价值，但代价最高，放最后并在预算紧张时最先被降级。 |

## 2. checkpoint 格式

路径：`<workdir>/checkpoints/stage<N>.json`，UTF-8 JSON，sort_keys 序列化。

```json
{
  "stage": 1,
  "stage_name": "stage1_ingest",
  "finished_at": "ISO-8601 时间戳",
  "artifact_sha1": "对 data 字段确定性序列化后的 sha1",
  "data": { "…续跑载荷…" }
}
```

- `finished_at` 只存在于 checkpoint 与 run_log.json，**绝不进入 result.json**。
- 续跑载荷按阶段不同：stage0 存 case 摘要；stage1 存全量语料记录 + 裸边 + 来源注册表；
  stage2 存图边 + 一层候选；stage3 只存摘要与 result.json 的 sha1（终态确认）。
- `artifact_sha1` 用于目检与 QC：可核对 checkpoint 宣告的产物与实际文件一致。

## 3. 断点续跑规则

1. `--resume` 时扫描 checkpoints 目录，取最大已完成阶段号 `S`；
2. 从对应 checkpoint 载荷重建内存状态（语料、图、候选），跳过 stage0…S；
3. 从 stage S+1 继续执行；**因预算降级被跳过的阶段不写 checkpoint**，因此续跑时会
   重新尝试，降级不会造成永久性缺失；
4. stage3 checkpoint 已存在时续跑为空操作，直接报告管线已完成；
5. checkpoint 损坏（JSON 解析失败）时该文件被忽略，相当于回退到更早阶段续跑。

## 4. 预算降级规则

- 参数：`--time-budget`（默认 850 秒，对齐 900 秒平台预算留余量）、`--margin`
  （默认 30 秒安全余量）。
- 在进入 stage1 / stage2 / stage3 前检查 `剩余时间 > margin`，不满足则跳过该阶段及
  后续全部阶段，立即落盘当前最好版本，并在 `stage_summary` 标注
  `budget_limited: true`、在 uncertainty 说明跳过原因。
- 降级优先级：stage3（加深）最先牺牲，stage2（一层扩展）其次，stage1（ingest）最后；
  stage0 永不降级（成本为秒级以下）。
- 降级决策记录到 run_log.json，供 QC 与人工复核。

## 5. 确定性规则

1. 文件遍历：候选根内 rglob 结果按解析后的绝对路径字符串排序；
2. 记录迭代：按 `(doi, 规范化标题, record_id)` 稳定键排序；
3. 边迭代：按 `(source_id, target_id, type)` 排序；BFS 邻接表同键排序；
4. 候选列表：按 `(hop, 稳定键)` 排序；
5. JSON 序列化：`sort_keys=True`、`ensure_ascii=False`、缩进 2、末尾换行；
6. 时间戳、临时路径、环境信息一律只进 run_log.json / checkpoint，不进 result.json。

满足以上六条，重复运行（同输入、同参数）的 result.json 逐字节一致，由 reproduce.py
双跑校验兜底。
