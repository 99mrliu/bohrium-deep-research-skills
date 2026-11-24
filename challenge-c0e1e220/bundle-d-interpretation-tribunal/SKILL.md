---
name: interpretation-tribunal
description: >-
  统计分析与结果解读 Skill（Bohrium Playground challenge-c0e1e220，Bundle D）。
  当任务要求对 /input 中的 CSV/SQLite 数据做统计推断并产出规范的结果解释时触发：
  一键完成清洗、假设门控检验、效应量与置信区间，并把「统计显著≠实际意义、
  p 值不能写成证明、CI 不是个体取值范围」做成机器可检的措辞 lint
  （wording_lint.py），让报告每句结论携带可解析的证据标签 [ev:Hk] 并与
  result.json.claims 逐字绑定（claim_bind.py）。不做：图形渲染、
  领域意义上的重要性裁决（Δ 未给出时只给效应量量级并声明局限）、因果推断。
---

# interpretation-tribunal — 结果解释措辞纪律与结论-证据绑定

## 何时使用 / 边界

适用：
- 输入为 `/input/case.json` + `/input/task.md` + 数据文件（CSV 有/无表头、SQLite .db，
  数值可能以 TEXT 存储）的统计比较任务（两组或 k 组均值/分布比较）。
- 需要交付 `/app/output/result.json`（9 个契约字段）+ 规范中文报告的场景。

不适用 / 边界：
- 回归建模、生存分析、多重插补、贝叶斯推断（超出本 Skill 的检验菜单）。
- 图表渲染（本 bundle 只产出文本交付物）。
- 领域实际重要性裁决：task 未给最小实际重要差异 Δ 时，只报告效应量量级并声明局限。
- 观察性数据的因果结论（本 Skill 在措辞层面禁止因果动词）。

## 运行契约

- 输入：`/input/case.json`、`/input/task.md`、数据文件（CSV + SQLite）。
- 中间产物：`/app/work`（run_config.json、decisions.json、digest.md）。
- 交付：`/app/output/result.json` + `report.md` + `digest.md`。
- `result.json` 必须含 `case_id` 与 `output_contract.required_fields` 全部字段
  （case_id, status, cleaning, descriptive, hypothesis_test, effect_size,
  confidence_interval, interpretation, limitations），并附加 `claims`
  （结论-证据绑定数组）、`sources`（每个输入文件 sha256）、`reproducibility`
  （seed/python/platform/utc）、`uncertainty`、`exceptions`、`decisions`。
- 诚实 partial：任何失败或部分完成都写入 `status`（complete/partial/failed）
  与 `exceptions`，绝不静默；partial 时报告必须含不确定性说明段
  （wording_lint 的 UNHEDGED_PARTIAL 强制）。
- 不得预制答案：所有数值由脚本从原始数据真实计算；报告句由 claims 渲染，
  逐字一致由 claim_bind 强制。

## 精确命令工作流

```bash
# 0. 定向（1 次模型请求内完成阅读）
cat /input/case.json /input/task.md; ls -la /input

# 探测 SKILL 安装目录
SKILL_DIR=/skills/weekly-skill
[ -f "$SKILL_DIR/scripts/pipeline_d.py" ] || \
  SKILL_DIR=$(dirname "$(grep -rl 'name: interpretation-tribunal' /skills --include=SKILL.md 2>/dev/null | head -1)")
echo "$SKILL_DIR"

# 1. 一键 baseline 全流程（0 模型请求）
#    按 task.md 指定结果变量/分组变量/分组水平/单位（启发式默认值见 digest）
python3 $SKILL_DIR/scripts/pipeline_d.py run --input /input --work /app/work --output /app/output \
  --outcome <结果变量列名> --group <分组变量列名>            # 如：--outcome c2 --group c4
#  分组水平很多时限定子集，如混凝土 28 天 vs 90 天： --group age --levels 28,90

# 2. 重心深度审计（0 模型请求；机器可检核心）
python3 $SKILL_DIR/scripts/wording_lint.py --file /app/output/report.md --result /app/output/result.json
python3 $SKILL_DIR/scripts/claim_bind.py  --report /app/output/report.md --result /app/output/result.json

# 3. 读 digest，确认/覆盖 ≤5 项裁决（1 次模型请求）
cat /app/work/digest.md
python3 $SKILL_DIR/scripts/pipeline_d.py decide --work /app/work \
  --set outcome=<列名> --set group=<列名> --set levels=<a,b> --set unit=<单位>   # 仅改需要改的

# 4. finalize 重写交付物（自动重跑 wording_lint + claim_bind，全过才 exit 0）
python3 $SKILL_DIR/scripts/pipeline_d.py finalize --input /input --work /app/work --output /app/output

# 5. 交付前自查（全部 exit 0 才可交付）
python3 -m json.tool /app/output/result.json >/dev/null && echo "result.json 合法"
python3 - <<'EOF'
import json
r = json.load(open("/app/output/result.json", encoding="utf-8"))
req = ["case_id", "status", "cleaning", "descriptive", "hypothesis_test",
       "effect_size", "confidence_interval", "interpretation", "limitations"]
assert all(k in r for k in req), "契约字段缺失"
assert r["claims"], "claims 为空"
print("9 字段齐全，status=%s，claims=%d" % (r["status"], len(r["claims"])))
EOF
```

