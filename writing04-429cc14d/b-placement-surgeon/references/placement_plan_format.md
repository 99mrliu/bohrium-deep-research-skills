# 修复计划与产物格式：plan.json / change_map.json / intent.jsonl

本文件定义 placement-surgeon 阶段 3 的三个 JSON 格式。所有文件均为
UTF-8；JSON 中允许中文字段值。

## 1. plan.json（输入：人工/模型编写的修复计划）

```json
{
  "note": "计划说明（可选）：本计划针对哪些 violation、来源依据",
  "operations": [ <操作>, ... ]
}
```

操作按数组顺序校验，但施加时按文本位置降序进行，因此操作间书写顺序不
影响结果。三种操作：

### move —— 移动已有标记

```json
{
  "op": "move",
  "marker": "[6]",
  "from_sentence": "S016",
  "to_sentence": "S013",
  "reason": "P3：从图注移回正文论断句（必填，便于回溯）"
}
```

- `marker`：标记**原文精确串**（含方括号/括号与内部空白），在
  `from_sentence` 句内必须逐字出现且**恰好一次**；
- `from_sentence` / `to_sentence`：`claim_scan.py` 生成的句 id，二者不
  可相同；`from_sentence` 也可用 `anchor_text`（全稿唯一子串）替代；
- 插入位置：`to_sentence` 句末终结标点（。！？；.!?）与闭引号**之前**。

### insert —— 插入标记

```json
{
  "op": "insert",
  "sentence": "S005",
  "marker_text": "[1]",
  "reason": "P1：为前一独立论断补挂已核验来源 [1]"
}
```

- `sentence` 可换成 `anchor_text`（唯一匹配）；
- `marker_text` 必须整体匹配合法引用标记：`[n]`、`[n-m]`、`[n,m]` 或
  `（作者, 年）`/`(Author, year)`；其余文本一律拒绝（防止借 insert 改
  写正文）；
- **纪律**：insert 的编号必须已在文献表中存在且经来源核验与论断对应；
  无对应来源的缺口只能在审计报告中标注 `[缺来源]`，不得写入 plan。

### remove —— 移除标记

```json
{
  "op": "remove",
  "marker": "[6]",
  "sentence": "S016",
  "reason": "P3：图注误挂，正文已有等价引用"
}
```

- `marker` 在指定句内逐字出现且恰好一次，否则拒绝。

### 校验与原子性

`placement_plan.py` 依次校验：锚点句存在且唯一 → marker 原文逐字唯一 →
marker_text 合法 → 删除区间互不重叠、插入点不落在删除区间内。**任一校验
失败：整体不写任何输出文件**，stderr 打印全部错误，退出码 2；全部通过
才原子写入（临时文件 + `os.replace`），退出码 0。

## 2. change_map.json（输出：施加记录，全程可回溯）

```json
{
  "plan_note": "来自 plan.json 的 note",
  "operations_applied": 4,
  "changes": [
    {
      "op": "move",
      "marker": "[6]",
      "from_sentence": "S016",
      "to_sentence": "S013",
      "reason": "……",
      "old_position": {"line": 15, "col": 51, "char_offset": 634},
      "new_position": {"line": 13, "col": 177, "char_offset": 566}
    }
  ],
  "diff": ["--- original", "+++ edited", "@@ ...", ...]
}
```

- insert 只有 `to_sentence` 与 `new_position`；remove 只有
  `from_sentence` 与 `old_position`；move 两者俱全；
- 行/列均 1 起始；`char_offset` 为 0 起始字符偏移；
- `diff` 为 `difflib.unified_diff` 的逐行结果。**验收要求：diff 中除引
  用标记的插入/移动/删除外不得出现任何正文改动**（引用跨度外零改动）。

## 3. intent.jsonl（可选输入：来源台账，供 P2 使用）

每行一个 JSON 对象：

```json
{"marker": "[2]", "supports": ["S006"], "source": "文献表第 2 条：短程口服方案荟萃分析"}
```

- `marker`：标记原文精确串；
- `supports`：台账声明的、该标记应当支撑的全部句 id；
- `source`：自由文本备注（可选）。

句 id 以**当前版本稿件**的 `claim_scan.py` 输出为准；稿件改动后须重跑
扫描并刷新台账。无台账时审计跳过 P2 并在报告 `skipped_rules` 中注明。
