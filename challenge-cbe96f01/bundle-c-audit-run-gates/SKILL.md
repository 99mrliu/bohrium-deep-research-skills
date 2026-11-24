---
name: audit-run-gates
description: 引用与事实核验的"过程质量控制"门控协议。当任务要求对论文或科研材料做审查并要求结果可复核、可复现、中断可恢复时使用。核心立场：审查结论的可信度来自过程——换一个人按记录复核能否得到同一批结论。机制：把审查流水线切成五个带门控（G1–G8）的阶段，每道门由 stdlib 脚本机器校验（case_id 存在、output_contract 字段齐全、六类覆盖状态合法、finding schema 完整、摘录逐字落在原文页内、状态诚实一致、运行日志齐备、确定性产物重放一致），任何一道门不过则不许进入交付；所有中途产物按checkpoint落盘，预算耗尽或中断时从最近checkpoint恢复并诚实标注 partial。脚本：ingest.py、anchor_index.py、gate_check.py、replay_diff.py。
---

# audit-run-gates：门控式可复核审查流水线

## 1. 定位与核心立场

本题的第三条成败标准是"**换一个人按记录复核能否得到同一批结论**"。多数 Agent 的审查过程是单体的：读完就写报告，结论不可分解、不可重放、中断即报废。本 Skill 的重心在**过程质量控制**：审查内容（六类问题的判断）交给 Agent 的专业判断，但**每一阶段的产出都必须通过机器门控才能进入下一阶段**，门控记录本身就是复核依据。

与"内容型"Skill 的分工：本 Skill 不规定某类问题怎么判（那是判定规则的事），它规定**任何判定在交付前必须满足的可验证属性**——位置真实、字段齐全、状态诚实、产物可重放。

## 2. 适用条件与不适用范围

适用：任何"发现问题+给出证据"的审查任务，尤其适合长文档、多轮次、有中断风险（预算/超时）的运行环境。不适用：论文润色、综述写作、数据分析建模。

## 3. 运行契约（Harbor）

- 输入 `/input/case.json`、`/input/task.md`；工作目录 `/app/work`；交付 `/app/output/`。
- `result.json` 含 `case_id` 与 case.json `output_contract`（或 `outputContract`/`outputs`）声明的全部字段——逐字段同名复制填充，无法填充的置 `null` 并记入 `uncertainties`。
- 预算 64 次模型请求 / 900 秒 / 单次响应 ≤16384 token。**checkpoint 纪律**：每个阶段结束立即写 `/app/work/checkpoints/<stage>/`，任何时刻被中断都能从最近 checkpoint 恢复；恢复点与恢复动作写入运行日志。
- partial 必须诚实：`status="partial"` 时 `unchecked_items` 逐项写明缺什么、为何缺、补做路径；禁止把未做的事写成已做。

### 防御式输入解析

1. `case_id`：尝试 `case_id`/`id`/`caseId`；取不到用文件名并记入 `uncertainties`。
2. 材料：尝试 `paper`/`pdf`/`material`/`document`/`file`/`manuscript`（含一层嵌套）；否则 `/input/` 下按 `*.pdf → *.txt → *.md → *.html` 取第一个。
3. `task.md` 具体要求优先于本文件通用清单。
4. 材料缺失 → `status="blocked"`，仍写 result.json 与报告后终止。

## 4. 五阶段门控流水线

### 阶段 0：解析与锚点化（脚本）→ 门 G0

```bash
cd /app/work
python3 <SKILL_DIR>/scripts/ingest.py <材料路径> checkpoints/stage0/pages.jsonl
python3 <SKILL_DIR>/scripts/anchor_index.py --pages checkpoints/stage0/pages.jsonl \
    --out checkpoints/stage0/anchors.json
```

- 门 G0（脚本退出码即门）：解析成功且锚点非空。失败则 blocked 流程。
- `anchor_index.py` 产出段锚点 `p<页>.¶<段>`、图表锚点 `p<页>.Fig<n>`/`Tab<n>`、参考文献节位置；全部 finding 的 `location.anchor` 必须取自该表。

### 阶段 1：阅读与主张清单（Agent，约 10–15 次请求）→ 门 G1

产出 `checkpoints/stage1/claims.jsonl`（claim_id、anchor、quote、类型）。门 G1：每条 quote 逐字落在所声称锚点文本内（gate_check 的 quote 校验子集，可单独跑 `gate_check.py --only quote --claims ...`）。不通过的条目修复（从 anchors.json 取真实文本）或丢弃，不得带病进入阶段 2。

### 阶段 2：六类审查（Agent，约 20–30 次请求）→ 门 G2

