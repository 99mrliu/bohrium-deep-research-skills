# output_contract 常见字段模式与保守填充规则

本文是 contract_probe / result_scaffold / delivery_gate 三脚本的语义参考。
核心原则：**字段名以 case.json 实际写法为准；语义不明时保守填充并记录 assumption，不猜不造。**

## 一、常见字段模式

| 字段名（常见变体） | 典型语义 | 推荐填充形态 |
|---|---|---|
| `artifact` / `essay` / `chapter` / `report` / `manuscript` | 主要产物（章节正文） | `value` 填产物相对路径（如 `chapter.md`），或内联全文；`sources` 列主要依据材料 |
| `sources` / `references` / `citations` / `provenance` | 来源定位 | 数组：`{file, locator, note}`；locator 给行号/表号/字段路径，可核验 |
| `uncertainty` / `caveats` / `ambiguities` | 不确定性 | 字符串数组，每条写明"不确定点 + 原因 + 影响" |
| `changes` / `edits` / `revisions` / `diff` | 修改记录 | 数组：`{target, before, after, reason}`；对草稿的每处修改留痕 |
| `status` / `state` / `completion` | 完成状态 | `done`/`partial`/`unavailable`/`failed` 之一 + 说明 |
| `needs_human_review` / `review` / `confirm` | 人工确认项 | 数组：每条写明"事项 + 为什么需要人看" |
| `preview` / `render` / `figure` | 预览产物 | 指向 SVG/PNG/PDF 的相对路径；必须为真实渲染结果 |
| `dataset` / `data` / `splits` | 数据集与划分 | 名称、规模、划分比例/清单、来源 |
| `parameters` / `config` / `hyperparameters` | 参数与来源 | 键值 + 每个参数的来源（材料定位或"默认假设"标注） |
| `metrics` / `results` / `scores` | 结果指标 | 只填材料中真实出现的数值；派生计算注明公式 |
| `baselines` / `controls` / `ablations` | 对照 | 对照方法清单及其在材料中的出处 |
| `limitations` / `threats` | 局限 | 如实列局限，不得空洞套话 |

## 二、字段语义不明时的保守填充规则

1. **保留键，不删不改名**。门禁按字段名验收，改名等同缺字段。
2. **标量/事实类**：`value: null`，`status: "unknown"`，并在 `assumptions` 写：
   "该字段名 `xxx` 在契约中无类型与说明，按『……』理解；因无法确认，保守置空待人工确认。"
3. **文本类**：`value` 可填一段保守说明（"根据现有材料仅能确认……"），`status: "partial"`，
   `uncertainty` 写明局限。
4. **产物路径类**：若确认是产物字段，填已生成的文件路径；不确定时在 `assumptions` 记录两种可能解释。
5. **同步登记** `needs_human_review`（若契约无此字段，写进对应字段的 `notes`）。
6. **禁止**：
   - 用示例/占位文本冒充真实内容（示例必须带"合成示例"水印并只在 examples/ 下）；
   - 从其他字段复制内容充数；
   - 编造"系统默认值""标准配置"作为来源；
   - 为了让门禁 PASS 而把不确定内容标 `done`。

## 三、partial 状态的诚实写法

`partial` 必须同时满足三点，否则等于隐瞒：

```json
{
  "status": "partial",
  "value": "已完成的部分（具体内容，不是套话）",
  "uncertainty": [
    "缺少什么：例如『材料中未给出测试集划分比例，正文按训练/验证两段描述』",
    "为什么缺：例如『logs/train.log 仅有 2 个 epoch 记录，疑似截断』",
    "影响：例如『复现完整性受限，需人工补充划分信息』"
  ],
  "notes": "下一步建议"
}
```

反例（不合格）：`{"status": "partial", "value": "部分完成", "uncertainty": []}`——
没有说出缺什么，评审无法判断风险，门禁按"partial 未说明原因"判 FAIL。

## 四、状态值速查

| status | 含义 | 必须附带 |
|---|---|---|
| `done` | 完整且可回溯 | 非空 value + sources |
| `partial` | 部分完成 | uncertainty 说明局限 |
| `unavailable` | 材料缺失 | 查找过的位置清单 |
| `unknown` | 无法判断 | 判断受阻的原因 |
| `failed` | 运行失败 | 错误摘要与发生步骤 |
| `pending` | 骨架初值 | **禁止出现在最终交付中** |
