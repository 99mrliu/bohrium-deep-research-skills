---
name: coverage-cartographer
description: 多数据库联合检索的覆盖完备性审计与缺口诚实化技能。对 /input 下离线材料（Crossref / Europe PMC / 出版商响应、引用图、增量导入状态）做嗅探分类、数据库盘点、检索编排审计（mechanical_copy、分页/命中数风险、查询证据缺失）、规范字段×数据库覆盖矩阵、跨源身份归并后的单一来源文献识别、标识符冲突列待仲裁，并将全部异常落入带类型/严重级/证据定位/影响陈述的缺口台账；产出 result.json（含 case_id 与全部 output_contract 字段）、gap_ledger.json、coverage_matrix.json/md、omission_report.md。任何缺口均如实声明、绝不静默吞没；台账非空即 status=partial。纯 Python 3 标准库、离线、确定性、可幂等重跑。
---

# Coverage Cartographer（覆盖制图师）

多数据库联合检索场景中，回答的不是「检到了什么」，而是「**覆盖了多少、缺在
哪里、用户因此不能下什么结论**」。本技能对组织者提供的离线材料做覆盖完备性
审计，把一切异常——缺席的数据库、系统性缺失的字段、命中数与返回数不符、
跨库元数据冲突、导入状态对不上账、引用图断点、单一来源文献——如实登记入
缺口台账，绝不静默吞没。

## 何时使用

- 案例要求多数据库联合检索（crossref / europepmc / publisher 等），且材料为
  离线响应文件，需要审计检索覆盖的完备性；
- 需要回答「哪些库/字段被覆盖、哪些文献仅单一来源、哪些缺口是系统性的」；
- 需要对检索编排（各库检索式、分页）做复核，发现逐字复制检索式、命中数与
  返回数不符等风险；
- 需要对齐增量导入状态与检索响应、检查引用图节点是否都被检索到；
- 需要交付可复核的遗漏说明（omission report）与诚实的 status / uncertainty。

不适用：需要联网发起真实检索的场景（本技能完全离线）；需要复杂模糊实体
对齐的场景（本技能采用 DOI / PMID / 标题+年份+第一作者姓的精确键归并，
重心在覆盖审计而非匹配精妙度）。

## 固定运行方式

技能安装于 `/skills/weekly-skill`，标准运行命令（在 `run_case.sh` 或等效
入口中执行）：

```bash
python3 /skills/weekly-skill/scripts/coverage_cartographer.py \
  --case /input/case.json --task /input/task.md \
  --work /app/work --out /app/output
```

四个参数均有默认值（恰为上列取值），无参运行亦可。`--help` 可用且退出码为 0。

若安装路径不确定，先定位脚本：

```bash
find / -maxdepth 6 -name "coverage_cartographer.py" 2>/dev/null
```

找到后以相同参数运行。仅依赖 Python 3 标准库；无网络；无随机性。

## 完整工作流

以下步骤中，「脚本化」表示由 `coverage_cartographer.py` 自动完成，「模型判断」
表示需要 Agent 在脚本运行前后用自然语言理解与判断完成。

1. **【模型判断】读取任务**：读 `/input/task.md` 与 `/input/case.json`，确认
   研究问题、`source_dbs` 期望集合、`output_contract` 字段及形状。
2. **【脚本化】STEP 0**：脚本在读取任何输入**之前**先向
   `/app/output/result.json` 写出 `status="partial"` 骨架（诚实降级底线）。
3. **【脚本化】材料发现与嗅探分类**：按 case.json `materials` 清单 + 案例目录
   扫描发现材料，按信封结构分类（crossref `message.items` / europepmc
   `resultList.result` / publisher JSON 数组或 JSONL / reference_graph /
   import_state / unknown），并做最小规范化（归一化 DOI、PMID、
   标题+年份+第一作者姓复合键）。
4. **【脚本化】数据库盘点**：期望集合 vs 实际材料；缺席库 → `db_absent`，
   计划外来源 → `extra_source`。
5. **【脚本化】检索编排审计**：抽取各库检索式证据（case.json / task.md /
   信封回显），对照 `references/db-capabilities.md`；逐字复制到 ≥2 个语法
   不同的库 → `mechanical_copy`；命中数与返回数不符且无翻页证据 →
   `hitcount_mismatch`；无证据 → `query_evidence_missing`（不假设）。
6. **【脚本化】字段覆盖矩阵**：12 个规范字段 × 各数据库的实际提供计数
   （coverage_matrix.json/md）；0 次提供 → `field_systematic_gap`。
