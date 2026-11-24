# 最小调用示例（全虚构合成数据）

> **合成声明**：`examples/input/` 与 `examples/input_fixed/` 中的全部条目、刊名
> （Journal of Synthetic Citation Studies、合成情报学报等）、出版社（Fictional
> Academic Press）、机构（虚构大学）、人名与 DOI（10.55555/10.55556/10.55557
> 为保留测试段风格的前缀）**均为虚构**，仅用于演示。`examples/output/` 与
> `examples/output_fixed/` 是本仓库发布前**真实运行**下列命令得到的产物。

## 输入设计（故意埋的坑）

| 文件 | 条数 | 埋点 |
| --- | --- | --- |
| `input/library.bib` | 4 | `@string{jscis}` 宏用于刊名；`wang2024missing` 缺页码；`zhang2023survey` 含未映射 `note` 字段、4 名作者 |
| `input/cnki_export.ris` | 3 | CNKI RefWorks 风味；`K1` 未映射自定义标签；第 3 条缺 `Y1`（缺年） |
| `input/cnki_text.txt` | 2 | 第 1 条题名含 CJK 紧邻半角冒号（`问题:兼论`），触发 L7 |

## 第 1 步：导入（阶段 1）

```
python3 scripts/import_records.py --file examples/input/library.bib \
    --file examples/input/cnki_export.ris --file examples/input/cnki_text.txt \
    --out examples/output
# 退出码 0；输出 examples/output/records.json（9 条，5 条警告）
```

目检确认（见 `output/records.json`）：

- 宏已展开：`wang2024missing.venue = "Journal of Synthetic Citation Studies"`，
  同时 `raw_fields.journal = "jscis"` 逐字保留；
- 未映射标签保留：`ris2-1.unmapped_fields = {"K1": "CNKI-SAMPLE-0001"}`；
- `@preamble`、注释逐字存于 `meta`；CNKI 文本 2 条挂"类型默认期刊论文"警告。

## 第 2 步：lint（阶段 2）

```
python3 scripts/field_lint.py --records examples/output/records.json --out examples/output
# 退出码 1；输出 lint_report.json / lint_report.md
```

恰好 4 条发现：**error 2**（L1：`ris2-3` 缺年、`wang2024missing` 缺页码）、
**warning 1**（L7：`cnki3-1` 题名 CJK 紧邻半角冒号）、**info 1**（L4：
`zhang2023survey` 4 名作者将启用 et al. 省略）。有 error → 退出码 1，阻断交付。

## 第 3 步：渲染（阶段 3）

```
python3 scripts/style_render.py --records examples/output/records.json \
    --style gbt7714-numeric --out examples/output/gbt7714.txt     # 退出码 0
python3 scripts/style_render.py --records examples/output/records.json \
    --style apa7 --out examples/output/apa7.txt                   # 退出码 0
```

占位符可见（引自 `output/gbt7714.txt` 实际产物）：

```
[7] 吴雪梅. 中文期刊参考文献格式的抽样调查[J]. 合成编辑学刊, [缺: 年份], 30(8): 701-709.
[8] WANG F. Placeholder Strategies in Reference Rendering[J]. Journal of Synthetic Citation Studies, 2024, 13(1): [缺: 页码]. DOI: 10.55555/jscis.2024.0002.
[9] ZHANG W, LI X, WANG F, et al. A Survey of Citation Graph Embeddings for Digital Libraries[J]. ...
```

逐条占位符登记在 `output/render_notes.json`（=`gbt7714.render_notes.json`，
`placeholder_total = 2`）。APA 7 产物见 `output/apa7.txt`（刊名/卷号 `*…*`
斜体约定、题名句首大写保守策略）。

## 第 4 步：往返（阶段 4）

```
python3 scripts/style_render.py --records examples/output/records.json \
    --style ris --out examples/output/roundtrip_export.ris        # 退出码 0
python3 scripts/import_records.py --file examples/output/roundtrip_export.ris \
    --out examples/output/roundtrip                               # 退出码 0
python3 scripts/field_lint.py --records examples/output/records.json \
    --roundtrip examples/output/roundtrip/records.json --out examples/output/roundtrip
```

**L8 字段级 diff = 0**（该次报告中的 2 条 error 是源数据本身的 L1 缺年/缺页，
非往返差异；见 `output/roundtrip/lint_report.json`，L8 findings 为 0）。

## 第 5 步：修复后复检

`input_fixed/` 仅做两处人工修复（回源补字段，非编造）：`wang2024missing` 补
`pages = {33-41}`；RIS 第 3 条补 `Y1 - 2021`。

```
python3 scripts/import_records.py --file examples/input_fixed/library.bib \
    --file examples/input_fixed/cnki_export.ris \
    --file examples/input_fixed/cnki_text.txt --out examples/output_fixed   # 退出码 0
python3 scripts/field_lint.py --records examples/output_fixed/records.json \
    --out examples/output_fixed                                             # 退出码 0
```

结果：error 0 / warning 1 / info 1 → **退出码 0**。剩余 warning 为 L7 标点
混用（lint 原则：只报告、不改写原文），info 为 >3 作者提示——均不阻断交付，
但必须在结果中声明。
