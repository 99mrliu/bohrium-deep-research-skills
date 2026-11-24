# 关系图谱语义（信号、边类型与 canonical 策略）

## 六类信号（机械提取，均可回查）

| 信号 | 提取方式 | 强度 |
|---|---|---|
| `sha256_equal` | 文件字节哈希相等 | 决定性：duplicate_of |
| `title_jaccard≥0.6` | 归一化标题 token 集合 Jaccard | 强：same_work 候选 |
| `arxiv_match` | 正文/文件名 arXiv 号一致 | 强：同一工作 |
| `doi_match` | DOI 一致 | 强：同一工作 |
| `version_statement` | 正文含 "published version" 等自述且共享 arXiv 号 | 强：version_of 方向依据 |
| `admin_note` | 旁挂说明中同一行互指两个文件（含 重复/正式版/预印本/canonical 关键词） | 强：人工权威来源 |

## 边类型

- `duplicate_of`：字节级重复下载；归档时仅保留组内最小 fid，其余进
  `_archive_dups/`（不删除）。
- `same_work` / `same_work_candidate`：同一工作（candidate 为仅弱信号，
  须模型 confirm 才参与 canonical 与归档判定）。
- `version_of`：版本关系，roles 标 `preprint`/`published`/`unspecified`。
- `supplement_of`：补充材料 ↔ 主文档，roles 标 `supplement`/`main`。

每条边带 `signals`（命中信号）与 `evidence`（哈希短码、标题对、正文短引或
管理员说明 文件+行号）。

## canonical 打分策略（每步进 arbitration_log.json）

| 特征 | 分值 |
|---|---|
| 含 DOI | +3 |
| 正文自称 published version | +2 |
| 含期刊/机构标识且非预印本 | +1 |
| 预印本特征（arXiv 且未声明正式版） | -1 |
| 补充材料 | -2 |
| 内容不可用（损坏/无文本层/无权限） | -3 |

裁决顺序：**管理员说明指定 > 唯一正分最高 > 单节点簇 > null**。
并列或零分 ⇒ `canonical: null`，写入 uncertainties，绝不硬选。

## 模型裁决接口（adjudication.json）

- `confirm`：把 `same_work_candidate` 升级为正式边（可改 type）；
- `reject`：删除误判边（留痕 `rejected_edges`，簇重算）；
- `canonical_overrides`：改判 canonical（必须给 reason，写 change_log）；
- `answers`：检索问题回答（带 evidence）。
