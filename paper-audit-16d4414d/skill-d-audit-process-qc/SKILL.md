---
name: audit-process-qc
description: >-
  论文逻辑与论证审查的过程质量控制引擎。当任务是审查 /input 中的科研论文（case.json + task.md + PDF/文本材料）且需要在 64 次模型请求 / 900 秒预算内产出可复核结果时使用。核心立场：本题七类高频失败里有三类（截断仍宣称全文审查、只有最终报告没有过程记录、严重度/结论随运行漂移）根因不在判断力而在过程管理。scripts/runqc.py（纯标准库、零依赖）提供：原子化 result.json 骨架与增量检查点（任何中断都留下诚实半成品）、覆盖台账（每个检查项 examined/pending/skipped/unchecked，跳过必须给理由）、预算安全网（40/56 阈值告警）、复跑一致性 diff（STABLE/DRIFT，无法解释的漂移降级为待复核）、finalize 诚实门禁（存在未检查项时禁止 success 状态、契约字段缺失拒收）。它不替你审论文，它让你的审查可被评审复核。不适用：文字润色、查重、参考文献格式、原始数据复算。
---

# audit-process-qc：审查过程质量控制

## 定位

本 Skill 的重心在**过程层**：不规定你怎么判断论文，而是保证你的判断过程留下可复核的证据链，且任何时刻中断都有诚实的交付物。五道机制：

1. **原子检查点**：result.json 从第 0 分钟就存在（骨架），之后每次写入都是原子替换（tmp+rename），不存在写一半的 JSON。
2. **覆盖台账**：task.md 的每个检查项登记为 examined/pending/skipped/unchecked；skipped/unchecked 必须给理由——"没做"和"做了没问题"分得清清楚楚。
3. **预算安全网**：64 次请求的 40/56 阈值告警；到 56 次强制收尾，杜绝"预算耗尽、磁盘上什么都没有"。
4. **复跑一致性**：同案例重复运行的 findings diff（STABLE/DRIFT）；DRIFT 必须逐条解释，解释不了的 finding 降级待复核。
5. **finalize 诚实门禁**：交付前校验 case_id 一致、output_contract 字段齐全、存在未检查项时 status 不得为 success、journal 检查点足够。门禁不过（exit=5）不得交付。

## 固定路径与运行契约

- 引擎：`/skills/weekly-skill/scripts/runqc.py`（下文 `$QC`，Python ≥3.8，纯标准库）
- 参考：`/skills/weekly-skill/references/runbook.md`（900 秒时间盒、检查点节奏、DRIFT 处置）
- 输入：`/input/case.json`、`/input/task.md`、论文材料；工作区 `/app/work`；交付 `/app/output/result.json`

## 执行协议

### 第 0 分钟：init（最先做，先于读论文）

```bash
python3 $QC init --work /app/work --output /app/output --case /input/case.json
```

骨架立即落盘：case_id、output_contract 全字段（占位 null）、status=in_progress。**从这一刻起任何中断都有诚实半成品。**

### 第 0–10 分钟：登记覆盖台账

把 task.md 的检查项逐条登记（examined 待做也先记 pending）：

```bash
python3 $QC coverage --work /app/work --item <检查项> --status pending
```

材料体检（PDF 无文本层/截断/缺章节）后，把不可检的项改为 skipped/unchecked 并给理由。

### 审查进行中：检查点节奏

每完成一个检查项：更新台账 + 落检查点（把已确认 findings 增量写进 result.json）：

```bash
python3 $QC coverage --work /app/work --item stats_report --status examined
python3 $QC checkpoint --work /app/work --output /app/output --stage stats-done \
  --field findings --value "$(cat /app/work/findings_so_far.json)"
```

每次调用工具/模型后心里计数，关键节点报账：

```bash
python3 $QC budget --work /app/work --requests <已用次数>
```

warn（40）停止开新检查线；critical（56）立即收尾，exit=6 是命令不是建议。

### 交付前：门禁

```bash
python3 $QC checkpoint --work /app/work --output /app/output --stage final --field status --value '"partial"'  # 有未检查项时
python3 $QC finalize --work /app/work --output /app/output
```

exit=5 时读 finalize_report.json 逐条整改。**有未检查项时 status 只能是 partial**；全部 examined 且无 pending 才能 success。

### 重复运行（平台三重复条件下）

把上一轮 findings 存为 /app/work/findings_prev.json，本轮结束后：

```bash
python3 $QC reruncheck --work /app/work --previous /app/work/findings_prev.json --current /app/work/findings.json
```

DRIFT 的每条 diff 写进报告"运行间差异说明"；无法解释的 DRIFT 对应 finding 降级 needs_review。

## 异常处理

| 情况 | 处置 |
|-|-|
| case.json 无 case_id | init 拒绝（exit=3）；不得手编 case_id |
| 预算到 critical | 立即 checkpoint 当前 findings + status=partial + finalize，停止新分析 |
| 中断/超时恢复 | result.json 与 journal 均在；从最后一个 checkpoint 继续，不重跑已完成项 |
| finalize 拒收 | 逐条整改 violations；禁止绕过门禁直接交付 |
| 复跑 DRIFT | 逐条解释；解释不了降级待复核 |

## 不适用

本 Skill 不做任何论文内容判断（那由你的审查方法完成）；不负责文字润色、查重、参考文献格式、原始数据复算。

## 最小示例

`examples/minimal/`（**合成示例，非正式案例**）：合成 case.json + 模拟一次带检查点的审查会话 + 两次运行的 findings（构造 DRIFT）+ 一次蓄意的 dishonest status 负面对照。`sh examples/minimal/run_example.sh` 真实执行：finalize 对 partial 放行（PASS）、对 success 拒收（exit=5）。产物在 `examples/minimal/outputs/`。