## 方法决策规则（硬性）

| 情形 | 处置 |
|---|---|
| 两组，各组正态（D'Agostino K²，n≥8 才做）且 Levene(median) 齐性 | Student t |
| 两组，正态但方差不齐 | Welch t |
| 两组，非正态或 n<8 | Mann-Whitney U（tie 校正），另报 Welch t 敏感性 |
| k 组，全正态且齐性 | 单因素 ANOVA |
| k 组，正态不齐 | Welch ANOVA，另报经典 ANOVA 敏感性 |
| k 组，非正态 | Kruskal-Wallis（tie 校正），事后 Mann-Whitney |
| 事后两两比较 | 与主检验同路线，Holm 校正；claim.p 存调整后 p |
| 效应量 | 两组 Hedges g（bootstrap B=2000, seed=20240501）；k 组 ω²（KW 路线 ε²） |
| CI | 参数路线均值差 Welch CI；非参路线 Hodges-Lehmann 中位数差 + bootstrap CI |
| 措辞 | 见 references/wording-rules.md：p 必须落在「在 α=… 水平下…」句式；禁用证明/证实/导致/引起等 |
| CI 含义 | 必须出现「并非个体取值的范围」句（CI_MISREAD 防线） |
| 显著结论 | 同段必须有独立实际意义句（效应量数值或 Δ 讨论，MISSING_PRACTICAL 强制） |
| 结论句 | 必须以 [ev:Hk] 结尾且与 claims 逐字一致（claim_bind 强制） |

## 预算表（64 请求上限内，典型 ≤8）

| 步骤 | 模型请求 |
|---|---|
| 0 定向 + 读 task 选列 | 1 |
| 1–2 跑脚本（baseline + 两项 lint） | 1 |
| 3 读 digest + decide | 1 |
| 4 finalize | 1 |
| 5 自查 + 交付陈述 | 1 |
| 余量（异常重试、措辞微调） | 3 |
| 合计 | ≤8 |

## 异常处理表

| 异常 | 识别 | 处置 |
|---|---|---|
| 样本量不足 | 有效 n<8 | status=partial；正态性保守按非正态；局限注明效能不足 |
| 组内方差为零 | Levene/t 退化 | 走秩检验路线；exceptions 记录 |
| 缺失比例过高 | 缺失排除 >50% | status=partial；局限注明代表性风险 |
| 假设不成立 | K² p<α 或 Levene p<α | 门控自动切换到稳健路线 + 敏感性对照 |
| 单位不明 | task.md 无单位 | unit=未注明；句子不带单位；局限注明口径以原始数据为准 |
| SQLite 连接失败/无用户表 | 异常捕获 | 以 CSV 为主源继续；exceptions 记录；行数不一致写 uncertainty |
| CSV 无表头 | 类型签名嗅探 | 列名 c0..cn（与 db 列名一致）；digest 提示人工核对 |
| 分组水平过多 | >10 个水平 | digest 警示，建议 --levels 限定子集 |
| pipeline 崩溃 | 异常捕获 | 写出 status=failed 的 result.json 骨架，exit 2 |

## 文件清单

```
SKILL.md                      本文件
GITHUB_URL.txt                GitHub 树 URL + SKILL.md
README.md                     用途与维护信息
scripts/statcore_d.py         stdlib 统计核心（分布函数/检验/效应量/CI/Holm）
scripts/pipeline_d.py         一键 baseline：run / decide / finalize
scripts/wording_lint.py       措辞纪律 lint（BANNED_PHRASE/P_WORDING/CI_MISREAD/
                              MISSING_PRACTICAL/UNHEDGED_PARTIAL）
scripts/claim_bind.py         结论-证据绑定核验（DANGLING_EVIDENCE/
                              DIRECTION_MISMATCH/SIGNIFICANCE_MISMATCH/
                              NUMBER_MISMATCH/SENTENCE_DRIFT）
references/wording-rules.md   句式模板与禁用语表及出处理由
references/ci-interpretation.md  CI 正确含义与典型误读
references/significance-vs-importance.md  统计显著 vs 实际意义
references/claim-evidence-binding.md      绑定协议与精度约定
examples/make_synthetic.py    合成示例数据生成器（大样本小差异场景）
examples/run_example.sh       端到端自校验（好例 + 5 组埋雷）
examples/minimal-example.md   最小示例说明（合成示例）
examples/example_output/      真实跑出的文本产物（json/md/csv）
```
