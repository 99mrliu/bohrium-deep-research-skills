# 任务说明（合成示例，非正式案例结果）

对 `draft_bad.md` 执行中文学术文体规约与措辞强度校准：

1. 运行 `register_lint.py` 对病稿做 R1–R8 检查，生成 `style_report.md`；
2. 运行 `--fix` 自动修复 R2（全角化）与 R1 无歧义替换，产出 `fix_log.json`；
3. 模型逐条处理 style_report 中 R3–R8 各项（修改或驳回并给出理由），写入 `resolution_log.json`；
4. 运行 `--verify` 复检，直至高级别项清零；
5. 运行 `assemble_result.py` 装配 `result.json`（契约 5 字段 + lint 统计 + 诚实 status/sources/uncertainty）。

材料见 `materials/material_study.md`（含「初步/preliminary/小样本/n=12」信号，无因果设计信号）。
