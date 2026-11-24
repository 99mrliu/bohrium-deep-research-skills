---
name: replayable-increment-ledger
description: >-
  增量证据链与逐字节回放。适用场景：案例材料中包含本地固化的文献题录响应
  （Crossref / Europe PMC / arXiv / 出版商 API 的 JSON）、上一轮的增量导入状态
  （previous snapshot / 已有 journal），要求给出本轮新增清单、预印本→正式版版本链、
  跨源去重结论，并且每一项判定都必须可回放、可复核。差异化能力：append-only
  increment_journal.jsonl 记录 run_id、UTC 窗口、per-source 水位、每条判定的
  locator（文件+JSON路径+文件sha256）与命中规则、每条投递的 delivery_hash；
  replayer 从 journal+previous_snapshot 重放任意一轮并做逐字节 diff；
  idempotency_check 证明同轮重跑零新事件、零二次投递。边界：不做源完整性校验、
  不做窗口规划与补抓调度、不做重试退避编排、不做 QA 评分；完全离线，永不发起
  网络请求，绝不编造 DOI 或元数据。
---

# replayable-increment-ledger：增量证据链与逐字节回放

## 1. 适用场景与边界

**适用**：

- 输入是**本地固化**的题录响应 JSON（Crossref `message.items`、arXiv Atom
  转 JSON 的 `entries`、Europe PMC `resultList.result` 等形态均可宽容解析）；
- 存在或可推导“上一轮状态”（previous_snapshot.json、已有的
  increment_journal.jsonl，或案例材料中的增量导入状态快照）；
- 任务要求：本轮哪些文献是新增 / 哪些是重复 / 哪些是版本更新（预印本→正式版、
  arXiv vN→vN+1），且结论必须带证据、可复核、可回放。

**边界（本 skill 不做）**：

- 不做源数据本身的完整性/真伪校验（只记录 sha256 指纹，不评判来源可信度）；
- 不做窗口规划、补抓调度、抓取频率决策（窗口起止从 case.json 或材料中读取）；
- 不做网络重试与退避编排（完全离线，脚本永不联网）；
- 不做结果质量的 QA 打分（只交付可回放的事实清单与 diff 结论）。

**红线**：任何字段值必须来自案例材料；每个新增/更新判定必须给出
`locator = {file, json_path, file_sha256}`；缺失的信息写进 `uncertainty`，
绝不臆造 DOI、日期或检索结果。

## 2. 运行环境与输入定位兜底

- 仅需 Python3 标准库；脚本之间通过文件通信，不产生任何网络请求。
- **不假设固定目录布局**。先用 `find` 定位输入（工作目录通常为 /app/work，
  输出目录 /app/output，但必须以实际定位为准）：

```bash
find /input /app /workspace . -maxdepth 4 -name 'case.json' 2>/dev/null
find /input /app /workspace . -maxdepth 4 -name 'task.md' 2>/dev/null
# 材料与历史状态：按实际文件名 glob，常见关键词如下
find /input /app /workspace . -maxdepth 5 \( -name '*snapshot*' -o -name '*journal*' \
     -o -name '*crossref*' -o -name '*europe*pmc*' -o -name '*arxiv*' \
     -o -name '*response*' -o -name '*material*' \) 2>/dev/null
```

- 先读 case.json：确认 `case_id`、`output_contract` 字段清单、窗口配置
  （`window` / `windows` / task.md 中的 UTC 时间）与告警渠道。
- 材料形态不一时，按内容而非文件名判断源类型：含 `message.items` 视为
  crossref 形态；含 `entries` 视为 arxiv 形态；含 `resultList.result` 视为
  europepmc 形态（脚本已内置宽容探测，`--source` 的 name 只作提示）。

## 3. 编号工作流程

> 确定性工作全部交给脚本；模型只负责读题、判断材料归属、检查输出与撰写结论。

1. **定位与读题**：用第 2 节的 find 定位 case.json / task.md / 材料 / 历史状态；
   读取 case.json 的 `case_id` 与 `output_contract`，确定本轮窗口
   `[window_start_utc, window_end_utc)`。
2. **准备账本**：在 /app/work 建立工作区。若材料中已有 journal 快照，
   复制为工作用 `increment_journal.jsonl`（append-only，绝不改写已有行）；
   若无则新建空文件。同理准备 `snapshot_prev.json`（无则省略 `--snapshot-in`，
   等价于空注册表起步）。
3. **执行本轮增量**（每个窗口跑一次）：

```bash
python3 scripts/record_run.py --case <case.json> \
    --window-start <UTC起> --window-end <UTC止> \
    --source crossref=<题录响应A.json> --source arxiv=<题录响应B.json> \
    --journal increment_journal.jsonl \
    --snapshot-in snapshot_prev.json --snapshot-out snapshot_new.json \
    --run-summary run_summary.json
```

   输出：journal 追加一条 run 记录（含 run_id、窗口、水位、每条判定的
   locator/规则、投递哈希），`snapshot_new.json` 推进水位与注册表，
   `run_summary.json` 给出 counts 与事件清单。**从 summary 抄下 run_id**。
4. **回放验证**：对本轮（以及需要复核的历史轮）执行：

