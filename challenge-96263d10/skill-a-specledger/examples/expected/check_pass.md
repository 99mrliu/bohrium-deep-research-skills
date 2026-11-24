# 规格核对报告（spec_check）

输出文件：`examples/work/output_fixed.docx`；容差 ±0.06

PASS 20 / FAIL 0 / UNKNOWN 10（共 30 项）

| id | 期望 | 实测 | 判定 | 规格溯源 |
|---|---|---|---|---|
| caption.figure.position | below  | — | UNKNOWN | examples/work/rules.txt line 4 |
| caption.table.position | above  | — | UNKNOWN | examples/work/rules.txt line 4 |
| page.columns | 1 栏 | 1 | PASS | examples/work/rules.txt line 4 |
| page.header_footer_refs | {'headers': 0, 'footers': 0}  | — | UNKNOWN | examples/work/template.docx word/document.xml#body/sectPr |
| page.margin.bottom | 3.17 cm | 3.169 | PASS | examples/work/rules.txt line 2 |
| page.margin.footer | 1.75 cm | 1.75 | PASS | examples/work/template.docx word/document.xml#body/sectPr/pgMar@footer |
| page.margin.gutter | 0.0 cm | 0.0 | PASS | examples/work/template.docx word/document.xml#body/sectPr/pgMar@gutter |
| page.margin.header | 1.501 cm | 1.501 | PASS | examples/work/template.docx word/document.xml#body/sectPr/pgMar@header |
| page.margin.left | 2.54 cm | 2.54 | PASS | examples/work/template.docx word/document.xml#body/sectPr/pgMar@left |
| page.margin.right | 2.54 cm | 2.54 | PASS | examples/work/rules.txt line 2 |
| page.margin.top | 3.169 cm | 3.169 | PASS | examples/work/template.docx word/document.xml#body/sectPr/pgMar@top |
| page.section_count | 1 节 | 1 | PASS | examples/work/template.docx word/document.xml |
| page.size.height | 29.7 cm | 29.7 | PASS | examples/work/template.docx word/document.xml#body/sectPr/pgSz@h |
| page.size.width | 21.0 cm | 21.0 | PASS | examples/work/template.docx word/document.xml#body/sectPr/pgSz@w |
| refs.standard | GB/T 7714  | — | UNKNOWN | examples/work/rules.txt line 5 |
| style.Heading1.bold | True  | True | PASS | examples/work/template.docx word/styles.xml#style[@styleId=Heading1]/rPr/b |
| style.Heading1.font_eastasia | SimHei  | SimHei | PASS | examples/work/template.docx word/styles.xml#style[@styleId=Heading1]/rPr/rFonts@eastAsia |
| style.Heading1.font_latin | Liberation Serif  | Liberation Serif | PASS | examples/work/template.docx word/styles.xml#style[@styleId=Heading1]/rPr/rFonts@ascii |
| style.Heading1.outline_level | 1 级 | 1 | PASS | examples/work/template.docx word/styles.xml#style[@styleId=Heading1]/pPr/outlineLvl@val |
| style.Heading1.size | 16.0 pt | 16.0 | PASS | examples/work/template.docx word/styles.xml#style[@styleId=Heading1]/rPr/sz@val |
| style.Heading1.space_after | 60.0 pt | — | UNKNOWN | examples/work/template.docx word/styles.xml#style[@styleId=Heading1]/pPr/spacing@after |
| style.Heading1.space_before | 120.0 pt | — | UNKNOWN | examples/work/template.docx word/styles.xml#style[@styleId=Heading1]/pPr/spacing@before |
| style.Normal.font_eastasia | SimSun  | SimSun | PASS | examples/work/template.docx word/styles.xml#style[@styleId=Normal]/rPr/rFonts@eastAsia |
| style.Normal.font_latin | Liberation Serif  | Liberation Serif | PASS | examples/work/template.docx word/styles.xml#style[@styleId=Normal]/rPr/rFonts@ascii |
| style.Normal.line_spacing | 1.25 倍 | 1.25 | PASS | examples/work/rules.txt line 3 |
| style.Normal.size | 10.5 pt | 10.5 | PASS | examples/work/rules.txt line 3 |
| style.Normal.space_after | 80.0 pt | — | UNKNOWN | examples/work/template.docx word/styles.xml#style[@styleId=Normal]/pPr/spacing@after |
| text.line_spacing | 1.25 倍 | — | UNKNOWN | examples/work/rules.txt line 3 |
| text.一级标题.size | 16 pt | — | UNKNOWN | examples/work/rules.txt line 3 |
| text.正文.size | 10.5 pt | — | UNKNOWN | examples/work/rules.txt line 3 |