7. **【脚本化】跨源身份归并与对账**：精确键并查集归并 → 单一来源文献
   （`single_source_only`）；同 DOI 跨库冲突列待仲裁（`identifier_conflict`）；
   导入状态双向对账（`import_state_gap`）；引用图节点核对
   （`referenced_not_retrieved`）。
8. **【脚本化】落盘**：result.json（case_id + 全部契约字段 + status /
   sources / uncertainty / change_records）、gap_ledger.json、
   coverage_matrix.json/md、omission_report.md；无法填充的契约字段 →
   `null` + `unresolved_contract_fields`，绝不编造。
9. **【模型判断】复核与陈述**：读 omission_report.md 与 gap_ledger.json，
   在最终答复中按严重级概述缺口；对 `identifier_conflict` 给出仲裁建议
   （脚本只列不判）；确认 status 与台账一致性（非空 ⇒ partial）。
10. **【模型判断】预算意识**：官方 Harness 约 64 次请求 / 900 秒。脚本一次
    运行即完成全部审计——预算应用于步骤 1、9 的复核与陈述，**不要**逐文件
    手工审计替代脚本，不要重复运行脚本（幂等，重跑产物字节一致）。

## 输出契约

`/app/output/` 下：

| 文件 | 内容 |
|---|---|
| `result.json` | `case_id`、`status`、`sources`、`uncertainty`、`gap_counts`、`unresolved_contract_fields`、`change_records`，外加 case.json `output_contract` 声明的**每一个**字段（list/dict/string 形状均按声明解析填充；填不出 → null + 登记） |
| `gap_ledger.json` | 缺口台账：按类型/严重级排序编号的条目，含证据定位与影响陈述 |
| `coverage_matrix.json` / `coverage_matrix.md` | 规范字段 × 数据库覆盖矩阵与系统性缺口清单 |
| `omission_report.md` | 遗漏报告：每条台账条目的证据定位与「用户因此不能得出什么结论」 |

`/app/work/normalized_records.json` 为中间产物（规范化记录），供复核。

## 状态语义

- `ok`：审计完成且台账为空（仅意味着「已提供材料范围内无缺口」）；
- `partial`：审计完成但台账非空，或输入/脚本降级——结论须以台账为准；
- `failed`：输入无效（case.json 缺失或不可解析，退出码 3）。

退出码：`0` 审计正常完成（分析性缺口体现在 status，不影响退出码）；
`2` 诚实降级（顶层异常被捕获或存在无法填充的契约字段，仍写出诚实
result.json）；`3` 输入无效。任何情况下不崩溃、不静默。

## 规则边界和维护

- **重心是覆盖审计，不是匹配精妙度**：身份归并只用 DOI / PMID /
  标题+年份+第一作者姓精确键；疑似但未证实的同文不合并、不猜测。
- **冲突列待仲裁**：`identifier_conflict` 只列出各来源取值，脚本不裁决。
- **无证据不假设**：查询证据缺失记 `query_evidence_missing`；命中数不符
  记 `hitcount_mismatch`；不得编造分页或检索式证据。
- 能力阈值与缺口分类的权威说明在 `references/db-capabilities.md` 与
  `references/gap-taxonomy.md`；修改脚本中的阈值/模板时须同步更新参考文档。
- 不修改 `/input`；所有写入限于 `--work` 与 `--out`。

## 确定性与自查

- 纯标准库、无网络、无随机性、产出物不含墙钟时间；同输入重跑字节一致。
- 自查清单（交付前逐项确认）：
  1. `--help` 退出码 0；
  2. 案例运行后 `result.json` 含 case_id 与全部契约字段，status 与台账一致；
  3. `gap_ledger.json` 每条目有 type/severity/evidence/impact；
  4. `coverage_matrix.md` 表格渲染正确；
  5. 重跑两次产物 byte-identical；
  6. 未写入 `/input`，无网络调用。

## 示例

`examples/synthetic-input/` 为**合成教学数据**（虚构案例
`synthetic-coverage-001`，伪造 DOI 前缀 10.99955，标题均为 "Synthetic ..."，
仅用于演示审计逻辑，非真实文献）：内置全部典型异常各若干——命中数不符、
字段系统性缺口、单一来源文献、标识符冲突、引用图断点、导入状态幻影子记录、
机械复制检索式、出版商库查询证据缺失。`examples/synthetic-output/` 为对该
输入**真实运行脚本**得到的产物，`run-record.md` 记录了运行命令、
「埋设异常 vs 检出结果」对照表与重跑确定性验证。
