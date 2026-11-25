# 交付物格式约定与交叉核验规则（check_exports.py 的判定依据）

设计原则：核验脚本与构建脚本**相互独立**——check_exports.py 不 import
build_review.py 的任何函数，只重新读盘、按本文件约定复算。第三方可不看
构建过程、只凭本约定复核任何一次交付。

## 五件交付物 + 一件核验产物

| 文件 | 生成者 | 格式要点 |
|-|-|-|
| ledger.csv | build_review.py | **UTF-8-SIG**（带 BOM，Excel 双击不乱码）；首行表头固定 14 列：`review,rid,decision,decision_cn,reason,title,authors,year,venue,doi,matched_terms,src_file,src_row,note`；`decision` ∈ {include, borderline, exclude, duplicate} |
| report.md | build_review.py | 七个固定章节：概要/筛查条款/候选清单/排除理由分布/署名清单核验/不确定性/交付物哈希 |
| review.html | build_review.py | **自包含单文件**：内联 CSS/JS，零外部引用（无 src/href 外链），可离线打开；每行一个勾选位（duplicate 行无勾选位）；纳入标题以 HTML 转义形式出现 |
| flow.svg | build_review.py | 纯文本 SVG，无绘图库产物；六个 stage 盒子各为 `<g id="stage-...">`，盒内必有文本 `n = N`；stage id 固定：identified / duplicates / screened / excluded / included / borderline |
| manifest.json | build_review.py | `{"case_id", "generated_at", "deliverables": {name: {"sha256", "bytes"}}}`；登记上述四件 + result.json，共 5 件；不登记自身 |
| result.json | build_review.py | 按 output_contract 动态装配 + status/sources/uncertainty/field_notes |
| export-check.json | check_exports.py | 核验报告（不在 manifest 内，属核验侧产物） |

## 计数恒等式（X5 的理论基础）

```
identified = duplicates + screened
screened   = included + borderline + excluded
```

ledger.csv 的每一行（含 duplicate 行）都计入 identified；flow.svg 的每个
stage 计数必须等于 ledger.csv 对应 decision 的行数推导值。

## 逐项核验规则

| ID | 规则 | 失败时的典型原因 |
|-|-|-|
| X1 | manifest.json 存在且登记全部 5 件交付物 | 构建中断；manifest 被删 |
| X2 | 每件交付物重新计算 sha256 与字节数，与 manifest 逐项一致 | 交付物被手工篡改；半截写盘；复制时损坏 |
| X3 | ledger.csv（UTF-8-SIG 读取）数据行数 == result.json `screening_log` 条数 | 台账与结果脱节（手工编辑其一） |
| X4 | 每条 decision=include 的标题（HTML 转义后）都出现在 review.html 中 | HTML 与台账脱节；转义 bug |
| X5 | flow.svg 六个 stage 的 `n = N` 与 ledger.csv 处置分布逐项一致 | 流程图与台账脱节；计数恒等式被破坏 |
| X6 | result.json：case_id 与 case.json 一致；output_contract 字段全覆盖（null 即缺失）；status ∈ {complete,partial,blocked} 且 complete ⇒ uncertainty 为空 | 串案例；契约被忽略；状态虚报 |

任一 FAIL 则总判定 FAIL、exit 1；全部 PASS 才 exit 0。**手工编辑交付物必然
触发 X2/X3/X4/X5 之一**——修正永远发生在输入或 overrides 层，然后重跑管线，
这是本格式约定的核心纪律。

## field_notes 约定

result.json 中的字典：键为留空的契约字段名，值为一句原因说明。它解决一个
真实歧义：空字段既可能是"没有"，也可能是"漏了"。X6 配合 field_notes 杜绝
静默空字段。
