# 合成示例说明（合成示例，非正式案例结果）

本目录为**虚构 mini 材料**，仅用于演示三个脚本的用法与陷阱拦截能力，与任何真实基金申请无关。

## 文件

| 文件 | 内容 |
|---|---|
| `materials/external_paper_excerpt.txt` | 虚构"外部论文节选"：含 87.3%、n=120、62 kJ/mol 等数字结论 |
| `materials/applicant_prior_records.txt` | 虚构"申请人前期记录"：含 0.8%/h、41.6%、280 °C 等自检数据 |
| `materials/organizer-workorder.json` | 虚构组织方工单片段：声明"真实申请人证据明确缺失时按缺失处理" |
| `evidence_map.json` | **含 2 个陷阱**：E2 把外部工作错标为 `已完成`；E3 的 quote 经过改写、未逐字命中原文 |
| `proposal_sections.md` | **含 1 个陷阱**：拟开展部分出现无出处数字 "42%" |
| `evidence_map_fixed.json` / `proposal_sections_fixed.md` | 修复版输入（修复方式见下） |
| `whitelist.json` | 案例年份白名单 `["2021", "2023"]`（与内置 0-9 单位数白名单合并） |

## 运行命令与真实结果

以下命令在本机真实执行，产物写入 bundle 之外的
`/Users/liuhengshen/Desktop/bhr_product/writing14/example-runs/grant-a-evidence-anchor/`
（下称 `$R`；`$B` 为 bundle 根目录）。退出码为真实返回值。

### 1. 盘点材料（exit=0）

```
python3 $B/scripts/extract_sources.py --input $B/examples/materials --out $R
```

输出摘录：

```
盘点完成：3 个文件（0 个 unreadable），inventory -> $R/materials_inventory.json
  [copied] applicant_prior_records.txt (applicant-record, 398 bytes, md5=843f3ff0)
  [copied] external_paper_excerpt.txt (notes-or-draft, 482 bytes, md5=7b8ab838)
  [copied] organizer-workorder.json (organizer-workorder, 339 bytes, md5=20e20d3f)
```

三个文本文件复制进 `$R/src_text/`；`applicant_prior_records.txt` 因文件名含"记录"
被猜为 `applicant-record`（source_class_guess=applicant）。

### 2. 锚定核验 · 陷阱版（exit=1，抓到 2 个陷阱）

```
python3 $B/scripts/anchor_audit.py --evidence $B/examples/evidence_map.json \
  --src-text $R/src_text --inventory $R/materials_inventory.json \
  --out $R/anchor_audit_report_trap.json
```

真实输出：

```
锚定核验：5 条，error=2，warning=1 -> $R/anchor_audit_report_trap.json
  [ERROR] E2: status=已完成 但来源类别为 external：原论文/既有成果归外部作者，不得记为申请人已完成（应改为 外部工作）
  [ERROR] E3: quote 未逐字命中来源文本（疑似改写/凭印象引用）
  [WARN ] E5: 引用缺年份要件
```

E3 的诊断（报告中 `diagnosis` 字段）指出 quote 与原文的最长公共片段只有 9 个字符，
并给出来源原文上下文 `表面氧空位浓度与表观活化能(62 kJ/mol)呈负相关。`，
与改写后的 quote `表面氧空位浓度和表观活化能 62 kJ/mol 之间呈负相关关系` 对照即知差异所在。

### 3. 无出处数字扫描 · 陷阱版（exit=1，抓到 1 个无出处数字）

```
python3 $B/scripts/orphan_scan.py --proposal $B/examples/proposal_sections.md \
  --evidence $B/examples/evidence_map.json --whitelist $B/examples/whitelist.json \
  --out $R/orphan_report_trap.json
```

真实输出：

```
无出处数字扫描：1 处；占位符 {'【待确认】': 0, '【待申请人确认：…】': 1} -> $R/orphan_report_trap.json
  [ORPHAN] proposal_sections.md:9 数字 '42%' 无出处 | 拟通过氧空位调变将甲烷转化率提升 42%,并阐明其与表观活化能的关系。
```

（0.8%、280、41.6%、87.3% 均命中 quote；2021 在白名单；5 命中内置单位数白名单。）

### 4. 修复版（exit=0）

修复方式：
- E2：`status` 由 `已完成` 改为 `外部工作`（claim 同步改为"外部工作报道…"）；
- E3：`quote` 改为逐字原文 `表面氧空位浓度与表观活化能（62 kJ/mol）呈负相关。`；
- 章节稿：删去无出处数字 "42%"（改为"具体量化指标待实验确定"），删去无出处篇数 "5 篇"。

```
python3 $B/scripts/anchor_audit.py --evidence $B/examples/evidence_map_fixed.json \
  --src-text $R/src_text --inventory $R/materials_inventory.json \
  --out $R/anchor_audit_report_fixed.json
# 锚定核验：5 条，error=0，warning=1（E5 引用缺年份，warning 不阻断）  exit=0

python3 $B/scripts/orphan_scan.py --proposal $B/examples/proposal_sections_fixed.md \
  --evidence $B/examples/evidence_map_fixed.json --whitelist $B/examples/whitelist.json \
  --out $R/orphan_report_fixed.json
# 无出处数字扫描：0 处；占位符 {'【待确认】': 0, '【待申请人确认：…】': 1}  exit=0
```

### 5. 确定性验证（二次运行字节一致）

对三个脚本以相同参数二次运行到 `$R/rerun/`，`diff` 逐字节比对：

```
materials_inventory.json       identical
anchor_audit_report_fixed.json identical
orphan_report_fixed.json       identical
```
