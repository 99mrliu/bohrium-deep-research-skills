# 最小调用示例（合成示例）

> **本示例为合成示例**：输入库与输出均为虚构数据，仅说明接口与完整流程，
> 不是平台正式案例的结果。

## 输入（make_fixture.py 生成的虚构资料库）

```
input/
  case.json          # case_id=synthetic-render-001，1 个问题 + output_contract
  task.md
  dev3_brief.txt      # 虚构研究简报（响应度 120 A/W）
  notes/test_notes.txt
  notes/test_notes_副本.txt  # 字节级重复副本
```

## 调用

```bash
bash examples/run_example.sh
```

## 示意输出（实际运行得到，数据虚构）

1. `render_scan`：3 个文件全部可读，识别 F003 为 F002 的字节副本；
   保底 result.json 落盘。
2. 模型写 work/answers.json（坐标取自真实编目）。
3. `render_kb` 生成 handover/：knowledge_index.md（文件树 + 版本链接 +
   答案卡索引）、catalog.csv（3 行）、version_notes.md（重复副本说明）、
   answers/q_q1.md（答案卡，含坐标 `[F001|…|L2-L2]` 与逐字引文）。
4. `link_check`：`{"pass": true, "checked": {"links": 4, "catalog_rows": 3,
   "citations": 1}}`。

反例演示：把答案卡中的 120 篡改为 999 后，机检立即报
`cite_quote_not_found`（F001）——交接包内的引文真实性由机器回验，
不是排版对了就算数。
