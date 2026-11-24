# 第三方复跑协议（Replay Protocol）

本文档说明第三方如何仅凭交付物中的 `run_journal.jsonl` 与 `run_manifest.json`，独立复核整条深度研究路径。

## 复跑三件套

| 文件 | 作用 |
|---|---|
| `run_journal.jsonl` | append-only 运行日志，逐笔记录工具调用（参数、返回计数、内容哈希、状态） |
| `run_manifest.json` | 环境信息 + 输入/产物/skill 文件 SHA-256 清单 + 阶段时间线 |
| `replay_plan.json` | 由 `journal.py replay` 生成的复跑清单（可从 journal 重新生成，等价） |

## 复跑步骤

### 第 1 步：校验账本哈希链

```bash
python3 scripts/journal.py verify --journal run_journal.jsonl
```

exit 0：账本自洽（无篡改、无缺笔、无插入）。exit 1：stdout 逐项列出断链 seq，复核终止——账本已不可信，研究路径不可复跑。

### 第 2 步：按复跑清单重放检索

```bash
python3 scripts/journal.py replay --journal run_journal.jsonl
```

对清单中每一笔（跳过 genesis）：

1. 以相同 `tool` 与 `args` 重放调用；
2. 对重放返回的原始内容计算 SHA-256，与 `expect_results_digest` 比对；
3. 比对返回条数与 `expect_results_count`；
4. 对 `empty` / `failed` 笔，确认重放时的真实语义一致（例如原笔记 `empty`，重放若命中大量结果，说明环境/语料已变化，而非原记录造假——见"复跑差异处置"）。

### 第 3 步：比对清单与产物哈希

```bash
python3 scripts/manifest.py verify --manifest run_manifest.json
```

重算输入与产物文件哈希并与清单比对。exit 0：交付产物与记账时一致；exit 1：stdout 指出哪个文件被改/缺失/新增。

### 第 4 步：覆盖率交叉核对

用 `journal.py stats` 的输出对照 `result.json` 的检索覆盖区块：每子问题的检索角度数、命中数应可追溯到账本中的对应笔。`empty` 角度应在 result.json 的 uncertainty/研究空白区块中如实出现。

## 哈希链构造（伪码）

```
GENESIS_PREV = "0" * 64
canonical(obj) = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

entry[0]  = {seq: 0, tool: "genesis", ..., prev_digest: GENESIS_PREV}
entry[i].prev_digest   = entry[i-1].entry_digest
entry[i].entry_digest  = SHA256( entry[i].prev_digest
                                 + canonical({seq, tool, args,
                                              results_count, results_digest,
                                              status, note}) )
```

校验：逐笔检查 `seq == 行号`、`prev_digest` 与上一笔衔接、`entry_digest` 重算一致。任一不满足即断链，报首个断点 seq。

## 不参与哈希的字段及理由

| 字段 | 是否参哈希 | 理由 |
|---|---|---|
| `seq` / `tool` / `args` / `results_count` / `results_digest` / `status` | 参与 | 复跑比对的全部依据 |
| `note` | 参与 | 失败原因与降级决策是审计内容，不允许事后改写 |
| `ts`（时间戳） | **不参与** | 时钟不可信且不可复现；复跑者无法重放出相同时间戳，纳入哈希会使复跑校验必然失败。时间顺序由 seq 与哈希链保证，时间戳仅供阅读参考 |
| `entry_digest` / `prev_digest` 自身 | 派生 | 由上述字段确定性推出 |

manifest 中同理：`generated_at`、`phase_timeline` 的时间戳仅供阅读，校验只看文件哈希。

## 复跑差异的处置

| 差异类型 | 判定 | 处置 |
|---|---|---|
| 哈希链断链（verify exit 1） | 账本被事后改动 | 复核失败，要求原始运行方说明 |
| `results_digest` 不一致但链完整 | 语料/索引更新、工具版本差异 | 非造假：记录差异，按重放结果重新评估结论确信度 |
| `results_count` 减少、原 ok 变 empty | 来源下线/撤稿 | 在复核报告中标注来源可得性风险 |
| manifest verify exit 1 | 交付产物在记账后被改 | 以 manifest 点名文件为准，要求重跑对应阶段 |
| `failed` 笔重放成功 | 原失败为瞬时故障（限流等） | 正常；原 note 中的降级决策仍然成立且可审计 |
