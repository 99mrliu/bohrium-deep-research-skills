# slr-corpus-verity — 题录真实性核验与语料治理

系统性文献综述（challenge-51977f9b）Skill bundle。**签名能力：在筛选之前建立
"可信语料层"**——凡进入筛选的每条题录都必须通过元数据核验；伪造嫌疑、重复、
撤稿记录进入隔离区并给出机器可复核的理由，直接喂给 PRISMA 流程的
duplicates_removed 与排除理由。

## 布局

```
SKILL.md            # 本体（frontmatter + 8 节必备结构）
README.md           # 本文件
scripts/
  parse_case.py     # 防御式案例解析 → case_summary.json
  scaffold_result.py# result.json 保底骨架（status=draft）
  verify_corpus.py  # 签名引擎：V1–V8 题录核验 → corpus_report.json
  selfcheck         # 自检（python3 直接运行，38 项断言）
references/
  record_schema.md      # 题录字段定义与规范化规则
  duplicate_policy.md   # 重复判定哲学、阈值 0.92 依据、误杀处置
  online_verification.md# Crossref 在线核查与离线降级语义
examples/           # 全部合成示例（synthetic, illustrative）
  input/            # case.json / task.md / records.json（10 条埋雷题录）
  negative/         # 损坏 JSON 负例
  output/           # 脚本真实运行产物
  expected_states.json
```

## 快速开始

```bash
python3 scripts/selfcheck          # 一键自检，预期 exit 0
# 或对任意案例：
python3 scripts/parse_case.py --case /input/case.json --task /input/task.md \
  --out /app/work/case_summary.json
python3 scripts/scaffold_result.py --summary /app/work/case_summary.json \
  --out /app/output/result.json
python3 scripts/verify_corpus.py --records /input/records.json \
  --out /app/work/corpus_report.json          # 可加 --strict / --online
```

## 退出码约定

0=通过；2=输入/材料不足（诚实降级，仍交付协议或最小报告）；3=校验失败
（--strict 下发现 invalid/suspicious/retraction_flagged，或输出不可写）。

## 限制

- 仅 Python 3 标准库；在线核查（--online）依赖外网，离线自动降级为
  "本地一致性核验"，绝不把"查不到"当伪造证据。
- V5 近似重复阈值为经验值（0.92），短题名与同系列研究有误杀风险，
  probable_duplicate 必须人工复核（见 references/duplicate_policy.md）。
- DOI 合法 ≠ 真实：DOI 语法合法但内容伪造的记录只能标 suspicious，
  不能断言伪造。
- examples/ 全部为合成数据，不对应任何真实文献。
