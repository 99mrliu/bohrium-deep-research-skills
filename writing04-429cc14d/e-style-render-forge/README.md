# style-render-forge

参考文献**格式转换与确定性渲染**技能（方向 E：格式转换与下游渲染工程）。
核心立场：格式转换的敌人是「静默丢字段」和「凭印象补字段」——任何来源解析进
规范化记录模型（raw 逐字保留、未识别标签登记不丢弃、宏延迟展开），再由类型化
模板确定性渲染；缺字段渲染可见占位符（`[缺: 页码]`），绝不杜撰；往返
（import→export→import）字段级 diff 必须为零或全部可解释；渲染器是草稿而非
规范验证器，最终逐条目检。

## 组成

```
SKILL.md                          技能说明（运行时契约、五阶段流程、异常处理表）
scripts/import_records.py         阶段1：BibTeX / RIS（含 CNKI 风味）/ CNKI 文本 → records.json
scripts/field_lint.py             阶段2：L1–L8 字段 lint（有 error 退出码 1；L8 为往返 diff）
scripts/style_render.py           阶段3：GB/T 7714—2015（顺序编码/著者年）、APA 7 渲染；
                                  ris/bibtex/csljson 无损导出（占位符必登记）
references/gbt7714_cheatsheet.md  GB/T 7714—2015 操作速查（非规范原文）
references/import_export_formats.md  records.json 字段格式、映射表、往返规程
examples/                         全虚构合成示例 + 真实运行产物（见 minimal_example.md）
```

## 用法（评测环境）

```
python3 /skills/weekly-skill/scripts/import_records.py --file /input/lib.bib --out /app/work
python3 /skills/weekly-skill/scripts/field_lint.py --records /app/work/records.json --out /app/work
python3 /skills/weekly-skill/scripts/style_render.py --records /app/work/records.json \
    --style gbt7714-numeric --out /app/work/refs.txt
```

本地复现用相对路径（见 `examples/minimal_example.md`）。仅标准库、无网络、
确定性输出（同输入必同输出）。

## 快速验证

`examples/output/` 为真实运行产物：导入 9 条合成记录 → lint 报 2 error
（缺页码、缺年）退出码 1 → 渲染可见占位符 → RIS 往返 diff 为零 →
`examples/output_fixed/` 修复后 lint 退出码 0。
