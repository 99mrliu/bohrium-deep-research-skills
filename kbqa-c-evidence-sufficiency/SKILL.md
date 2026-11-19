---
name: kbqa-evidence-sufficiency
description: 科研知识库问答的"证据充分性判定 + 分级拒答"工作流——为每个问题建立"问题×来源"覆盖矩阵，按明确判据把答案分成五级（SUPPORTED/PARTIAL/CONFLICTED/UNSUPPORTED/INACCESSIBLE），只有 SUPPORTED 的论断才写进答案；证据冲突并列双方坐标不擅自取舍；无依据的问题必须明确说"没有"并逐条说明缺什么（缺哪类文件、哪个版本、哪个字段）。判定与裁决全程由确定性脚本执行并留痕，模型的职责只是选段与措辞。Use when a task requires honest, graded answers over a scientific document library with explicit handling of missing/conflicting/inaccessible evidence (不确定性提示, 缺证判据, 证据冲突, 分级拒答, 覆盖矩阵, /input/case.json, result.json).
---

# 证据充分性判定与分级拒答（kbqa-evidence-sufficiency）

## 何时使用

平台给出 `/input/case.json` + `/input/task.md`，其中包含一个科研资料库与若干问题；交付要求对证据不足、证据冲突、文件不可读等情况**分级提示**，答案中的每个论断都能落到具体文件与坐标，且对库中确实没有依据的问题敢于说"没有"。结果写入 `/app/output`，`result.json` 必须含 `case_id`、`output_contract` 全部字段，以及诚实的 `status` / `sources` / `uncertainty` / `change_log`。

本 Skill 的增益在认识侧：它不把"检索到几段相似文本"当作"有依据"，而是把判定交给显式规则——覆盖矩阵给出量，判据表给出级，冲突登记表给出并列证据，最终每题得到一个可复核的裁决。

## 运行方式（五步）

```bash
SKILL=/skills/weekly-skill

# 1) 索引：哈希 + 文本抽取 + 可读性（先落 partial result.json 检查点）
python3 $SKILL/scripts/suff_index.py --input /input --work /app/work --out /app/output

# 2) 从 case.json 提取问题列表到 /app/work/questions.json（模型完成，
#    结构见 resources/grading_rubric.md 附录），然后建覆盖矩阵：
python3 $SKILL/scripts/suff_matrix.py --work /app/work --out /app/output

# 3) 冲突登记：从矩阵摘取中提取"键:值"事实候选，跨来源比对：
python3 $SKILL/scripts/suff_conflict.py --work /app/work --out /app/output

# 4) 作答：模型按矩阵与冲突登记表撰写 /app/work/answers.json；
#    每题一个裁决（五级之一），SUPPORTED 论断必须带逐字引文与坐标。

# 5) 裁决校验 + 收尾：脚本校验每题裁决与证据的一致性，组装 result.json
python3 $SKILL/scripts/suff_verdict.py --case /input/case.json --work /app/work --out /app/output
```

## 五级判据（摘要，全表见 resources/grading_rubric.md）

| 级 | 判据 | 答案写法 |
|-|-|-|
| SUPPORTED | 逐字引文在当前可读来源中机器核验通过，且无未决冲突 | 正常作答，论断后接坐标引文 |
| PARTIAL | 有引文但仅覆盖部分子论断，或仅历史版本/间接表述 | 作答 + 限定语，`uncertainty` 说明覆盖缺口 |
| CONFLICTED | 两个及以上来源对同一事实给出不同值 | 并列双方引文与坐标，不裁决，说明分歧点 |
| UNSUPPORTED | 零命中或仅有模板式命中 | 明确写"库中无依据"，`missing` 逐条说明缺什么 |
| INACCESSIBLE | 证据疑似存在于不可读/无权限文件 | 写明文件名与所需权限/工具，不引用其内容 |

判级由 `suff_verdict.py` 机械校验：模型在 answers.json 中声明的裁决若与矩阵/冲突/核验结果矛盾（如零命中却报 SUPPORTED），脚本会降级并在 `change_log` 记录——模型不能用措辞绕过判据。

## 硬规则

1. 每个写进答案的论断都要逐字引文 + 坐标 `[Dxx|sha8|L起-L止]`；引文核验方式与 bundle 无关的本 Skill 脚本一致（空白去除后子串比对）。
2. 无依据的问题写"库中无依据"，且 `missing` 必须具体：缺哪类文件（如原始实验记录）、哪个版本（如 2023 修订版）、哪个字段（如样本量）。"不确定"不是可接受的 missing 描述。
3. 冲突双方都给坐标；除非行政备注/任务说明给出权威版本，否则不取舍。
4. 每完成一题更新一次 `result.json`（partial 检查点纪律）；预算约 64 次请求、900 秒，过半立即收尾。
5. 库目录为空 → 全部问题 UNSUPPORTED + INACCESSIBLE 混合说明，status=partial。

## 自查清单

1. 每题裁决与矩阵/冲突登记一致？脚本无降级记录？
2. SUPPORTED 论断引文全部机器核验通过？
3. UNSUPPORTED 的 missing 是否具体到文件类/版本/字段？
4. CONFLICTED 是否并列了双方坐标？
5. result.json 契约字段齐全、status 诚实？

最小调用示例见 [examples/minimal_example.md](examples/minimal_example.md)（虚构示意，非正式案例结果）。
