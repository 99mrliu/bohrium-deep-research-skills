# ops.json 操作 DSL 规范（surgical-edit-ops/v1）

`compile_workorder.py` 的输出、`apply_ops.py` 的输入。一个 ops.json 是一组**有序、
幂等倾向、可审计**的编辑操作；每个 op 要么完全确定性（脚本直接落改），要么是
`manual`（保留原文交模型）。DSL 设计原则：**op 自带锚点与保护区，落改不需要模型在场**。

## 顶层结构

```json
{
  "schema": "surgical-edit-ops/v1",
  "case_id": "…",
  "source_workorder": "organizer-edit-workorder.json",
  "chapter_files": ["ch01.md", "ch02.md", "ch03.md"],
  "ops": [ /* Op, Op, … */ ],
  "summary": {"total": 2, "manual": 0, "deterministic": 2},
  "note": "可选标注（合成示例必带）"
}
```

## Op 公共字段

| 字段 | 类型 | 语义 |
|---|---|---|
| `op_id` | string | `op-001` 形式，apply/verify/change_log 用它交叉引用 |
| `item_id` | int | 来源 workorder item 的 id |
| `item_title` | string | 来源 item 标题（便于人读） |
| `type` | enum | `term_unify` / `float_ref_fix` / `replace` / `delete` / `format_normalize` / `manual` |
| `target_files` | [string] | 目标章节文件名列表（"全部章节"已被编译器展开为具体列表） |
| `params` | object | 类型相关参数，见下 |
| `warning` | string? | 编译期警告（如 target 回退全部章节） |
| `action` / `reason` | string | 仅 `manual`：原 action 文本与未识别原因 |

## term_unify — 术语统一（"将X统一为Y"）

```json
{"type": "term_unify",
 "params": {"from": "隔膜", "to": "隔板",
            "protect_patterns": ["^\\s*\\[\\d+\\]"],
            "protect_sections": ["参考文献"],
            "sync_abbrev": false}}
```

- 语义：在 `target_files` 的非保护行中把 `from` 全部替换为 `to`（字面替换，逐行）。
- `protect_sections`：标题文本含任一字符串的 Markdown 节（`#`~`######` 起，至下一同级或更高级标题止）整节保护。
- `protect_patterns`：命中任一正则的**行**保护（典型：文献条目行 `^\s*\[\d+\]`）。
- `sync_abbrev=true`：替换后把 `to(ABBR)`（半角括号跟拉丁缩写）归一为全角 `to（ABBR）`，即缩写定义处同步。
- 锚点失败：全文（保护区外）零命中 → 记 problem，不改动。

## float_ref_fix — 图表引用编号纠错

```json
{"type": "float_ref_fix",
 "params": {"fixes": [{"file": "ch01.md", "kind": "图", "old_num": "1-2",
                       "new_num": "1-1", "rule": "同章同类型题注唯一"}],
            "unresolved": [{"file": "…", "line": 8, "kind": "图", "num": "3-1",
                            "reason": "候选题注不唯一，需模型判断"}],
            "captions": ["图1-1", "图2-1", "表1-1"]}}
```

- 编译期已完成的确定性工作：扫描全部 target 章节，行首（可带 `**`）`图x-y`/`表x-y` 记为**题注**；其余位置的 `图x-y`/`表x-y` 记为**正文引用**；引用编号不在题注集合中即为**悬空引用**。
- 修复规则（按优先级）：同章（编号第一段相同）同类型题注唯一 → 指向它；否则全文同类型题注唯一 → 指向它；否则进 `unresolved` 交模型。
- 落改语义：对每个 fix，在该文件的非题注行把 `kind old_num`（容忍空格与 `-–—` 变体）替换为 `kind+new_num`（规范化无空格形式）。题注行永不改。
- `captions` 为编译期快照，供人工核对与 verify 使用。

## replace — 明确旧文/新文替换

```json
{"type": "replace", "params": {"old": "…原文…", "new": "…新文…", "count": "all"}}
```

- 字面子串替换；`count: "all"|"first"`。全文零命中 → problem。

## delete — 删除指定文本

```json
{"type": "delete", "params": {"text": "…待删除文本…"}}
```

- 删除 `text` 的全部出现（子串级）。零命中 → problem。

## format_normalize — 格式规范化（规则表驱动）

```json
{"type": "format_normalize", "params": {"rule": "number_unit_space"}}
```

- `number_unit_space`：数字与单位之间补半角空格（`305K`→`305 K`、`60℃`→`60 ℃`）；代码块（``` 围栏）内不改。单位表内置在 apply/verify 两个脚本中，保持一致。
- 未命中规则表的格式类需求编译为 `manual` 并注明原因。

## manual — 非机械项（模型处理）

```json
{"type": "manual", "action": "<item.action 原文>", "reason": "未匹配任何确定性规则: …"}
```

- apply_ops 不改动任何文件，只把它转录进 change_log 的 `manual_ops`；verify 标 SKIP；make_result 把它计入 uncertainty。模型编辑工作副本后重跑 verify + make_result 收口。

## change_log.json 结构（surgical-edit-changelog/v1）

```json
{"schema": "…", "case_id": "…", "mode": "apply|dry-run|rollback",
 "ops_total": 2, "ops_applied": 2, "ops_manual": 0,
 "problems": [{"op_id": "…", "reason": "…"}],
 "manual_ops": [{"op_id": "…", "item_id": 3, "action": "…", "reason": "…"}],
 "hunks": [{"file": "ch01.md", "op_id": "op-001",
            "line_range": [6, 6], "before": ["…旧行…"], "after": ["…新行…"]}]}
```

- 只存**相对文件名**与行号，不存绝对路径与时间戳（保证可复现、可入 expected）。
- 连续变更行聚合为一个 hunk；`line_range` 为 1 基闭区间。
