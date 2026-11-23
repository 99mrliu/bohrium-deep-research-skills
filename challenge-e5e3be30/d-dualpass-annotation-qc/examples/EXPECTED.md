# EXPECTED.md — 合成示例的预期产物与实际运行记录

【合成示例】本文件记录 `run_example.sh` 在本 bundle 交付前的**实际**运行结果
（macOS, Python 3.9+，纯标准库）。paper.txt 为虚构论文；passA.json / passB.json
为手工构造的演示输入，不是真实模型输出。设计意图：

- C1、C4、C5：两通道判定与定位一致（supported / contradicted / insufficient_evidence）；
- C2：判定一致（partially_supported）但**定位分歧**（A→页4，B→页2）；
- C3：**verdict 分歧**（A=supported，B=insufficient_evidence，对"孔结构→性能"因果断言的宽严差异）。

## 1. agreement.py 实际输出（exit 0）

```
[agreement] 论断数 n=5
[agreement] verdict 观测一致率 po=0.8000，期望一致率 pe=0.2400
[agreement] Cohen's kappa = 0.7368
[agreement] 定位：平均 Jaccard=0.7000，至少一页精确重合比例=0.8000
[agreement] verdict 分歧 1 条；仅定位分歧 1 条
  [verdict 分歧] C3: A=supported vs B=insufficient_evidence
  [定位分歧] C2: A页[4] vs B页[2]
```

手算复核：po=4/5=0.8；pe=(2·1+1·1+1·1+1·2)/25=0.24；
kappa=(0.8−0.24)/(1−0.24)=0.7368…。定位：Jaccard = (1.0+0.0+0.5+1.0+1.0)/5=0.70；
至少一页精确重合 = 4/5 = 0.80（C5 双方空页码按"均无证据"计为一致）。
kappa=0.7368 ∈ [0.6, 0.8)，可接受但需报告 needs_review 计数，不触发低质警告。

## 2. adjudicate.py 实际输出（exit 0）

```
[adjudicate] 共 5 条：一致采纳 3，needs_review 2（含 conflict 0）
[adjudicate] 终判分布: {'supported': 1, 'partially_supported': 2, 'contradicted': 1, 'insufficient_evidence': 1}
  [复核] C2 → partially_supported：判定一致但证据页码无重合（location_divergence），页码取并集，建议复核定位
  [复核] C3 → partially_supported：保守默认：分歧对 (supported, insufficient_evidence) 取更不乐观判定 → partially_supported
```

终判：C1=supported；C2=partially_supported（needs_review，页码并集 [2,4]）；
C3=partially_supported（provisional，needs_review，双方原话并列于日志）；
C4=contradicted；C5=insufficient_evidence。
若写入 result.json：status 应为 **partial**（存在 2 条 needs_review），
uncertainty 须含 kappa=0.7368、mean_jaccard=0.70、exact_overlap=0.80、needs_review=2。

## 3. checklist.py 实际输出（exit 0）

```
[checklist] 5 条论断 → out/checklist.csv + out/checklist.md
```

CSV 八列（勾选/claim_id/论断原文/待查槽位/证据位置(页)/判定/复核人/复核日期，
UTF-8 带 BOM）；Markdown 含 5 个 `- [ ]` 勾选项与待填核验记录表。

## 4. 退出码验证记录

| 场景 | 命令 | exit |
|---|---|---|
| 正常流水线 | `bash examples/run_example.sh` | 0 |
| 各脚本帮助 | `python3 scripts/{agreement,adjudicate,checklist}.py --help` | 0 |
| 用法错误（缺参数） | 各脚本无参数运行 | 2 |
| 输入文件不存在 | agreement.py 指向不存在路径 | 1 |
| verdict 非法值 | agreement.py 输入 `"verdict":"bogus"` | 1 |
| 低 kappa 质量警告 | 构造 4 条全分歧输入（kappa=−0.3333） | 0（警告走 stderr） |
| contradicted 冲突特例 | 同上输入，adjudicate.py | 0（conflict=true，双方并列） |

## 5. 产物清单（examples/out/，可随时删除重跑）

```
agreement-report.json   adjudicated.json   adjudication-log.md
checklist.csv           checklist.md
```
