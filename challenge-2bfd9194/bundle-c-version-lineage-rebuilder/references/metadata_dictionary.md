# 元数据字典（manifest / version_graph / journal 字段）

原则：**只记录可计算、可回查的字段**。不得凭文件名猜作者/年份/项目号/仪器型号；
伴随元数据表（如 metadata.csv）有什么算什么，没有的字段标未知，不补脑。

## LIBRARY_MANIFEST.jsonl（每行一个 JSON）

| 字段 | 含义 |
|---|---|
| source_path | 材料在 /input 下的相对路径（NFC） |
| sha256 | 内容 SHA-256（64KB 流式计算） |
| size | 字节数 |
| mtime | 源文件修改时间（Unix 秒，浮点） |
| stem | 规范化词干（见 stem_normalization_rules.md） |
| role | 世系角色：`latest`（链尾）/ `superseded`（被替代）/ `alias`（别名，不重复入库）/ `orphan`（无版本关系证据） |
| library_path | 在 library/ 下的相对路径；alias 行为 `null` |
| bucket | 所属桶：papers/data/scans/supplementary/drafts/admin/_unassigned/_versions |
| alias_of / alias_of_path | 仅 alias 行：正本的 sha256 与源路径 |

## version_graph.json

| 字段 | 含义 |
|---|---|
| nodes[] | `{sha256, path, stem, mtime, size}`，覆盖全部已扫描未跳过文件 |
| edges[] | `{src_sha, dst_sha, basis, evidence, locator?}`；方向旧→新；basis ∈ `admin_note`（E1）/ `stem_mtime`（E3）/ `model`（模型裁定）；admin_note 边必有 locator=文件#L行号 |
| aliases[] | `{canonical_sha, canonical_path, alias_sha, alias_path}`（E2，非版本） |
| chains[] | 链（弱连通分量拓扑序的 sha 序列） |
| chain_meta[] | `{stem, latest_sha}`，stem 取 latest 节点词干 |
| orphans[] | 无任何边的非别名节点 sha |
| conflicts[] | `cycle` / `multi_parent` / `multi_sink` / `no_sink` / `unresolved_admin_reference` / `admin_self_edge` / `e1_overrides_e3` / `override_noop` |
| degraded | 存在未决冲突时为 true（finalize 据此报 partial） |

## operations_journal.jsonl（每行一个 JSON）

| 字段 | 含义 |
|---|---|
| seq | 顺序号（按 source_path 排序，确定性） |
| op | `copy` / `alias_record` |
| src / dst | 源相对路径 / library 内相对路径（alias 为 null） |
| sha256 / role | 同 manifest |
| status | `copied` / `already_committed_identical` / `copied_with_suffix` / `recorded_not_copied` / `failed` |

不记时间戳：保证重跑字节级幂等。重跑收敛时全部 copy 项为 `already_committed_identical`。

## result.json 关键字段

`case_id`、`status`（in_progress/complete/partial/blocked）、`contract_fields`（output_contract 镜像）、
`summary`（files_scanned/files_committed/bytes_committed/alias_groups/version_chains/version_edges/skipped/conflicts/audit_pass/audit_fail）、
`limits`、`uncertainties`、`failures_and_recovery`、`audit_overall`、`change_records`。

## 桶分类规则（缺省，task.md 可覆盖）

文件名含 备注/notes/version/版本/行政/admin → `admin/`；含 scan/扫描 → `scans/`；
扩展名 .csv/.tsv/.json/.dat/.xlsx/.xls → `data/`；含 draft/草稿/草案 → `drafts/`；
扩展名 .pdf/.doc/.docx/.tex/.bib → `papers/`；扩展名 .txt/.md → `supplementary/`；其余 `_unassigned/`。
被替代版本一律 `_versions/<链词干>/`，保留原文件名。
