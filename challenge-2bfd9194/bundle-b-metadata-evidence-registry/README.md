# metadata-evidence-registry

科研资料库整理 Skill（challenge-2bfd9194 / 科研资料库与文件管理），重心：**元数据字段级证据链**——每个元数据字段值都必须带可回查的出处（provenance locator），填不出就诚实留空，绝不从文件名"看着像"猜。

## 核心机制

- **四级来源优先级**：L1 伴随表格/行政备注（定位到 文件#行号 / 文件#record键）> L2 文件内容首部 4KB 模式匹配（文件#行号）> L3 文件名语法（带 id 的正则集）> L4 人工/模型裁定（必须给理由，显式优先）。
- **冲突矩阵 conflicts.json**：同文件同字段多来源不同值 → winner 按级别裁定，全部候选保留标注。
- **独立校验器**：verify_registry.py 只读输入与输出，逐条重读源文件回查 locator，重算哈希核对 manifest↔目录树，输出 audit_report.json。
- 通用底座：内容哈希去重、规范化词干版本链、目录模板路由（缺字段进 `_unassigned/` 并记原因）、`__vN` 目标冲突、幂等重跑。

## 运行

```bash
python3 scripts/run_case.py all --input /input --work /app/work --out /app/output
# 自查
python3 scripts/verify_registry.py --input /input --out /app/output
```

子命令：`init / scan / extract / plan / apply / verify / finalize / all`。仅 Python 3 标准库，无网络访问，不写 /input。

## 输出（/app/output/）

`result.json`、`library/`、`LIBRARY_MANIFEST.jsonl`（带元数据子对象与 provenance 摘要）、`metadata_registry.jsonl`、`conflicts.json`、`coverage_report.json`、`duplicates.json`、`version_chains.json`、`operations_journal.jsonl`、`skipped_and_conflicts.json`、`audit_report.json`、`metadata_overrides_snapshot.json`；task.md 含检索/问题时另有 `QA_LOG.json`。详见 SKILL.md 第 8 节输出清单表。

## 人工裁定（可选）

跑完 extract 后编辑 `work/metadata_overrides.json`：
`{"<源相对路径>": {"fields": {"year": "2020"}, "reason": "裁定理由（必填）"}}`
重跑 `plan apply verify finalize` 生效；快照落入 output 供校验器回查。

## 限制

- 元数据自动抽取只覆盖：伴随表格/备注、文本首部 4KB 模式、文件名正则、人工裁定四类证据；需要全文语义理解的字段只能走 L4。
- 行政备注全局默认只接受 instrument/retention/access_scope/source_party/author，项目号与年份必须有文件级证据。
- 示例（examples/）为**合成示例**，非正式案例结果。

## 文件

`SKILL.md` 主说明 · `scripts/run_case.py` 编排器 · `scripts/registry.py` 证据链引擎 · `scripts/verify_registry.py` 独立校验器 · `references/` 字段字典与规则 · `examples/` 合成示例（含真实跑出的输出）。
