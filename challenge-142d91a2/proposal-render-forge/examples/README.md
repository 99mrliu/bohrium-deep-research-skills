# 最小调用示例（合成示例，非正式案例结果）

题材：**城市内涝时空预测模型研究**开题。全部输入均为演示接口而构造的
**合成数据**（文献与材料为合成，非真实出版物/数据源）。

## 输入（input/）

- `case.json`：合成契约，output_contract 含 5 个字段（proposal_draft /
  preview_svg / preview_html / diff_report / revision_table）；
- `task.md`：合成开题任务（周期 8 季度、经费 28 万、6 项任务等硬条件）；
- `material_notes.md`：合成材料笔记；`advisor_feedback.md`：合成导师首轮反馈
  （驱动 v1→v2 两处修改：第 3 节指标阈值改写、第 5 节 T2 延期加缓冲）；
- `document_v1.json`：预制初稿（七要素齐全，阶段计划 6 项任务供甘特渲染）；
- `document_v2.json`：按导师意见修订的版本（含 revision 修改记录数组）；
- `document_bad.json`：故意构造的坏文档（缺 meta 字段、缺第 6 节、schedule
  缺表、悬挂引用 [S9]），用于演示 schema 校验 fail→拦截 行为。

## 运行

```
bash examples/run_example.sh   # 依赖仅 python3（标准库）
```

## 产物（expected/，全部为真实执行输出）

| 文件 | 说明 |
|---|---|
| `proposal.md` | v1 渲染的可编辑 Markdown 主交付（章节编号 1–7、GFM 表格、行内 [S#]、文末来源清单） |
| `preview.svg` | 纯文本 SVG 预览：七节卡片 + 阶段计划横向甘特条 |
| `preview.html` | 自包含 HTML 预览页（内嵌样式与同一份 SVG），浏览器直接打开 |
| `diff_report.md` | v1→v2 逐节修订对照：第 3 节 1 处改写、第 5 节 1 处新增 + T2 行级变更，其余节逐字节一致 |
| `revision_table.md` | 由 v2 的 revision 数组渲染的修改记录表 |
| `determinism_check.txt` | 确定性校验：render_markdown 双跑 cmp 字节一致 |
| `schema_fail.log` | 坏文档被拦截的真实校验输出（退出码 2，列出全部错误） |
| `result_partial.json` | init 后的诚实 partial 骨架（契约字段全 null） |
| `final_validation.log` | 两次 final 校验：骨架被判 partial 并点名 5 项缺项；填齐后判 ok |
| `result.json` | 收尾结果，status=ok（契约字段齐备；合成性质在 uncertainty 中声明） |

## result.json 路径说明

本示例演示 **ok 路径**：五个契约字段均由脚本真实产出后填齐，`final` 校验通过
判 ok。诚实 partial 由两处留证：`result_partial.json`（init 骨架）与
`final_validation.log` 第一段（骨架被强制 partial 并点名缺项）。若真实运行中
材料缺失或某交付物无法生成，对应字段保持 null，`final` 会强制 partial 并在
uncertainty 点名——与 SPEC 第 4 节纪律一致。
