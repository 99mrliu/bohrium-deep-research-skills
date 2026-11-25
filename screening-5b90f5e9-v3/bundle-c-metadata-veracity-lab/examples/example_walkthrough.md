# 示例走查（合成示例，非真实评测案例）

本目录是一个**端到端真实跑通**的合成演示：`case.json` 与
`synthetic_records.jsonl` 全部为虚构数据（9 条记录，每条故意带一种或多种
毛病），`run/` 下是脚本真实跑出的产物。真实命令与 exit code 见
`selftest_log.md`。

## 1. 合成输入的毛病设计

| record_id | 故意埋的毛病 | 期望处置 |
| --- | --- | --- |
| WOS-0001 | DOI 带 `https://doi.org/` 前缀且大写 | doi_normalize → `10.1000/jtest.2024.123` |
| PUBMED-0002 | 与 WOS-0001 同 DOI（小写+尾点）；缺 year/journal/volume/issue/pages/language | 规范化后同键 → cross_fill_by_doi 补 6 个字段，source_record_id=WOS-0001 |
| SCIELO-0003 | title 为 `InfluÃªncia…`（UTF-8-as-Latin-1）；abstract 乱码且混 U+FFFD；葡语 | title 修复为 `Influência da cafeína na atenção de idosos`；abstract 不可修复 → untrusted → quarantine；language_flag |
| CNKI-0004 | abstract 空串、DOI 占位符 "N/A"，无任何强键伙伴 | abstract/doi 保持 missing，**不补**；不进 quarantine（missing≠untrusted） |
| EMBASE-0005 | title 含 `&amp;`、`&#8212;`；abstract 含 `&lt;` 与 BEL(\x07) 控制字符；DOI 含大写段 | 实体反转义 + 控制字符删除 + DOI 小写化，三处留痕 |
| OVID-0006 | DOI `doi:10.10/abc` 畸形；year `20O5`（字母 O）；与 0007/0008 同题名但年份/期刊冲突 | DOI 保留原值+untrusted；year untrusted → quarantine；pages 经题名键由伙伴补全；journal/year 冲突**不补** |
| WOS-0007 | 缺 pages；与 PUBMED-0008 同 DOI | cross_fill 补 pages=88-95 |
| PUBMED-0008 | 干净，充当 0006/0007 的补全 donor | 无改动 |
| CNKI-0009 | 中文记录（eligible_languages 仅 en） | language=zh → language_flag（不据此排除） |

## 2. 流程与产物对照

1. `scaffold_result.py` → `run/result.json` 骨架：6 个合同字段全 null，
   status=partial。
2. `profile_fields.py` → `run/field_profile.json`：
   - 逐字段完整率（如 doi：9 条中 present 7、placeholder 1、missing 1）；
   - domain_flags：仅 OVID-0006 两条（`year_not_4digit_int`、`doi_malformed`）；
   - language_flag：SCIELO-0003(pt)、CNKI-0009(zh)。
3. `text_health.py` → `run/records_text_fixed.jsonl` +
   `run/text_health_report.json`：issues=5（2 条乱码、2 条实体、1 条控制
   字符），修复留痕 3 条，不可修复 1 条（SCIELO-0003.abstract）。
4. `repair_fields.py` → `run/records_final.jsonl` + `run/repair_ledger.json`：
   doi_normalize 3 条；cross_fill 8 处（PUBMED-0002 六处、WOS-0007 与
   OVID-0006 的 pages）；conflicts 8 条（键组内 abstract/journal/year/doi
   取值不一致，全部不补）；畸形 DOI 1 条。**记录数进 9 出 9，无合并。**
5. `trust_scores.py --finalize` → `run/trust_scores.json`（逐记录
   field_trust、quarantine=[OVID-0006, SCIELO-0003]）+ `run/result.json`
   回填：5 个合同字段填实，`screening_decisions` 保留 null（纳排判定不在
   本技能范围），status=partial，uncertainty 如实说明。

## 3. 目检结论（人工复核，非脚本输出）

- mojibake：SCIELO-0003.title 被正确还原为葡语原文；abstract 因混有
  U+FFFD 被判不可修复、原值未动——保守方向正确。
- 补全留痕：ledger 每条 change 均含 record/field/old/new/
  source_record_id/rule；PUBMED-0002 的 donor 确为 WOS-0001。
- 无可补键时不补：CNKI-0004 的 abstract/doi 在最终记录中仍为空/"N/A"，
  ledger 中无任何以它为目标的 change。
- 冲突不补：OVID-0006 的 journal 仍缺失（两源期刊名不一致），
  conflicts 清单有对应条目。
- 幂等：全套流程连跑两遍，`run/` 下产物 md5 逐字节一致
  （见 selftest_log.md）。
