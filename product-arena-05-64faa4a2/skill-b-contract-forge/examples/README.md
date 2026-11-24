# examples：contract-forge 合成示例

**本目录全部内容为合成示例，非正式案例结果。** 数据由人工编造，仅用于演示与自检。

## 输入（case/）

- `case/case.json`：合成案例，含 `case_id`（SYNTH-DEMO-0001）与嵌套在 `task` 下的
  `output_contract`（4 个字段：`artifact`、`sources`、`uncertainty`、`status`），
  用于演示契约键的嵌套定位。
- `case/task.md`：体裁（方法与实验章节）/受众（审稿人）/格式（Markdown + SVG 预览）/篇幅约束。
- `case/notes.md`：小材料（合成实验记录），是章节全部数值的唯一来源。

## 调用

```bash
cd examples && bash run_example.sh
```

依次执行：contract_probe → result_scaffold → 脚本内模拟填充最小 chapter.md 与
result.json → preview_render → delivery_gate（正例），最后构造一个删除 `sources`
字段的 result.json 验证门禁判 FAIL（负例产物在临时目录，自动清理）。

## 预期输出（expected/）

| 文件 | 说明 |
|---|---|
| `work/contract.json` | 提取结果：case_id、4 个契约字段（含类型/必填/语义猜测）、task.md 约束、materials、unrecognized |
| `work/result.skeleton.json` | 骨架：case_id 已填，4 字段均为 pending 占位结构 |
| `work/WORKSPACE.md` | 工作目录约定说明 |
| `chapter.md` | 模拟写作的章节（覆盖六要素） |
| `result.json` | 填充完成的交付物，4 字段均 done |
| `chapter.preview.svg` | 纯标准库渲染的章节预览（含标题层级、表格、列表） |
| `gate_report.json` / `gate_report.md` | 门禁报告：正例全部 PASS；负例（缺 sources）G3 判 FAIL、退出码 1 |

## 自检要点

1. contract.json 的 `contract_source` 应为 `$.task.output_contract`（嵌套命中）。
2. 骨架与 result.json 的字段名与契约逐字符一致，case_id = `SYNTH-DEMO-0001`。
3. chapter.preview.svg 是合法 XML 且含章节文字（如"方法与实验"、"学习率"）。
4. gate_report.md 正例结论 PASS；负例结论 FAIL 且指出缺少字段 `sources`。
