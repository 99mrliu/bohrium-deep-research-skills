# slr-claim-backlink — 综述论断回链审计 Skill

系统性文献综述（challenge-51977f9b）五 bundle 之一。重心：**下游论断审计**——
综述正文的每条论断必须回链到可机器解析的证据位置，治理"综述里的论断找不到
回链的原文位置"这一复发性故障。

## 用途

- 把材料（全文文本、题录）切成带定位的 span 并建确定性索引（spans.json）。
- 论断先登记为 claims.jsonl（含 fact/inference/uncertain 强度标签），脚本逐条
  核验：quote 是否指定 span 的 verbatim 子串、span 是否悬空、强度措辞是否越界、
  fact 是否无证据、uncertain 是否说明原因、孤儿证据与冲突对登记。
- 生成论断 × 文献覆盖矩阵（evidence_matrix.csv）、论断-证据对照表（coverage.md）
  与冲突证据矩阵（conflict_matrix.md）。

## 布局

```
SKILL.md                本体（完整综述链工作流 + 输出合同映射 + 异常处理）
scripts/
  parse_case.py         case.json → case_summary.json
  scaffold_result.py    result.json 骨架（skill_name=slr-claim-backlink）
  index_sources.py      材料目录 → spans.json（确定性，重跑逐字节一致）
  audit_claims.py       签名引擎：C1–C7 论断回链审计
  build_matrix.py       覆盖矩阵 / 对照表 / 冲突矩阵
  selfcheck             全量自检（正负例断言 + py_compile）
references/             强度三分与词表 / span 定位规范 / 冲突与空白登记
examples/               合成示例（含 negative/ 埋雷输入），数据全为虚构
```

## 快速开始

```bash
python3 scripts/selfcheck          # 自检，exit 0 即通过
# 最小链路（在 examples/ 下）：
python3 ../scripts/index_sources.py --sources sources --out /tmp/spans.json
python3 ../scripts/audit_claims.py --claims claims.jsonl --spans /tmp/spans.json --out /tmp/audit.json
python3 ../scripts/build_matrix.py --claims claims.jsonl --spans /tmp/spans.json --audit /tmp/audit.json --out-dir /tmp/products
```

## 限制

- 机器只保证**字面回链**与强度措辞边界；论断与证据的语义匹配是模型职责
  （见 SKILL.md 自查方法，须写入 result.json.checks）。
- 脚本仅 Python 3 标准库；退出码 0=通过 / 2=输入不足 / 3=校验失败。
- 材料变更后必须重建索引并重审（span 按行号定位）。
