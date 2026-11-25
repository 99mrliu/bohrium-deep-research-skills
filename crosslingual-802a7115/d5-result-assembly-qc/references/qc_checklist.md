# 提交前质检清单（QC checklist）

## 为什么需要末端质检

跨语言检索的错误有两类：检索过程的错误（漏召回、错配）与**交付过程的错误**
（契约字段缺失、归因断链、status 虚报、语种覆盖静默缺席）。后者完全可以通过
机械检查消灭——本清单就是这套机械检查。

## 检查项细则

### C1 case_id 一致
result.json 的 case_id 必须逐字等于 case.json 的 case_id。手敲 case_id 是
最常见的交付错误；一律由 assemble_result.py 从文件读取。

### C2 output_contract 字段齐全
契约里点名的每个字段都必须出现。没数据写 null，但 null 必须在 uncertainty
或 change_records 中被点名认领——"显式的空"与"遗漏"是可复核性的分水岭。

### C3 status 与内容一致
- ok：hits 非空，或 uncertainty 中有"空结果属预期"的显式说明；
- partial/failed：uncertainty 必须非空，说明哪些部分未完成；
- 组装器发现 ok＋空 hits 且无说明时自动降为 partial 并留痕。

### C4 命中可回指
每条 hit 需要：(a) locator——locator/source_file/evidence/file/offsets 之一；
(b) 归因四字段 source/doi/language/version——真实缺失写 null 且附
attribution_note，**不推断、不补造**。

### C5 语种覆盖诚实
coverage 中每个声明语种：有命中（count/hits）或有 note/status 说明缺失原因
（query-not-emittable / query-partial / no-record-matched）。静默缺席即 fail。

### C6 去重计数说明
hits/coverage 中出现 duplicate、translation、view_type 等版本信息时，
必须存在去重计数说明（dedup/count once/countable/去重 字样）。同一工作的
多语种版本重复计数是本任务最典型的指标虚高。

### C7 sources 可解析
sources 非空；形如路径的条目必须真实存在。引用不存在的文件与引用不存在的
文献同性质。

### C8 无占位符
TODO/XXX/lorem/example.com/待定/占位 等模板残留一律 fail。合成示例中的
示意值不得流入正式 result.json。

## 修复优先级

fail 必须修复后才能交付；无法修复的 fail（如原文确不可得）把该检查项与原因
写入 uncertainty，status 降为 partial 后交付。warn 可以交付，但每条 warn 的
接受理由要记入 change_records。
