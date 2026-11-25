---
name: evidence-provenance-translation
description: >-
  当科研翻译案例的评分关注"可核验性"——每段译文能否指回原文具体段落与句子、译法依据是否留痕、译不准处是否明确标注而非含混处理——时使用本 Skill。
  Use when a scientific-translation case (/input/case.json + task.md + source) requires evidence-anchored delivery: every translated segment records a source quote plus its exact offset (machine-verified against the actual source, tamper-evident), a translation-basis label (literal / termbase / convention / uncertain) with a concrete note, an uncertainty register that derives an honest status (success only when all segments are translated and all evidence verifies; partial otherwise), explicit 未报告/无法判断 marking instead of silent guessing, and a verification report with a human-review checklist mapping each claim back to source evidence. Contract-driven result.json carries case_id and every output_contract field.
  不做的事：不给无证据的译文背书、不把无法判断写成事实、不伪造页码或引文、不用"大意如此"替代逐段指回。
---

# evidence-provenance-translation（证据锚定与不确定性诚实标注，Bundle E）

本 Skill 的重心是**可核验性**：译文的价值取决于能否逐段回到原文证据。脚本对每段
记录的原文引文与偏移做机器核验（引用必须与实际源文本一致），统计源文覆盖缺口
（潜在漏译区），并把不确定性登记为独立工件推导诚实状态。翻译由 Agent 完成；
脚本确保证据真实、缺口可见、状态诚实。

## 何时使用 / 边界

**适用**：评分关注"每段可指回原文、译法有据、不确定项明确"的案例；交付物需被
第三方复核的场景。**不适用**：无源文本可比对的摘要式任务；核验只能证明"引文与
源文本一致 + 覆盖无缺口"，不证明语义正确（语义仍由 Bundle C 类核验或人工复核承担）。

## 运行契约

- 输入：`/input/case.json` + `/input/task.md` + 源文件。
- 中间产物（`/app/work/evjob/`）：`source.md`、`translations.json`、`evidence_map.json`、`uncertainty_register.json`。
- 交付（`/app/output/`）：`result.json`（`case_id` + 合同全部必填字段）、`bilingual.md`、`verification_report.md`、`evidence_map.json`。
- 诚实状态：`success` 要求全部段已译、全部证据核验通过、覆盖无缺口；否则 `partial`；
  无法判断的条目写入 `uncertainties`，绝不写成事实。

## 精确命令工作流

```bash
# 0. 定向
cat /input/case.json /input/task.md; ls -la /input
export SKILL_DIR=$(dirname $(find /skills -maxdepth 3 -name SKILL.md -path '*evidence-provenance*' 2>/dev/null | head -1))
S=$SKILL_DIR/scripts; W=/app/work/evjob; O=/app/output; mkdir -p $W $O

# 1. 源文
python3 $S/extract_source.py --input /input --out $W/source.md

# 2. Agent 逐段翻译并在每段记录证据与译法依据（见下"证据记录格式"）

# 3. 机器核验证据 + 覆盖缺口
python3 $S/anchor_evidence.py --source $W/source.md --translations $W/translations.json \
    --out $W/evidence_map.json
#    verdict: verified / offset_mismatch / quote_not_found / overlapping / gap_report

# 4. 不确定性登记 + 诚实状态推导
python3 $S/uncertainty_register.py --translations $W/translations.json \
    --evidence $W/evidence_map.json --out $W/uncertainty_register.json

# 5. 验证报告 + 合同组装
python3 $S/verification_report.py --translations $W/translations.json \
    --evidence $W/evidence_map.json --register $W/uncertainty_register.json \
    --out $O/verification_report.md
python3 $S/assemble_result.py --case /input/case.json --translations $W/translations.json \
    --evidence $W/evidence_map.json --register $W/uncertainty_register.json --out $O
```

## 证据记录格式（translations.json 每段必填）

```json
{"id": "p003",
 "source": "<原文段>",
 "translation": "<译文>",
 "evidence": {"quote": "<原文段的精确子串（逐字）>", "start": 1234,
              "basis": "literal | termbase | convention | uncertain",
              "note": "译法依据：为何这样译（术语表第几条/惯例/存疑点）"},
 "uncertainty": null}
```

- `quote` 必须逐字来自源文本；`start` 为源文本字符偏移（脚本核验二者一致）。
- `basis=uncertain` 或 `uncertainty` 非空 → 进人工确认清单，状态至多 `partial`。
- 无法辨认的符号/词汇：quote 原样保留（含 �），`uncertainty.type="unreadable"`，
  写明位置与尝试过的判读，不得猜译。

## 最小调用示例（合成示例，非正式案例结果）

`examples/source_en.txt` 为**合成的**机器学习论文摘录（含一处刻意含糊的缩写与一处
不可读符号）。`run_example.sh` 跑通 翻译（合成译文，含刻意错引与存疑标注）→证据核验
（必须检出错引与覆盖缺口）→ 修正后全绿 → 报告与组装，并断言 `result.json` 合同字段
齐全、状态推导诚实。示意输出见 `examples/example_output/`。

## 预算、可靠性与限制

- 官方包线 64 请求 / 900 秒：核验为脚本零请求；Agent 工作集中在翻译与证据记录。
- 稳定性：脚本幂等；证据核验不依赖任何模型输出，可独立复跑。
- 异常处理：无文字层源 → 证据层标 `unauditable` 并说明；页码缺失时偏移仍为有效锚点。
- 限制：偏移基于可读文本导出，物理页码需由抽取时另存；覆盖缺口提示"可能漏译"而非
  判定；机器核验不评价译文的语言质量。
