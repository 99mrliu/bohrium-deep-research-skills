---
name: metadata-veracity-lab
description: 系统性文献检索与纳排筛选流程中的"字段级元数据可信度与保守修复所"。假设题录已被解析成结构化记录，本 Skill 管的是"每个字段能不能被下游信任"：先做逐字段画像（完整率、占位符、年份/页码/DOI 取值域 sanity、语种鉴定与 eligible_languages 比对），再做编码与文本健康检查（mojibake/乱码启发式、HTML 实体残留、控制字符，可安全修复的修复并留痕、不可修复的标记），然后做 DOI 形态校验与规范化（不联网）和快照内保守补全（仅凭规范化 DOI 或规范化题名强键、键组内取值唯一才补、只补字段不合并记录、逐字段留痕），最后输出逐记录 field_trust 与 quarantine 清单供下游判定证据可用性。Use when a screening task gives parsed citation records (离线快照、/input/case.json 含 output_contract) and you must handle DOI 缺失、摘要为空、编码乱码、数据库导出格式不一致、占位符、非英文记录 before any downstream trust or screening use (元数据可信度, 字段画像, mojibake, DOI 规范化, 保守补全, 修复台账, field_trust, quarantine, /app/output/result.json).
---

# 字段级元数据可信度与保守修复所（metadata-veracity-lab）

## 适用场景与边界（红线）

**适用**：评测/真实任务已把 RIS、CSV、JSON 等导出**解析成结构化题录记录**
（每条记录含 record_id 与 title/abstract/doi/year 等字段），需要在纳排判定
或证据抽取**之前**回答"每条记录的每个字段能不能被信任"：

- DOI 缺失、占位符（"N/A"、"."）、形态畸形、带 `https://doi.org/` 前缀或尾标点；
- 摘要为空、标题含 mojibake（如 `InfluÃªncia`）、HTML 实体（`&amp;`）、控制字符；
- 年份越界或形如 `20O5`、页码形态异常；
- 同一快照内不同来源的重复导出互有缺字段（可保守补全）；
- 非英文记录需要与 eligible_languages 比对并标记。

**红线（明确不做，越界即错）**：

1. **不做格式解析与计数审计**——题录解析、导出格式识别、计数闭合是上游
   （如 ingest-forensics 类技能）的职责；本技能的输入必须是已解析记录。
2. **不做记录合并/去重判定**——保守补全只补字段，记录条数进出一致；
   重复记录的去留是别的方向的职责。
3. **不联网**——DOI 只做形态校验与规范化，不做注册解析；语种用启发式，
   不调用外部服务；无强键可补的字段宁可空缺。
4. **不做纳排判定本身**——输出 field_trust 与 quarantine 供下游使用；
   合同中的 screening_decisions 一类字段保留 null 并在 uncertainty 说明。
5. **不伪造人工复核**——标注者僵持/双人意见冲突不属于字段级事实，
   本技能不裁决，只在不确定中标注。
6. **不预置答案**——全部产物由脚本从当次输入真实计算；示例仅为合成演示。

## 运行环境

- Python 3 标准库，零第三方依赖；脚本位于 `scripts/`。
- 退出码约定：**0** 成功；**2** 运行/IO 错误（输入缺失、不可解析）；
  **3** 合同不满足（case.json 缺 case_id/output_contract、缺前置产物、
  result.json 骨架未建立）。所有脚本顶层 try/except 兜底，绝不以
  traceback 崩溃退出。
- 路径默认值均可覆盖：`--case /input/case.json`、`--work /app/work`、
  `--output /app/output`、`--records /app/work/records_text_fixed.jsonl`。
- **幂等**：重复运行产出逐字节一致；scaffold 对已有 result.json 只做
  增量补键、绝不覆盖非 null 值；finalize 不重复追加 uncertainty。
- 输入记录格式：JSONL（每行一个对象）或 JSON 数组或含
  `records`/`citations`/`references` 键的对象；缺 record_id 自动编号。

## 工作流程

1. **[脚本] 落 result.json 骨架（最先做）**
   `python3 scripts/scaffold_result.py --case /input/case.json --output /app/output`
   读取 case_id 与 output_contract 全部字段名，骨架字段一律 null，
   status=partial。此后每步完成可增量更新。
2. **[模型] 通读 task.md 与 case.json**，确认 eligible_languages、记录来源
   与 output_contract 语义；把记录整理为 JSONL 放入 /app/work（若 case.json
   已内嵌记录数组可直接指向）。**不解析原始导出格式**（红线 1），只承接
   已解析记录。
3. **[脚本] 字段画像**
   `python3 scripts/profile_fields.py --records <records.jsonl> --case /input/case.json --work /app/work`
   产出 `field_profile.json`：逐字段完整率/占位符统计、取值域 domain_flags
   （年份范围 1800–当前年+1、页码形态、DOI 形态）、逐记录语种鉴定与
   language_flag。
4. **[脚本] 编码与文本健康**
   `python3 scripts/text_health.py --records <records.jsonl> --work /app/work`
   产出 `records_text_fixed.jsonl`（安全修复后记录）与
   `text_health_report.json`（issues + 逐条修复留痕 + 不可修复清单）。