逐类审查事实核验、引用支持、方法设计、统计报告、论证链、学术规范（各类审查要点见 `references/gates.md` 附录；本 Skill 不替代专业判定，只规定产出形态）。产出 `checkpoints/stage2/findings.draft.jsonl`。门 G2：draft 的每条 finding schema 完整、词表合法（category/issue_type/severity/confidence）、anchor 存在。

### 阶段 3：交付前总门（脚本）→ G1–G8 全量

```bash
python3 <SKILL_DIR>/scripts/gate_check.py --result /app/output/result.json \
    --pages checkpoints/stage0/pages.jsonl \
    --case /input/case.json --log /app/output/run_log.jsonl \
    --out checkpoints/stage3/gate_report.json
```

门定义详见 `references/gates.md`：

- **G1** case_id 存在且与 case.json 一致；
- **G2** output_contract 全部字段在 result.json 顶层存在；
- **G3** 六类覆盖状态齐全且取值合法；
- **G4** findings schema 完整；
- **G5** 每条 finding 的 quote 逐字落在所声称页文本内（折叠空白比对）；
- **G6** 词表合法；
- **G7** 诚实一致性：status=completed 时不允许存在未解释的 unchecked 覆盖；status=partial 时 unchecked_items 必须非空；findings 中标 `needs_human_review` 的条目必须在报告待复核清单中复现；
- **G8** run_log.jsonl 存在、每行含 `t/action/status`，且记录了 G0–G3 各门结果。

任一门失败：退出码 1，修复后重跑；预算耗尽在门内 → 保存 gate_report.json 与当前 result.json，标 partial 交付并说明未过的门。

### 阶段 4：确定性重放（脚本）→ 门 G9

```bash
python3 <SKILL_DIR>/scripts/replay_diff.py \
    --run checkpoints/stage0 --rerun checkpoints/stage0_replay \
    --out checkpoints/stage4/replay_report.json
```

对**确定性产物**（pages.jsonl、anchors.json——同一输入同一脚本必须逐字节一致）做重放比对；不一致说明流水线含隐藏不确定性（时间戳、字典序、外部状态），必须修复或在 uncertainties 中声明。Agent 判断类产物（claims、findings）不要求字节一致，但要求在 run_log 中记录版本变化。

## 5. 交付契约（/app/output/）

`result.json`（schema 见下）、`review_report.md`、`run_log.jsonl`、`evidence/`（anchors.json、gate_report.json、replay_report.json）。result.json：

```json
{
  "case_id": "...", "skill": "audit-run-gates", "status": "completed | partial | blocked",
  "coverage": {"事实核验": "checked", "引用支持": "checked", "方法设计": "checked", "统计报告": "checked", "论证链": "checked", "学术规范": "checked"},
  "findings": [{"id": "F-01", "category": "...", "issue_type": "...", "severity": "critical | major | minor | advisory",
    "location": {"locator": "p.3 ¶2", "anchor": "p3.2", "page": 3, "quote": "逐字摘录"},
    "claim": "...", "verdict": "...", "basis": "...", "suggestion": "...",
    "confidence": "high | medium | low", "recheck": "...", "needs_human_review": false}],
  "process_quality": {"gates": {"G0": "pass", "G1": "pass", "G2": "pass", "G3": "pass", "G9": "pass"},
    "replay_deterministic": true, "checkpoints": ["stage0", "stage1", "stage2", "stage3", "stage4"]},
  "unchecked_items": [], "uncertainties": [],
  "artifacts": {"report": "review_report.md", "gate_report": "evidence/gate_report.json", "log": "run_log.jsonl"}
}
```

## 6. 异常处理

| 情况 | 处置 |
|-|-|
| 解析失败/扫描件无 OCR | blocked；记录已尝试方法 |
| 阶段中断 | 从最近 checkpoint 恢复；恢复动作写日志 |
| 门 G5 大面积不过（quote 对不上） | 停止写作，回到 anchors.json 逐条重取真实文本；禁止手工"润色"quote 到通过 |
| replay_diff 报不一致 | 定位不确定性来源（如时间戳），修复或声明；不静默 |
| 预算不足 | 当前门报告 + partial 交付；unchecked_items 写明剩余阶段 |

## 7. 参考资料

- `references/gates.md`：G0–G9 门的精确定义、通过判据、失败处置；六类审查要点附录。
- `references/partial_honesty.md`：诚实 partial 的判定与写法。
- `examples/`：**合成示例**——一份过门与一份埋雷的 result.json，演示 gate_check 与 replay_diff 的拦截。
