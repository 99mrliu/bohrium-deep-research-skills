# 自测记录（selftest_log）

日期：2026-11-20。环境：macOS arm64，Python 3（仅标准库）。
模拟运行时：`/tmp/st-c-model/{input,work,output}`（dual_model 模式）与
`/tmp/st-c-fixture/{input,work,output}`（dual_fixture 模式），数据全部来自
examples/ 的**合成虚构**示例。填表/仲裁/result.json 填充步骤由 harness 复制
filled_*.json 模拟模型批量请求；其余全部为 skill 脚本真实执行。

## A. dual_model 全流程（/tmp/st-c-model）

| 步骤 | 命令（要点） | exit |
|---|---|---|
| 解析案例 | parse_case.py --input-dir .../input --work .../work → mode=dual_model, contract=19 字段 | 0 |
| 落盘骨架 | scaffold_result.py → result.json 19 字段 | 0 |
| 幂等重跑 | scaffold_result.py（再次）→ 已存在未覆盖 | 0 |
| 导入记录 | load_records.py → 9 条 | 0 |
| 精确去重 | exact_dedup.py → identified=9 removed=1 screened=8 suspected=0 | 0 |
| 生成双表 | prepare_sheets.py → sheet_s1(正序)/sheet_s2(逆序) 各 8 行空白槽 | 0 |
| 模拟两次独立填写 | cp filled_s1/s2.jsonl → annotations_s1/s2.jsonl | — |
| 校验 S1 | validate_annotations.py --sheet annotations_s1.jsonl → 8 条通过 | 0 |
| 校验 S2 | validate_annotations.py --sheet annotations_s2.jsonl → 8 条通过 | 0 |
| **负例：锚定破坏** | 篡改 R01 evidence_quote 后 validate → 写 validation_errors_annotations_s1.json | **3**（符合预期） |
| 修复重跑 | 还原后 validate | 0 |
| 一致性 | agreement.py → agree=5 disagree=3, kappa_3class=0.4146, kappa_binary=0.3846 | 0 |
| **负例：仲裁缺失** | arbitrations.json 只放 2 条 → adjudicate 写 adjudication_errors.json | **3**（符合预期） |
| 修复仲裁 | 完整 3 条仲裁 → include=2 exclude=4 needs_human=2 | 0 |
| 审计链 | audit_log.py → 3 条闭合等式 diff=0，audit.jsonl 8 阶段 | 0 |
| 填充 result.json | harness 按 SKILL.md 第 4 节映射表填充 19 字段 | — |
| 终检 | selfcheck.py → 合同齐/kappa 一致/3 分歧全仲裁/人工门 2 条一致/计数闭合 | 0 |

## B. dual_fixture 流程（/tmp/st-c-fixture，input 额外含 fixture_annotations.json）

| 步骤 | 结果 | exit |
|---|---|---|
| parse_case.py | 嗅探到文件名标记 annotation → mode=dual_fixture, fixtures=1 | 0 |
| scaffold_result.py | 骨架落盘 | 0 |
| load_records.py | 9 条记录 + external_annotations.json（fixture 原样 + 输入 fixture 声明） | 0 |
| exact_dedup.py | identified=9 removed=1 screened=8 | 0 |
| prepare_sheets.py | fixture 组 FX-A/FX-B → annotations_s1/s2.jsonl（source=external_fixture）；R02 标注指向已去重记录，丢弃并写 fixture_dropped.json | 0 |
| validate_annotations.py ×2 | 各 8 条通过 | 0 |
| agreement.py | agree=5 disagree=3（R05/R06/R07），kappa_3class=0.4146, kappa_binary=0.3846 | 0 |
| adjudicate.py | D1(R05→include, 回写标准解释) / D2(R06→exclude) / D3(R07→needs_human) | 0 |
| audit_log.py | 3 条闭合等式 diff=0 | 0 |
| selfcheck.py | 全部通过 | 0 |

## C. 其他核查

- 10/10 脚本 `--help` exit 0。
- final_labels.jsonl 抽查：R07（仲裁 D3）与 R09（双方一致 uncertain 升级）
  human_confirmation_required=true、final_decision=needs_human，其余为一致/仲裁判定。
- disagreements.json 每条含双方 decision/reason_code/evidence_quote 对照及题录原文。
- 关键数值（两种模式一致）：一致率 5/8=0.625；终判 include=2 / exclude=4 /
  needs_human=2；闭合等式 9=1+8、8=8=8、8=2+4+2 均 diff=0。
- kappa 独立复核：用纯 Python 按列联表手工重算（S1 边际 3/3/2，S2 边际 1/6/1，
  pe=0.3594，po=0.625）与 agreement.py 输出 0.4146 一致；二分类 0.3846 一致。
