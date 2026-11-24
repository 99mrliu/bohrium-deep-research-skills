---
name: gatekeeper-independent-audit
description: >-
  科研数据清洗的独立审计门：审计与清洗分离，不过门不交付。当案例要求
  "过程可按记录复跑并逐字段核对""报告数字与结果表一致"时使用。审计器
  不读清洗代码、不信操作者自述，只做机械复核：输入冻结校验、原始↔清洗
  行列对账、按键对齐的静默改动侦测、丢弃行台账核查、单位换算逆运算抽查、
  质量报告数字重算比对、工单覆盖矩阵。任一失败即拒绝交付。
---

# gatekeeper：先清洗、后审计、不过门不交付

## 重心

清洗质量的最大风险不是算错，而是**错了没人查**：静默丢行、手改数字、台账
缺条、工单漏项。本技能把"清洗"与"验收"强制分离——Agent 按工单清洗
（工具自选），`audit_run.py` 作为独立审计员对产物做七项机械复核，
**任何一项 FAIL 都禁止交付**，必须修复后重新过门。


脚本路径说明：技能默认安装在 `/skills/weekly-skill`，下文以 `$SK` 代指该目录；
若不在该路径，用 `find / -maxdepth 6 -name 'scripts' -path '*skill*' 2>/dev/null` 定位技能根。
所有脚本均为 Python 3 标准库、确定性、只读输入文件。

## 流程

### 0. 读案、冻结输入、保底 result.json

```bash
ls -laR /input; cat /input/case.json; cat task.md
mkdir -p /app/work /app/output
python3 $SK/scripts/snapshot_freeze.py /input/<全部原始材料> --out /app/work/frozen
```

立即写 `/app/output/result.json` 占位（case_id + output_contract 全字段 +
`"status":"in_progress"`），每阶段增量刷新。

### 1. 清洗（Agent 职责）

按数据字典、单位/QC 规则与工单清洗，硬性要求只有三条（审计依赖）：

1. 台账列为 `row,field,action,old,new,rule,source`；**每一个被改动的格子
   都必须有一条台账**（old=原值、new=新值）；
2. 单位换算的 rule 必须带倍率标注 `A->B (xF)`；
3. 去重丢弃的每行必须有 `dedup_drop` 台账（old 列存整行 JSON）。
铁律：绝不插补缺失/非法源值；不静默删行改格。

### 2. 工单证据映射

对照工单逐条编号，写 `/app/work/evidence_map.json`：
`{"1": ["cleaned.csv"], "2": ["ledger.csv"], ...}`——每条目至少一个真实
存在的证据文件。写不出证据的条目就是漏项，回去补做。

### 3. 审计过门

```bash
python3 $SK/scripts/audit_run.py --raw <原始表> --cleaned /app/work/cleaned.csv \
    --ledger /app/work/ledger.csv --key <主键列，逗号分隔> \
    --manifest /app/work/frozen/manifest.json \
    --report /app/output/report/quality_report.json \
    --workorder <工单> --evidence-map /app/work/evidence_map.json \
    --evidence-root /app/output --out /app/work/audit
```

退出码 5 ⇒ 读 `audit_verdict.md/json` 的差距清单，**修产物不修审计**，
全部修好后重跑审计。检查项语义见 `references/audit_checks.md`。

### 4. 交付

/app/output：result.json（status 如实）、cleaned.csv、ledger.csv、
质量报告、`audit_verdict.json/md`（过门证据）、evidence_map.json。
status=partial 必须配 limitations。

## 异常处理

- 键无法确定 → 审计降级（`--skip C,D`），在 verdict 与 result.json 如实标注；
- 原始文件被冻结核验发现改动 → 立即停止，以冻结副本为准恢复并说明；
- 时间不足 → 保 result.json 合法 + 已完成的审计项结果，降级 partial。

## 最小示例

`examples/`：合成原始/清洗表/台账/工单/证据映射 + 一次 PASS 与一次 FAIL
（人为制造的静默改动被检查 C 抓获）的真实运行记录，见 `examples/README.md`。
