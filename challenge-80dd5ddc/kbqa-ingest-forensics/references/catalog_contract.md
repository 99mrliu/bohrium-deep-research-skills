# 编目契约（catalog contract）

本契约定义 bundle 1 编目产物的事实标准。任何下游问答、版本判断、引用定位
都必须以 `catalog.json` + `lineage.json` 的记录为准；编目未覆盖的文件
不得作为证据引用。

## catalog.json（schema: kbqa-ingest-forensics/catalog/v1）

每条文件记录：

| 字段 | 含义 | 核验方式 |
|-|-|-|
| file_id | 稳定编号 F001…（一次扫描内唯一） | catalog_check 复核 |
| relpath | 相对输入根的路径 | 与磁盘逐一对应 |
| sha256 | 内容哈希，即版本坐标 | catalog_check 独立重算 |
| size / mtime | 字节数 / 修改时间（UTC） | os.stat |
| text_status | ok / unreadable / no_text_layer / unsupported_type / extraction_tool_missing / extraction_failed / empty | 七态枚举，禁止其他取值 |
| n_lines / extracted | 抽取文本行数 / work 内行号化文本路径 | 抽查比对 |
| byte_duplicate_of | 同哈希首件的 file_id | 重复组判定 |

`byte_duplicate_groups` 列出全部同哈希组；`skipped` 记录符号链接等
非普通文件；`stats` 给出七态计数。`text_status` 非 ok 的文件一律不得引用，
必须进入修复台账。

## lineage.json（schema: kbqa-ingest-forensics/lineage/v1）

- relations：byte_duplicate（同 SHA-256）、alias（异名近同，Jaccard≥0.85）、
  revision_chain（版本链）。每条 relation 携带机器依据字符串，禁止无依据判定。
- version_groups：每个版本组内成员按角色排序：current（当前有效）/
  current_copy（当前版本的字节副本）/ historical（历史版本）。
- admin_note_claims：行政备注的指认原文与坐标（file_id:L行），供人工复核。

## repair_ledger.json（schema: kbqa-ingest-forensics/catalog-check/v1）

台账动作类型：quarantine_duplicate / designate_current_version /
needs_attention / catalog_gap。状态枚举：proposed / applied / skipped /
failed。诚实性硬约束：**只提议未执行的动作一律为 proposed，不得写成
applied**；catalog_gap 一律为 failed 并要求重跑扫描。

## 六维覆盖自查（对应评分"结果完整性"）

编目交付前逐项确认：文件类型（suffix 分布）、元数据字段（本表字段无空缺
或显式 null）、目录层级（relpath 全量）、重复文件（byte_duplicate_groups）、
版本差异（version_groups + historical）、权限与来源（unreadable 与 skipped
清单）。任何一维为空必须在 result.json 的 uncertainty 中说明原因。
