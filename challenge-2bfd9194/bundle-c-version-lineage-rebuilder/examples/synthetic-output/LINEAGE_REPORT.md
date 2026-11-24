# 版本世系报告（LINEAGE_REPORT）

> 自动生成。证据等级：E1 行政备注（admin_note）> E2 内容哈希（别名，非版本）> E3 词干+mtime（stem_mtime 候选）。**无证据不连边。**
> 边方向：旧版本 → 新版本（supersedes）。

## 链 1：词干 `scan_final`（2 个版本）

版本序列（旧 → 新）：
1. `scan_old.pdf`（size=94B, mtime=1795533172）
2. `scan_final.pdf`（size=99B, mtime=1795533172） **（latest）**

边依据：
- `scan_old.pdf` → `scan_final.pdf`：basis=admin_note；evidence: 行政备注原文: 1. scan_final.pdf 替代 scan_old.pdf，旧件仅存档备查。；locator: `admin_notes.txt#L2`

## 链 2：词干 `report`（3 个版本）

版本序列（旧 → 新）：
1. `report_v1.txt`（size=97B, mtime=1795533172）
2. `report_v2.txt`（size=103B, mtime=1795533172）
3. `report_最终版.txt`（size=112B, mtime=1795533172） **（latest）**

边依据：
- `report_v1.txt` → `report_v2.txt`：basis=stem_mtime；evidence: size_delta=+6B; mtime_delta=0s; stem=report
- `report_v2.txt` → `report_最终版.txt`：basis=stem_mtime；evidence: size_delta=+9B; mtime_delta=0s; stem=report

## 别名组（同内容不同名，**不是**版本关系）

- 正本 `实验数据备份.txt` ← 别名 `data_copy.txt`（sha256 相同，不重复入库）

## 孤儿节点（无版本关系证据，正常入库）

- `admin_notes.txt`
- `metadata.csv`
- `projA/notes.txt`
- `projB/notes.txt`
- `实验数据备份.txt`
- `实验记录_2024春.txt`

---
链数=2，边数=3，别名=1，孤儿=6，冲突=0，degraded=false
