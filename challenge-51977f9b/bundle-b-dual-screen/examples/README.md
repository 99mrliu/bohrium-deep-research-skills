# examples — 合成示例（synthetic, illustrative）

**本目录全部数据均为虚构合成示例，仅用于演示 slr-dual-screen 技能流程与
自检，不代表真实文献，不得冒充正式案例结果。**

研究问题（虚构）：远程康复对脑卒中后上肢功能的效果（RCT 系统综述）。

## 文件清单

| 文件 | 说明 |
|------|------|
| input/case.json、input/task.md | 合成案例输入（含 output_contract） |
| input/records.json | 12 条合成题录（R01–R12） |
| input/criteria.json | 排除条款代码表 v1.0（EX-POP/EX-DESIGN/EX-OUTCOME/EX-TIME/EX-LANG/EX-FULLTEXT） |
| decisions_round1.jsonl | 题录级双筛：A、B 各 12 条，埋 2 处分歧（R05、R09） |
| records_round2.json | round 1 仲裁后的 5 条存活记录（R01/R02/R03/R06/R08） |
| decisions_round2.jsonl | 全文级双筛：A、B 各 5 条，埋 1 处分歧（R08） |
| adjudication.jsonl | 3 条仲裁：R05（uncertain→exclude）、R09（exclude）、R08（include） |
| negative/no_reason.jsonl | 埋雷：R04/B 的 exclude 缺 reason_code/reason_text（S3） |
| negative/post_freeze_decision.jsonl | 埋雷：冻结后追加决策（S5） |
| expected_output/ | selfcheck 真实运行生成的产物（骨架、两轮 kappa 报告、frozen_set） |

## 运行命令与预期 exit 码

```bash
S=../scripts
# 1) 解析 + 骨架            → exit 0
python3 $S/parse_case.py --case input/case.json --task input/task.md --out /tmp/case_summary.json
python3 $S/scaffold_result.py --case-summary /tmp/case_summary.json --out /tmp/result.json

# 2) 两轮决策校验           → exit 0
python3 $S/screen_check.py --records input/records.json --decisions decisions_round1.jsonl --round 1 --criteria input/criteria.json
python3 $S/screen_check.py --records records_round2.json --decisions decisions_round2.jsonl --round 2 --criteria input/criteria.json

# 3) 两轮 kappa             → 均 exit 0（round2 kappa<0.6 但未 enforce）
python3 $S/kappa.py --decisions decisions_round1.jsonl --round 1 --out /tmp/rep1.json
python3 $S/kappa.py --decisions decisions_round2.jsonl --round 2 --out /tmp/rep2.json

# 4) 仲裁 + 冻结 + 验证     → exit 0
python3 $S/adjudicate.py --disagreements /tmp/rep1.json /tmp/rep2.json \
  --rulings adjudication.jsonl \
  --decisions decisions_round1.jsonl decisions_round2.jsonl --out /tmp/frozen_set.json
python3 $S/adjudicate.py --verify /tmp/frozen_set.json --rulings adjudication.jsonl \
  --decisions decisions_round1.jsonl decisions_round2.jsonl

# 负例                      → 括号内为预期 exit 码
python3 $S/screen_check.py --records input/records.json --decisions negative/no_reason.jsonl --round 1 --criteria input/criteria.json   # (3, S3)
python3 $S/screen_check.py --records input/records.json --decisions negative/post_freeze_decision.jsonl --round 1 --freeze-file /tmp/frozen_set.json  # (3, S5)
python3 $S/screen_check.py --records /nonexistent.json --decisions decisions_round1.jsonl --round 1   # (2)
python3 $S/kappa.py --decisions decisions_round2.jsonl --round 2 --enforce   # (3, K3)
```

一键自检（含全部正负例断言与手算 kappa 比对）：

```bash
python3 ../scripts/selfcheck    # 预期 exit 0
```

## 手算 kappa 过程（selfcheck 断言的基准值）

### round 1（N=12，二分类 include vs 非 include）

A 判 include：R01 R02 R03 R05 R06 R08（6 条）；B 判 include：R01 R02 R03 R06
R08 R09（6 条）。分歧：R05（A=include / B=uncertain）、R09（A=exclude /
B=include），一致 10 条。

- po = 10/12 = 0.8333
- pe = (6/12)(6/12) + (6/12)(6/12) = 0.25 + 0.25 = 0.5000
- kappa = (0.8333 − 0.5000) / (1 − 0.5000) = **0.667**（≥ 0.6，达标）

### round 2（N=5）

A 判 include：R01 R02 R03 R08（4 条）；B 判 include：R01 R02 R03（3 条）。
分歧：R08（A=include / B=exclude），一致 4 条。

- po = 4/5 = 0.8000
- pe = (4/5)(3/5) + (1/5)(2/5) = 12/25 + 2/25 = 0.5600
- kappa = (0.8000 − 0.5600) / (1 − 0.5600) = 0.24/0.44 = **0.545**（< 0.6）

round 2 是患病率悖论的活例：N 小、纳入率高使 pe 被推高，po=0.80 仍有低
kappa。报告会写 `requires_extended_adjudication=true`，处置见
references/kappa_guide.md；本示例继续走仲裁（R08 经仲裁纳入）。

### 仲裁与最终纳入集

- R05（round1）：B 的 uncertain 经仲裁转 exclude（EX-DESIGN，单臂队列）；
- R09（round1）：维持 A 的 exclude（EX-OUTCOME，下肢结局）；
- R08（round2）：仲裁 include（次要结局含 FMA-UE 且数据可提取）。

最终冻结纳入集 = 共识纳入 R01/R02/R03 + 仲裁纳入 R08 = **[R01, R02, R03, R08]**。
