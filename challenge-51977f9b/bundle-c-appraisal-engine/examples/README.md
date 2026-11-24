# 合成示例说明（examples/）

> **本目录全部数据为合成示例 / synthetic, illustrative。** 6 篇研究文本
> （input/sources/S1.txt～S6.txt）、判定、论断均为虚构，非真实文献，
> 不得作为真实案例结果引用。

## 布局

- `input/case.json`、`input/task.md`：合成问题"正念干预对医护人员职业
  倦怠的效果——随机对照试验的系统综述"。
- `input/included.json`：6 篇合成研究 id 清单（S1–S6）。
- `input/sources/`：每篇 15–25 行虚构全文文本，含随机化、分配隐藏、
  盲法、失访、选择性报告相关描述。
- `rubric.json`：mini-RoB2-lite 5 维量表（随机序列、分配隐藏、结局测量
  盲法、不完整结局数据、选择性报告；每维 3 级 low/some/high =
  1.0/0.5/0.0，权重各 0.2）。
- `appraisals.jsonl`：6×5 = 30 条判定，每条 basis_quote verbatim 取自
  对应源文本。
- `claims.jsonl`：3 条合成论断。
- `negative/`：埋雷负例（缺 basis_quote 的判定、quote 不在源文本的
  判定、权重和 0.9 的 rubric）。

## 运行命令与预期 exit 码

```bash
S=../scripts
# 1. 量表校验 → exit 0
python3 $S/rubric_check.py --rubric rubric.json
# 2. 确定性评分 → exit 0
python3 $S/appraise.py --rubric rubric.json --appraisals appraisals.jsonl \
  --sources input/sources --included input/included.json --out /tmp/appraisal_report.json
# 3. 敏感性分析 → exit 0（C1 stable / C2 weakened / C3 unsupported）
python3 $S/sensitivity.py --appraisal /tmp/appraisal_report.json \
  --claims claims.jsonl --out /tmp/sensitivity_report.json
# 负例
python3 $S/rubric_check.py --rubric negative/rubric_bad_weight.json   # exit 3（R1）
python3 $S/appraise.py --rubric rubric.json --appraisals negative/appraisal_no_basis.jsonl \
  --sources input/sources --included input/included.json --out /tmp/n1.json  # exit 3（A2）
python3 $S/appraise.py --rubric rubric.json --appraisals negative/appraisal_bad_quote.jsonl \
  --sources input/sources --included input/included.json --out /tmp/n2.json  # exit 3
python3 $S/appraise.py --rubric rubric.json --appraisals appraisals.jsonl \
  --sources /nonexistent --included input/included.json --out /tmp/n3.json   # exit 2
```

## 手算评分过程（与脚本输出对照，3 位小数）

评分公式：`total = Σ weight × (level.score / 维度满分)`，满分 = 1.0，
权重各 0.2。等级：low [0.8,1.0]；some_concerns [0.4,0.8)；high [0.0,0.4)。

| 研究 | rand_seq | alloc_conceal | blind_outcome | incomplete_data | selective_report | 手算 total | grade |
|---|---|---|---|---|---|---|---|
| S1 | low 1.0 | low 1.0 | low 1.0 | low 1.0 | low 1.0 | 0.2×(1+1+1+1+1)=**1.000** | low |
| S2 | low 1.0 | low 1.0 | low 1.0 | some 0.5 | low 1.0 | 0.2×(1+1+1+0.5+1)=**0.900** | low |
| S3 | low 1.0 | some 0.5 | low 1.0 | some 0.5 | low 1.0 | 0.2×(1+0.5+1+0.5+1)=**0.800** | low |
| S4 | low 1.0 | some 0.5 | low 1.0 | some 0.5 | some 0.5 | 0.2×(1+0.5+1+0.5+0.5)=**0.700** | some_concerns |
| S5 | high 0.0 | some 0.5 | high 0.0 | some 0.5 | some 0.5 | 0.2×(0+0.5+0+0.5+0.5)=**0.300** | high |
| S6 | high 0.0 | high 0.0 | some 0.5 | high 0.0 | some 0.5 | 0.2×(0+0+0.5+0+0.5)=**0.200** | high |

selfcheck 断言脚本草算总分与上表手算值在 3 位小数下一致。

## 敏感性示例设计

剔除 grade=high（S5、S6）后（min_support=1）：

| claim | supporting | 剔除后剩余 | 预期判定 |
|---|---|---|---|
| C1 情感衰竭获益 | S1,S2,S3,S4 | S1,S2,S3,S4（支撑集不变） | stable |
| C2 去人格化改善 | S1,S3,S5 | S1,S3（失去 S5，仍 ≥1） | weakened |
| C3 内科常规推广 | S5,S6 | 无（支撑清零） | unsupported → 必须改写或移入 uncertainty |