5. **[脚本] 标识符规范化与保守补全**
   `python3 scripts/repair_fields.py --records /app/work/records_text_fixed.jsonl --work /app/work`
   产出 `records_final.jsonl` 与 `repair_ledger.json`（doi_normalize /
   cross_fill_by_doi / cross_fill_by_title 留痕、conflicts、doi_flags）。
6. **[脚本] 信任分汇总并回填 result.json**
   `python3 scripts/trust_scores.py --work /app/work --output /app/output --records-source <records.jsonl> --finalize`
   产出 `trust_scores.json`（逐记录 field_trust、quarantine、language_flags）、
   `repair_ledger.json`（交付副本），并按合同字段名回填 result.json；
   填不了的合同字段保留 null 并在 uncertainty 说明，status 如实。
7. **[模型] 目检与复核**：抽查 mojibake 是否被正确修复/标记、补全留痕的
   source_record_id 是否正确、无强键记录是否确实未补、quarantine 理由
   是否成立；把人工目检结论写入 uncertainty（不冒充脚本结论）。
8. **[脚本] 交付前自查**
   `python3 scripts/selfcheck.py --bundle <skill目录> --result /app/output/result.json`

## 输出合同映射

| output_contract 字段名（小写包含） | 回填内容 |
| --- | --- |
| `profile` / `completeness` | field_profile 汇总（逐字段完整率与统计） |
| `trust` | 逐记录 field_trust（trusted/repaired/filled/missing/untrusted + 理由） |
| `repair` / `ledger` / `change` | 修复台账（changes + conflicts + doi_flags） |
| `quarantine` | 含 untrusted 关键字段或不可修复乱码的记录清单及理由 |
| `language` | language_flag 记录及语种鉴定细节 |
| `decision` / `screening` / `inclusion` / `exclusion` | **不填**（红线 4），保留 null + uncertainty |
| 其他无法映射字段 | 保留 null + uncertainty 说明 |

result.json 基础键恒含：`case_id`、`status`（success/partial/failed 如实）、
`sources`、`uncertainty`、`change_records`（= 台账 changes + 冲突说明）。

## 异常处理表

| 情形 | 识别位置 | 处置 | 留痕/标记 |
| --- | --- | --- | --- |
| DOI 缺失或占位符（"N/A"、"."） | profile / repair | 视为 missing；有强键伙伴则补，否则不补 | field_trust=missing 或 filled |
| DOI 畸形（去前缀/小写/去尾标点后仍不符 `10.\d{4,9}/`） | profile / repair | 保留原值，不臆造，不联网 | doi_flags + field_trust=untrusted |
| 摘要为空 | profile | 不补（除非强键伙伴唯一持有） | field_trust=missing；missing≠排除 |
| 编码乱码可修复（`Ã©` 型，修复后校验通过） | text_health | 整串或逐簇 Latin-1→UTF-8 round-trip 修复 | issue=mojibake…repaired + old/new 留痕 |
| 编码乱码不可修复（混 U+FFFD、混合编码） | text_health | 保留原值，绝不猜改 | flagged_untrusted → 进 quarantine |
| HTML 实体残留（`&amp;`、`&#233;`） | text_health | html.unescape 安全反转义 | 留痕 old/new |
| 控制字符/零宽字符/内嵌 BOM | text_health | 删除 | 留痕 |
| 导出格式不一致（前缀 DOI、尾标点、大小写） | repair | doi_normalize 规范化 | rule=doi_normalize 留痕 |
| 年份越界/非 4 位数字、页码形态异常 | profile | 不改写 | domain_flags → field_trust=untrusted |
| 非英文记录 vs eligible_languages | profile | 字符脚本+停用词启发式判定 | language_flag（低置信度仅供参考） |
| 键组内取值冲突（两源年份/期刊不一致） | repair | **不补**，冲突双方皆不采信 | conflicts 清单 |
| 标注者僵持/双人意见冲突 | — | 非字段级事实，不裁决 | uncertainty 标注后移交下游 |

## 最小调用示例

```bash
# 在评测容器内（路径均为默认值，可显式覆盖）
python3 scripts/scaffold_result.py            # 1. 骨架
python3 scripts/profile_fields.py --records /app/work/records.jsonl
python3 scripts/text_health.py   --records /app/work/records.jsonl
python3 scripts/repair_fields.py              # 默认吃上一步产物
python3 scripts/trust_scores.py  --records-source /app/work/records.jsonl --finalize
python3 scripts/selfcheck.py --result /app/output/result.json
```

离线合成示例见 `examples/`（含合成 case.json、带毛病的题录、真实跑出的
台账与信任分、example_walkthrough.md、selftest_log.md）。

## 维护信息

- 版本：v1.0.0（2026-11-25）
- 维护方：bohrium-deep-research-skills 项目组
- 仓库：https://github.com/99mrliu/bohrium-deep-research-skills/tree/main/screening-5b90f5e9-v3/bundle-c-metadata-veracity-lab
- 参考文档：`references/field_trust_model.md`（信任分模型与修复规则表）、
  `references/encoding_and_identifier_notes.md`（编码与标识符处置细则）
