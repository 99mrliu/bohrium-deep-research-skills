---
name: contractdock-deliverable-engineering
description: >-
  科研数据清洗的下游交付工程：output_contract 优先抽取、result.json 脚手架
  先行落地、质量报告数字全部由产物重算生成（附 SVG 预览）、交付前机械验收
  （字段覆盖/类型/产物存在/报告自洽），不过验收不交付。当案例要求按
  output_contract 交付结构化 result.json、清洗表与数据质量报告时使用。
  本技能不规定清洗算法本身，而保证清洗结果被完整、一致、可核验地交付。
---

# contractdock：合同优先的交付工程

## 重心

评分里"结果完整性、可核验性、报告数字与结果表一致"丢分最多：报告靠自然语言
手写、result.json 缺字段、引用的文件不存在。本技能把交付做成机械过程——
**合同先钉死、骨架先落地、数字只重算、交付先验收**。清洗本身按案例工单执行
（本技能不替代清洗判断），但任何清洗结果都必须经这条交付线出门。


脚本路径说明：技能默认安装在 `/skills/weekly-skill`，下文以 `$SK` 代指该目录；
若不在该路径，用 `find / -maxdepth 6 -name 'scripts' -path '*skill*' 2>/dev/null` 定位技能根。
所有脚本均为 Python 3 标准库、确定性、只读输入文件。

## 流程

### 0. 抽取合同 + 落地脚手架（最先做，早于一切数据处理）

```bash
ls -laR /input; cat /input/case.json; cat task.md
mkdir -p /app/work /app/output
python3 $SK/scripts/contract_extract.py --case /input/case.json \
    --out /app/work/contract --scaffold-out /app/output/result.json
```

- 退出码 3 = 未找到 output_contract：仍已产出含 case_id 的骨架，人工从
  task.md 摘录交付要求补进 /app/work/contract/contract.json。
- 从此刻起 `/app/output/result.json` 永远结构合法；每完成一阶段就填入实测值
  并把 `status` 推进（in_progress → success/partial/failed）。

### 1. 清洗（按工单，留逐格台账）

在 /app/work 完成解码、缺失分类、单位换算、去重、异常标记；台账列约定为
`row,field,action,old,new,rule,source`（任何清洗工具均可，只要台账符合此列
约定，报告生成器即可消费）。**绝不插补缺失/非法源值。**

### 2. 报告生成（数字只从产物重算）

```bash
python3 $SK/scripts/report_build.py --cleaned /app/work/cleaned.csv \
    --ledger /app/work/ledger.csv --raw <原始表> --out /app/output/report
```

产出 `quality_report.json/md` + `report_preview.svg`（字段级问题条形图，
可直接打开目检）。把报告路径与关键数字回填进 result.json 对应字段。

### 3. 交付前验收（不过不交付）

```bash
python3 $SK/scripts/contract_verify.py --contract /app/work/contract/contract.json \
    --result /app/output/result.json --output-dir /app/output \
    --report /app/output/report/quality_report.json \
    --cleaned /app/work/cleaned.csv --ledger /app/work/ledger.csv --raw <原始表> \
    --out /app/work/verify
```

退出码 5 = 存在差距：按 `verify_verdict.json` 的清单逐项修复后重验。
验收语义详见 `references/acceptance_semantics.md`。

### 4. 交付

/app/output 至少含：result.json（全字段、status 如实、不确定性说明）、
cleaned.csv、ledger.csv、report/（三件套）、verify_verdict.json。
`status: "partial"` 必须配 `limitations` 说明哪里缺、为什么。

## 异常处理

- case.json 损坏/无合同 → 骨架保底 + 人工摘录合同，result.json 记 partial；
- 清洗中途失败 → 已产出的部分照常生成报告，status=failed 并说明断点；
- 报告自洽核查失败 → 以重算值为准修正报告，**不得**手改数字迁就报告。

## 最小示例

`examples/`：合成 case.json（含嵌套 output_contract）+ 合成原始/清洗表/台账，
三个脚本的真实运行产物见 `examples/expected/`，命令见 `examples/README.md`。
