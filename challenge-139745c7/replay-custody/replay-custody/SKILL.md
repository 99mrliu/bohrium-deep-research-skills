---
name: replay-custody
description: 过程质量控制方向。把检索全过程放进可复核的保管链：只增不改的哈希链日志记录每一步操作与产物摘要；每条结论先登记证据卡（文件+sha256+逐字引文+字符区间），独立核验门逐字比对，核验不过的论断机器强制拦下、禁止进入答案；result.json 过契约检查器（case_id 一致、output_contract 字段齐全、status 合法）；并自动生成 REPLAY.md 使第三方可用同一命令序列重放并复核到同一段。当任务强调"过程可复核、引用可逐字验证、别人能按记录复核到同一段"时使用；输入为 /input/case.json + task.md + 文档库。
---

# replay-custody：检索过程的质量控制与保管链

## 重心

"答案对"与"能证明答案对"是两回事。本技能给检索加三道**机器门槛**，
不依赖 Agent 自觉：

1. **保管链日志**（journal）：每次操作追加一条带 `prev_hash` 的记录，
   篡改任何一步都会断链。
2. **证据核验门**（gate）：结论的 `quote` 必须是所引文件抽取文本的
   **逐字子串**，且文件 sha256 与登记一致；fail 的 claim 被拦下。
3. **契约检查**（contract）：result.json 必须含 case_id 且与 case.json
   一致、output_contract 字段齐全、status 取值合法。

## 运行契约（必须遵守）

1. 先读 `/input/case.json` 与 `/input/task.md`：记录 `case_id`，照抄
   `output_contract` 全部字段；库路径与提问以实际键名为准，找不到就
   `ls -R /input` 盘点。**不凭文件名猜内容。**
2. **立刻**写 `/app/output/result.json` 骨架（case_id + 全字段占位 +
   `"status":"partial"`），随后逐步填充。
3. 中间产物 `/app/work`，交付 `/app/output`；`$S` 为技能安装目录
   （通常 `/skills/weekly-skill`）。Python ≥3.9 标准库，不装第三方包；
   PDF 抽取用本机 `pdftotext`，缺失时该文件记 `no_pdf_tool`。

## 执行步骤（顺序不可调换：先过门，再交卷）

```bash
S=/skills/weekly-skill
mkdir -p /app/work /app/output
# 1. 建保管链并执行检索：每个论断登记证据卡，操作全程入链
python3 "$S/scripts/custody_run.py" /input/case.json /app/work
# 2. 核验门：逐字比对所有证据卡，fail 的论断拦下 → verified_answers.json
python3 "$S/scripts/custody_gate.py" /app/work /app/work/verified_answers.json
# 3. 组装 result.json 并过契约检查器；不过则修复后重跑本步
python3 "$S/scripts/custody_contract.py" /input/case.json /app/work /app/output/result.json
# 4. 封印保管链，生成 REPLAY.md（第三方重放说明）
python3 "$S/scripts/custody_journal.py" seal /app/work /app/output/REPLAY.md
```

契约检查器退出码非 0 时，**不得直接提交**：按报告修复 result.json 后
重跑第 3 步；确实无法修复的字段置 null 并在 uncertainty 说明。

## 证据卡格式

```json
{"claim": "缓冲液配方为 25 mM HEPES pH 7.4",
 "file": "开题报告_终稿_2023-06-15.md", "sha256": "<全库登记值>",
 "quote": "缓冲液配方（修订）：25 mM HEPES pH 7.4",
 "char_start": 88, "char_end": 118}
```

核验门规则（详见 references/qc-protocol.md）：quote 逐字出现在该文件
抽取文本内；char 区间与 quote 一致（若提供）；sha256 与现文件一致。
三项任一不过 → claim 拦截，写入 `rejected` 并说明原因。

## 异常处理

| 情况 | 处置 |
|-|-|
| 证据卡核验失败 | 拦截该论断，answers 中记 `rejected_claims`，不静默改写 |
| 文件在登记后被改动 | sha256 不一致 → 全部相关 claim 拦截并报警 |
| 提问无命中 | `no_found` 记录检索词与覆盖文件数，不虚构证据 |
| 契约检查不过 | 修复或置 null + uncertainty；不得绕过检查器 |

## 最小示例

`examples/` 为**合成示例**（含一个正确引文与一个故意改写的引文，演示
核验门拦截后者），运行 `python3 run_example.py`，预期见
`examples/README.md`。

## 限制

- 本技能保证过程与证据质量；语义召回率非其重心。
- 哈希链防的是事后抵赖，不防运行期恶意篡改环境。
- 不做开放网络检索。
