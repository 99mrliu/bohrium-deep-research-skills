# 元数据字典（清单与报告字段）

## LIBRARY_MANIFEST.jsonl（每输入文件一行）

| 字段 | 含义 |
|---|---|
| `src` | 输入内相对路径（NFC） |
| `target` | 库内相对路径（`library/...`）；复制失败为 null |
| `src_sha256` / `dst_sha256` | 源端 / 目标端流式 SHA-256 |
| `fixity_match` | 双端哈希一致=true；未复制为 null |
| `forensic_verdict` | authentic / type_mismatch / corrupt_suspect / empty / unreadable |
| `forensic_evidence` | 取证证据（head_hex、截断检查、编码探测、错误信息） |
| `alias_of` | 内容重复的 canonical 源路径；非别名为 null |
| `version_stem` | 剥离版本/别名/备份/尾日期后的规范化词干 |
| `action` | committed / already_committed_identical / alias_recorded / copy_failed |
| `copied` | 是否实际落盘到 target |

## FORENSICS_REPORT.json

`root / generated_at / file_count / verdict_counts / records[]`；
每条 record：`path, size, mtime, sha256, extension, detected_type, encoding, verdict, evidence`。

## result.json（契约镜像）

| 字段 | 含义 |
|---|---|
| `case_id` | 防御式解析；缺失记 `unknown_case` |
| `contract_fields` | output_contract 字段名 → 交付物相对路径（映射不了给 value=null + reason） |
| `status` | in_progress / complete / partial / blocked（与 audit 一致，有隔离项至多 partial） |
| `sources` | 全部输入文件相对路径 |
| `uncertainties` | 隔离项、缺失输入、未决问题等逐条列明 |
| `change_records` | 阶段完成与模型人工裁定记录 |
| `failures_and_recovery` | 异常、traceback 尾部与恢复方式 |
| `summary` | 文件数/字节/verdict 统计/重复组/版本链/跳过/冲突/audit 结果 |
| `limits` | partial 时的降级项说明 |

## duplicates.json / version_chains.json / operations_journal.jsonl

- duplicates：`groups[] = {sha256, canonical, aliases[], reason}`，canonical=mtime 最早。
- version_chains：`chains[] = {stem, members[], distinct_contents, edges[]}`，边 `{from,to,relation=supersedes}` 按 mtime 升序。
- journal：逐操作一行 `{seq,time,stage,action,src,dst,status}`，末尾 `event=stage_complete` 闭合。