```bash
python3 scripts/replayer.py --journal increment_journal.jsonl \
    --run-id <run_id> --snapshot snapshot_prev.json \
    --source crossref=<A.json> --source arxiv=<B.json> \
    --case <case.json> --out replay_diff.json
```

   期望 `status=consistent`、`byte_equal=true`；不一致时按
   references/replay-verification.md 第 3 节排查，禁止跳过。
5. **幂等校验**：

```bash
python3 scripts/idempotency_check.py --case <case.json> \
    --window-start <UTC起> --window-end <UTC止> \
    --source crossref=<A.json> --source arxiv=<B.json> \
    --journal increment_journal.jsonl --snapshot-in snapshot_prev.json \
    --out idempotency_report.json
```

   期望 `status=pass`：重跑零追加、零新事件、零二次投递。
6. **组装 result.json**：

```bash
python3 scripts/assemble_result.py --case <case.json> \
    --journal increment_journal.jsonl \
    --run-summary run_summary.json [--run-summary 更早轮次...] \
    --replay-diff replay_diff.json [--replay-diff ...] \
    --idempotency idempotency_report.json \
    --snapshot-prev snapshot_prev.json --snapshot-new snapshot_new.json \
    --out /app/output/result.json
```

7. **模型终检**（不可省略）：读 result.json，核对——`case_id` 与 case.json
   一致；`output_contract` 每个字段都已填充（无法判定的为 null 且
   uncertainty 有说明）；每条 new_items/version_updates 都带 locator；
   `replay_verification.status` 与 `idempotency_verification.status` 与
   报告文件一致。发现矛盾先回到对应脚本重跑，禁止手改 result.json 掩盖。

## 4. 输出契约（result.json）

必须写入 **/app/output/result.json**（路径以平台约定为准）。字段：

- `case.json` 的 `output_contract` 列出的**全部字段**（有映射则填实值，
  无映射填 null 并在 uncertainty 说明）；
- `case_id`：与 case.json 完全一致；
- `status`：`complete` / `partial`；
- `sources`：全部输入材料与关键产物 `{file, role, sha256}`，事件级证据另见
  各清单项内的 `locator`；
- `uncertainty`：字符串数组，列出判重局限、字段缺失、粒度差异等；
- `change_records`：本轮全部变更——`seen_items` 的 add/update（含规则与
  locator）、per-source 水位 before→after、journal 追加记录。

典型字段（合成示例的 output_contract 即采用此集合）：
`window`、`new_items`、`version_updates`、`duplicates`、`deliveries`、
`journal_ref`（path+sha256+run_ids）、`replay_verification`、
`idempotency_verification`。

## 5. 异常处理与诚实 partial

- **材料缺失/不可解析**：`extract_items` 返回空数组时该轮 counts 全 0，
  继续执行并在 uncertainty 记录“未能在 <file> 中定位题录数组”；
  不要把字段留白充当成功。
- **日期无法解析**：该条记 `skipped / RX-no-date`，计入 counts，不进清单。
- **回放不一致 / 幂等失败**：result.json 必须 `status=partial`，并在
  uncertainty 中引用 replay_diff.json / idempotency_report.json 的具体
  mismatch 字段；禁止声称一致。
- **output_contract 出现未知字段**：填 null + uncertainty 说明，不猜值。
- **部分完成**：完成了记录但未完成回放等情形，`status=partial`，
  在 uncertainty 写明已完成与未完成的环节及原因。

## 6. 最小调用示例说明

`examples/minimal/` 为**合成示例**（数据全部虚构并标注 synthetic）：
两个源（crossref、arxiv）两轮窗口，第 2 轮刻意包含 1 条新增、1 条 arXiv
版本更新、1 条预印本→正式版版本链、2 条跨源重复（DOI 大小写差异、标题
大小写/标点差异）。在 bundle 根目录一键运行：

```bash
python3 scripts/run_minimal_example.py
```

自动完成：第 1 轮建账 → 第 2 轮增量 → 回放两轮 → 幂等校验 → 组装
`examples/minimal/output/result.json`，末行打印 `OVERALL: PASS/FAIL`。
真实案例求解时按第 3 节逐步执行同一组脚本即可。

## 7. 与其他方向的边界划分

| 邻近方向 | 归属 | 本 skill 的接口 |
|---|---|---|
| 源完整性校验（签名、证书、可信源分级） | 其他方向 | 本 skill 只记录文件 sha256 指纹供其核对 |
| 窗口规划与补抓调度 | 其他方向 | 本 skill 消费给定窗口，不决定窗口 |
| 抓取重试/退避编排 | 其他方向 | 本 skill 完全离线，无网络交互 |
| 结果 QA 评分 | 其他方向 | 本 skill 交付事实清单 + replay/idempotency 结论作为评分输入 |

## 8. 脚本与文档索引

- `scripts/journal_lib.py`：规范化、dedup_key、判定规则、process_run 纯函数核心；
- `scripts/record_run.py`：执行一轮并追加 journal（幂等）；
- `scripts/replayer.py`：逐字节回放任意一轮 → replay_diff.json；
- `scripts/idempotency_check.py`：同轮重跑零新事件/零二次投递证明；
- `scripts/assemble_result.py`：组装 result.json；
- `scripts/run_minimal_example.py`：合成示例一键端到端；
- `references/dedup-key-rules.md`：dedup_key 优先级链与判定规则全表；
- `references/journal-schema.md`：journal / snapshot / event / delivery 模式；
- `references/replay-verification.md`：回放算法、diff 语义与排查指引。
