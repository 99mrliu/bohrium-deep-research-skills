# 最小调用示例（全虚构合成数据）

> 本目录所有人名、地名、期刊、数据均为虚构，仅用于演示引擎行为。
> `examples/output/` 是下列命令的**真实运行产物**（未手工修饰）。

## 0. 输入设定

`examples/input/manuscript.txt`（68 行虚构英文小稿）：

- 两节以上正文 + 1 个图注（Figure 1）+ 1 个表注（Table 1）+ 1 个「注：」脚注段
  + 1 个附录段（Appendix A）；
- 标记乱序：首现依次是 `[3] [1] [7]`；
- 一个**悬空标记** `[9]`（列表只有 8 条）；
- 图注里 `[5]`、表注里 `[3]`、脚注里 `[1]`、附录里 `[2]`。

`examples/input/references.txt`：8 条虚构条目 `[1]`–`[8]`，其中 `[8]`
（Castellanos 口述史）**从未被引用**（未引用条目）。

`examples/input/ops.json`：三个操作——

1. `delete_marker` reading_order=4：删除悬空标记 `[9]`；
2. `merge_paragraphs` para_a=2, para_b=3：合并引言前两段；
3. `insert_marker` line=44 after_text="aged fastest" labels=["2"]：结果段补引 `[2]`。

## 1. 阶段 1：扫描建图

```bash
python3 scripts/cite_scan.py --manuscript examples/input/manuscript.txt \
  --references examples/input/references.txt --out examples/output
# 退出码 0
```

输出摘要（真实）：12 个标记、8 个条目、`dangling: ["9"]`、`uncited: ["8"]`、
区域计数 `{body: 8, figure_caption: 1, table_caption: 1, footnote: 1, appendix: 1}`。
产物：`examples/output/occurrences.jsonl`、`examples/output/labels.json`。

## 2. 阶段 2：plan 重算

```bash
python3 scripts/renumber.py plan --manuscript examples/input/manuscript.txt \
  --references examples/input/references.txt --ops examples/input/ops.json \
  --occurrences examples/output/occurrences.jsonl \
  --style numeric-bracket --out examples/output
# 退出码 0
```

三层映射（真实结果，按编辑后全局首现赋号）：

| 原标签 | sid | 新标签 | 说明 |
| --- | --- | --- | --- |
| 3 | sid-001 | 1 | 引言首现 |
| 1 | sid-002 | 2 | |
| 7 | sid-003 | 3 | |
| 4 | sid-004 | 4 | |
| 6 | sid-005 | 5 | |
| 5 | sid-006 | 6 | 图注纳入同一序列 |
| 2 | sid-007 | 7 | 结果段插入处首现 |
| 8 | sid-008 | — | uncited_retained → `[*] …【未引用·保留】` |

悬空 `[9]` 记入 `dangling_removed`，无编号、无臆造条目。

## 3. 阶段 3：apply 原子施加

```bash
python3 scripts/renumber.py apply --manuscript examples/input/manuscript.txt \
  --references examples/input/references.txt \
  --label_map examples/output/label_map.json \
  --style numeric-bracket --out examples/output
# 退出码 0
```

apply 先完整复算并逐字段比对 label_map，通过才写出 `edited_manuscript.txt`、
`edited_references.txt`、`label_map.json`。改后稿要点（真实）：

- 引言两段已合并为一段，`[9]` 删除后标点空白规整（`notes, which …`）；
- 正文 `[3][1][7]` → `[1][2][3]`；`[7,3]` → `[1,3]`；
- 图注 `[5]` → `[6]`，表注 `[3]` → `[1]`，脚注 `[1]` → `[2]`，附录 `[2]` → `[7]`；
- 结果段新插入 `aged fastest [7].`；
- 文末列表按新编号 1–7 重排，第 8 行为
  `[*] Castellanos, V. …【未引用·保留】`。

## 4. 阶段 4：verify 核验

```bash
python3 scripts/sync_verify.py --manuscript examples/output/edited_manuscript.txt \
  --references examples/output/edited_references.txt \
  --label_map examples/output/label_map.json --out examples/output
# 退出码 0，all_pass: true，failed_rules: []
```

V1–V8 全过：新编号自 1 连续、图注/表注/脚注/附录全部纳入、未引用条目带标注
保留、V8 空 ops 重跑零变化（幂等自证）。报告：
`examples/output/sync_report.json` / `sync_report.md`。

## 5. Booby-trap 演示（verify 必须抓住手改）

产物见 `examples/output/boobytrap/`。

**Trap A**——把 `edited_manuscript.txt` 中第一个 `[2]` 手改为 `[5]`（编号 5
在列表中存在，V1 抓不到；但首现序被破坏）：

```bash
python3 scripts/sync_verify.py --manuscript examples/output/boobytrap/trap_a/edited_manuscript.txt \
  --references examples/output/edited_references.txt \
  --label_map examples/output/label_map.json --out examples/output/boobytrap/trap_a
# 退出码 1；failed_rules: ["V8"]
# V8 detail: 映射非恒等 [('5','2'), ('6','5'), ('7','6'), ('2','7')]；重渲染文本与输入不一致
```

**Trap B**——把第一个 `[2]` 手改为 `[9]`（悬空编号）：

```bash
python3 scripts/sync_verify.py --manuscript examples/output/boobytrap/trap_b/edited_manuscript.txt \
  --references examples/output/edited_references.txt \
  --label_map examples/output/label_map.json --out examples/output/boobytrap/trap_b
# 退出码 1；failed_rules: ["V1", "V3", "V8"]
# V1: 1 个悬空标记 raw=[9]；V3: 正文使用的编号 [1,2,3,4,5,6,7,9] 存在跳号；V8: 重算抛错
```

两个陷阱都被捕获、退出码均为 1：Trap A 展示 V8 对「看似合法但破坏首现序」篡改
的捕获能力；Trap B 展示经典的悬空+跳号组合（V1/V3）连同 V8 一起报警。

## 6. 附：篡改 label_map 的 apply 行为

把 `label_map.json` 中任一 new_label 改掉再 apply：退出码 1，报
「label_map 与输入复算不一致（字段: mappings）」，且**输出目录不落任何文件**
（原子性）。重跑 plan+apply 产物与 examples/output 逐字节一致（确定性）。
