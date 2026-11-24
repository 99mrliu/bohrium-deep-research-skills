# 回复信定位写法规范与三方核验判定规则

## 定位四件套

回复信中每一处落过稿的改动，必须配一条**定位行**，独立成行：

```
- 定位：CHG-01 ｜ 章节：2 数据与方法 ｜ 段序：第 2 段 ｜ 锚点："风速数据来自机场气象站的小时级观测。我们采用线性回归估计风速与能耗的关系。"
```

四个字段缺一不可：

| 字段 | 写法 | 来源 |
| --- | --- | --- |
| CHG 编号 | `CHG-01`（两位数起，续编不重用） | edits.json / changes.json |
| 章节 | 章节路径中的末级标题即可，如 `2 数据与方法` | changes.json 的 anchor.heading |
| 段序 | `第 N 段`，N 为该章节内段序 | changes.json 的 anchor.paragraph_index |
| 锚点 | 半角双引号包裹的逐字 quote | changes.json 的 anchor.quote，直接复制 |

书写纪律：

- 分隔符用全角竖线 `｜`（半角 `|` 也被解析，但全角在 Markdown 表格外更安全）；
- 锚点 quote 从 changes.json **复制**，不要凭记忆转写；quote 内部不得含半角
  双引号（基线有此字符时，先向组织方确认或改用全角引号基线）；
- 允许引用 quote 的**逐字片段**（≥12 字）代替全段，但全等最稳妥；
- 没有落稿的回复（如礼貌反驳 rebut）不写定位行，但子要求编号必须出现在
  回信中；
- 每个 CHG 只允许一种真实落稿位置，定位行不得指向未发生的改动。

## 三方核验判定规则（locate_check.py）

核验对象为三方：回复信、changes.json、修订稿。逐项判定：

| 项 | 规则 | 失败样例 |
| --- | --- | --- |
| (a) chg_exists | 信中出现的每个 `CHG-\d+` 必须在 changes.json 中存在 | 信写 CHG-09 而 changes.json 只到 CHG-03 |
| (b) markers_in_revised | 被引用的每个 CHG 在修订稿中有成对 `<!-- CHG-xx begin: … -->` / `<!-- CHG-xx end -->` | 信声称改了但从未落稿 |
| (c) location_fields | 每条定位行：quote 与登记逐字全等（或为其 ≥12 字逐字片段）；章节文字是登记章节路径的子串；段序数字等于登记 paragraph_index | 信中 quote 改写了一个字；段序写错 |
| (d) no_orphan_changes | changes.json 每个条目都在信中被引用且有规范定位行 | 落了稿但信里没说（孤儿改动） |
| (e) subrequests_covered | decisions.json 里每个子要求编号（含 rebut 的）都在信中出现 | 漏回 R2.1 |

任一项失败：locate_report.json 记录精确错误（行号、CHG 号、信中值 vs
登记值），脚本 exit 1；此时 result.json 只允许 status=partial，并须按错误
清单修信或补落稿后重跑。全部通过才允许 status=success。

## 常见 FAIL 排查

1. **quote 不一致**：99% 是写信时手打而非复制。从 changes.json 复制重贴。
2. **段序错**：注意段序是「该章节路径内」的段序，不是全文段序；标题本身
   不算段。
3. **孤儿改动**：apply_edits 落了几处，信里就要有几条定位行；删改动要同时
   删 edits.json 条目并重跑，不能只改信。
4. **子要求漏回**：检查 decisions.json 与回信小标题一一对应，rebut 也算回复。
