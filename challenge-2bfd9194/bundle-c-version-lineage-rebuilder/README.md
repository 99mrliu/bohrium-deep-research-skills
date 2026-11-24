# version-lineage-rebuilder

科研资料库**版本世系图谱重建** Skill（Bohrium Playground challenge-2bfd9194，bundle C）。
回答一个问题：**谁替代了谁，差异在哪里**——并要求每条版本边都有可回查的证据。

## 核心机制：三级证据，无证据不连边

| 级别 | 依据 | 产物 |
|---|---|---|
| E1 | 行政版本备注解析（"X 替代 Y" / "X 作废，以 Y 为准" / "X supersedes Y"…），locator=文件#行号 | `basis=admin_note` 边，最高优先 |
| E2 | 内容 SHA-256 相同 | 别名组（**不是版本**），不重复入库 |
| E3 | 规范化词干相同 + 同扩展名 + 内容不全同，组内按 mtime 相邻 | `basis=stem_mtime` 候选边 |

- 别名（同内容不同名）与版本（同词干不同内容）严格区分。
- E1 优先于 E3；E1 指认的文件对词干不同也照连。
- 备注类文件（notes/备注/行政…）不参与 E3 分组——两个项目的同名 notes.txt 不会被误判为版本。
- 成环不强行断环、多父不自动选边：记 conflicts 降级 partial，模型写 `work/lineage_overrides.json` 裁定后重跑生效。

## 运行

```bash
python3 scripts/run_case.py all --input /input --work /app/work --out /app/output
```

子命令：`init / scan / lineage / plan / apply / verify / finalize / all`，全部幂等。
独立校验：`python3 scripts/verify_lineage.py --input /input --out /app/output`（只读两目录，出 audit_report.json）。

## 输出（/app/output/）

`result.json`（诚实 status）、`library/`（latest 规范化名入主目录，superseded 进 `_versions/<词干>/`）、
`LIBRARY_MANIFEST.jsonl`（每行带 latest/superseded/alias/orphan 角色）、`version_graph.json`、
`LINEAGE_REPORT.md`、`duplicates.json`、`operations_journal.jsonl`、`skipped_and_conflicts.json`、
`audit_report.json`；task.md 含问题时由模型写 `QA_LOG.json`。

## 目录

```
SKILL.md            harness agent 唯一会认真读的文件（三级证据判定规则全文）
scripts/run_case.py         分阶段编排器（仅标准库）
scripts/lineage.py          世系引擎：备注解析/词干规范化/建图/环检测/报告渲染
scripts/verify_lineage.py   独立校验器：重算+locator 回查+拓扑健全+清单一致
references/         词干规范化规则、备注句式正则清单、元数据字典
examples/           合成示例（明确标注，非正式案例）与真实跑出的输出
```

## 限制

- 仅 Python 3 标准库；无网络；不写 /input；全部 UTF-8 文本。
- 不做行级内容 diff（边 evidence 只有 size_delta 与 mtime_delta）。
- 文件名含空格的名字无法被备注句式捕获（字符类限制，见 references/admin_note_grammar.md）。
- mtime 不可靠（如拷贝拉平）时 E3 组内顺序退化为文件名字典序，仍确定性可复现，但 latest 需人工按 E1 或内容确认。
- examples/ 为合成示例，不内置任何正式案例答案。
