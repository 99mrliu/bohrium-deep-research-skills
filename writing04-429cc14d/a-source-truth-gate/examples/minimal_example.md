# 最小调用示例（合成示例）

> **⚠ 本目录全部内容均为虚构合成数据，不对应任何真实文献。**
> 论文、作者、DOI、期刊、数据、快照、论断全部为演示而编造。

本示例演示 source-truth-gate 三个脚本的调用方式、状态机判定与退出码语义。
`input/` 中埋了 3 处缺陷（booby trap），脚本应当精确捕获它们。

## 埋雷清单

| 位置 | 缺陷 | 预期判定 |
| --- | --- | --- |
| entries.jsonl 的 E5 | DOI `10.1234 /bogus.2024.001` 含空格，语法非法 | suspected_fabricated |
| entries.jsonl 的 E6 | year=2021 与快照记录（2020）冲突 | metadata_conflict |
| claims.jsonl 的 C4 | quote 删去"无量纲"三字，是转述而非逐字引文 | FAIL（paraphrase_or_minor_alteration） |

## 步骤 1：来源登记

```bash
cd skill/   # 本 bundle 根目录
python3 scripts/source_registry.py \
  --sources examples/input/sources \
  --out examples/output/source_registry.json
echo $?
```

预期：退出码 0；输出登记 3 个 txt 文件的 SHA-256、字节数，警告 0 条。
（评测环境中路径写作 `python3 /skills/weekly-skill/scripts/source_registry.py ...`。）

## 步骤 2：条目核验

```bash
python3 scripts/verify_entries.py \
  --entries examples/input/entries.jsonl \
  --snapshot examples/input/snapshot.json \
  --out examples/output
echo $?
```

预期：**退出码 1**（检出必须隔离/修复的条目）。汇总应为：
verified_identity=4（E1–E3 按 DOI 确认，E4 无 DOI 按标题确认，note: by_title）、
suspected_fabricated=1（E5，reason: invalid_doi_syntax）、
metadata_conflict=1（E6，conflicts 列出 year: 2021 → 2020）。
产物：`examples/output/verification_report.json` 与 `.md`。

处置演示：E5 隔离登记、禁止引用；E6 以快照为准把 year 改为 2020 后重验，
则该条转为 verified_identity。

## 步骤 3：论断锚点审计

```bash
python3 scripts/claim_anchor_audit.py \
  --sources examples/input/sources \
  --ledger examples/input/claims.jsonl \
  --out examples/output
echo $?
```

预期：**退出码 1**。汇总应为：PASS=4（C1、C2、C3、C5，附 char_offset；
C2 的 locator "第 3 节" 在来源中出现，locator_found_in_source=true）、
FAIL=1（C4，diagnosis: paraphrase_or_minor_alteration，最相似窗口相似度
约 0.93，窗口文本含被删去的"无量纲"原文）。
产物：`examples/output/anchor_report.json` 与 `.md`。

处置演示：把 C4 的 quote 改回来源逐字文本后重跑，退出码变为 0。

## 步骤 4：修复版验证（退出码 0）

修复 entries.jsonl（E5 DOI 去空格——若快照仍无记录则为 not_found_in_snapshot，
属警告不阻断；E6 year 改 2020）与 claims.jsonl（C4 quote 改逐字）后重跑步骤
2、3，两者退出码均应为 0。

## 输出文件来源声明

`examples/output/` 中的 5 个文件（source_registry.json、verification_report.json/.md、
anchor_report.json/.md）是上述命令在埋雷输入上的**真实运行产物**，逐字复制而来，
未做任何手工编辑。复跑步骤 1–3 可逐字节重现（时间戳固定为
1970-01-01T00:00:00Z，除非设置 SOURCE_DATE_EPOCH）。
