# bundle-c：slr-appraisal-engine

系统性文献综述技能，签名能力是**质量评价方法学引擎**：声明式评价量表
（JSON：维度×等级×权重×分级规则）+ 确定性评分（脚本重算，禁止口头
"质量较高"）+ 结论敏感性分析（剔除高风险研究后重算论断支撑，
stable/weakened/unsupported）。其余综述链环节以 references 协议 +
result.json 字段承载，见 SKILL.md。

## 布局

- `SKILL.md`：技能本体（含完整工作流程与输出合同映射）。
- `scripts/`：
  - `parse_case.py`：case.json+task.md → case_summary.json；
  - `scaffold_result.py`：result.json 保底骨架
    （skill_name=slr-appraisal-engine）；
  - `rubric_check.py`：量表校验 R1–R4；
  - `appraise.py`：签名引擎，判定完整性/依据可核（verbatim quote
    子串核验）/确定性评分定级 A1–A3；
  - `sensitivity.py`：剔除指定等级后重算结论支撑 S1–S2，产出 json+md；
  - `selfcheck`：正负例断言 + py_compile，exit 0 为准。
- `references/`：rubric_design.md（按研究类型选/配量表与版本化纪律）、
  grade_rules.md（等级→结论权重映射哲学）、sensitivity_guide.md
  （敏感性判定与改写纪律）。
- `examples/`：**全部合成示例**（synthetic, illustrative）：6 篇虚构
  RCT 文本、5 维 mini-RoB2-lite 量表、30 条判定、3 条论断、3 个埋雷
  负例、手算评分对照。

## 快速开始

```bash
cd examples
python3 ../scripts/rubric_check.py --rubric rubric.json
python3 ../scripts/appraise.py --rubric rubric.json \
  --appraisals appraisals.jsonl --sources input/sources \
  --included input/included.json --out /tmp/appraisal_report.json
python3 ../scripts/sensitivity.py --appraisal /tmp/appraisal_report.json \
  --claims claims.jsonl --out /tmp/sensitivity_report.json
python3 ../scripts/selfcheck   # 全部断言通过 exit 0
```

## 限制

- 纯 Python 3 标准库；脚本不解析 PDF、不联网。
- 逐维度判断由模型完成，脚本负责核验与重算；quote 必须与原文 verbatim
  （规范化空白后子串比对）。
- examples/ 数据全部为合成示例，不得冒充正式案例结果。
