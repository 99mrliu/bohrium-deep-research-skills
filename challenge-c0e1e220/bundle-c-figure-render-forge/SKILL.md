---
name: figure-render-forge
description: >-
  统计分析的下游渲染工程与图表证据锻造。何时触发：需要在 Bohrium Playground 统计任务中
  把假设检验结果变成合规、可机器审计的图表时。做什么：按数据形态选图（分组比较→箱线+抖动散点、
  非参路线→追加 ECDF、两数值变量→散点+OLS、分类计数→频数条形图），双通道渲染（matplotlib PNG /
  纯 Python 确定性 SVG 兜底），图注携带每组 n 与单位，figure_audit 机器核验图文件签名、图注数字一致性、
  选择规则合规与覆盖率。不做什么：不做上游数据真实性跨源审计（那是数据门禁的事），不产出违反
  dynamite plot 禁令的均值条形图。Standalone stdlib pipeline included (run/decide/finalize)。
---

# figure-render-forge — 图表证据锻造与机器审计

## 何时使用 / 边界

**适用**：输入为 CSV/SQLite 数据 + case.json + task.md 的统计分析任务；需要交付 result.json（9 字段）、
报告与**可审计图表**；matplotlib 可能缺失的环境（SVG 兜底）；需要证明图表合规（每组 n、单位、
选择规则、覆盖率）的场合。

**不适用**：纯可视化美化需求（无统计分析）；需要交互式图表（plotly 等）的场景；
数据真实性/跨源伪造甄别（用数据门禁类 skill）；上万组水平的超高维分组（max_figures 截断 + waiver）。

## 运行契约

- 输入：`/input/case.json` + `/input/task.md` + 数据文件（CSV 有/无表头、SQLite 第一个用户表）。
- 中间产物：`/app/work`（analysis_data.json、session.json、digest.md）。
- 交付：`/app/output/result.json`（**必须含 case_id 与 output_contract.required_fields 全部 9 字段**，
  另附 sources/reproducibility/uncertainty/exceptions/decisions/figures）+ `report.md` + `figures.md` + `fig<N>.png|.svg`。
- **诚实 partial**：任何失败/部分完成写入 `status`（ok/partial/failed）与 `exceptions`，绝不静默。
- **不得预制答案**：所有数字必须真实运行脚本产生；示例仅为合成演示。

## 精确命令工作流

```bash
# 0. 定向（1 次模型请求）
cat /input/case.json /input/task.md; ls -la /input
test -d /skills/weekly-skill && SKILL_DIR=/skills/weekly-skill || SKILL_DIR="$(pwd)"

# 1. 一键 baseline 全流程（0 模型请求）：原始数据 → result.json + report.md + work/digest.md
mkdir -p /app/work /app/output
python3 "$SKILL_DIR/scripts/pipeline_c.py" run --input /input --work /app/work --output /app/output

# 2. 重心：规则引擎选图 + 双通道渲染（0 模型请求；matplotlib 缺失时自动 SVG 兜底）
python3 "$SKILL_DIR/scripts/figure_forge.py" --work /app/work --output /app/output
# 机器审计（必须 exit 0 才可交付）
python3 "$SKILL_DIR/scripts/figure_audit.py" --output-dir /app/output --result /app/output/result.json

# 3. 读 digest，确认/覆盖 ≤5 项裁决（1 次模型请求）
cat /app/work/digest.md
# 如需覆盖（示例）：分组变量、结局、焦点水平、alpha、图表 waiver
python3 "$SKILL_DIR/scripts/pipeline_c.py" decide --work /app/work --set group_by=age --set focus=28,90
python3 "$SKILL_DIR/scripts/pipeline_c.py" decide --work /app/work --set figure_waiver.a7=“该结局与任务无关，效应可忽略”

# 4. finalize 重写交付物（0 模型请求；任何 decide 后必须重跑 forge + audit）
python3 "$SKILL_DIR/scripts/pipeline_c.py" finalize --work /app/work --output /app/output
python3 "$SKILL_DIR/scripts/figure_forge.py" --work /app/work --output /app/output
python3 "$SKILL_DIR/scripts/figure_audit.py" --output-dir /app/output --result /app/output/result.json

# 5. 交付前自查（0 模型请求）
python3 -m json.tool /app/output/result.json >/dev/null && echo RESULT_JSON_OK
python3 - <<'EOF'
import json
r = json.load(open('/app/output/result.json'))
need = ["case_id","status","cleaning","descriptive","hypothesis_test","effect_size",
        "confidence_interval","interpretation","limitations"]
missing = [k for k in need if k not in r]
assert not missing, missing
print("9 fields OK, status =", r["status"], ", analyses =", len(r["hypothesis_test"]["analyses"]))
EOF
# figure_audit 必须 exit 0（见第 2/4 步）；非 0 时按违例码修复后重跑
```

## 方法决策规则（硬性）

| 数据形态 | 图形 | 强制 |
|---|---|---|
| 分组数值比较 | 箱线+抖动散点 | 须=1.5×IQR 相邻值；每组 n<10 强制全点；n>50 确定性子样本 50 |
| 非参路线（MWU/KW） | 追加 ECDF | 图例含每组 n |
| 两数值变量 | 散点+OLS 参考线 | 标注 r |
| 分类计数 | 频数条形图 | y 轴从 0 起 |
| **禁止** | n<30 任一组的 bar+SE/SD 组间比较图 | dynamite plot；audit 命中 `RULE_VIOLATION_BAR` |
| 图注 | 每组 n/均值/SD + 单位 + 检验方法 + p | 与 result.json 一致（容差 0.005），否则 `CAPTION_NUMBER_MISMATCH` |
| 覆盖 | 每个检验过的分析 ≥1 张合规图或显式 waiver | 否则 `MISSING_COVERAGE` |

检验路线（pipeline 内建，与图形绑定）：两组 = 正态+齐→Student t / 正态不齐→Welch t /
否则 MWU（tie 校正）；k 组 = 全正态+齐→ANOVA / 正态不齐→Welch ANOVA / 否则 KW（tie 校正）。
正态性 = D'Agostino K²（n≥8 才做，否则保守非正态）；齐性 = Levene（median 中心）。

## 预算表（总计 ≤8 次模型请求）

| 步骤 | 请求数 |
|---|---|
| 0 定向 | 1 |
| 1–2 跑脚本 + 看输出 | 1 |
| 3 读 digest + decide | 1 |
| 4 finalize + 重跑 + 审计 | 1 |
| 5 自查 + 撰写最终答复 | 2 |
| 机动（异常修复） | 2 |
| **合计** | **≤8** |

## 异常处理表

| 异常 | 识别 | 处置 |
|---|---|---|
| 组内 n<8 | digest 假设警告「保守按非正态」 | 自动走非参路线；箱线图强制全点 |
| 组内方差为零 | K² 返回 zero variance / Welch 除零 | 记 exceptions，status=partial，该结局跳过推断 |
| 缺失比例高 | cleaning.missing.counts | report_and_exclude（按变量有效 n）；>20% 写入 uncertainty |
| 假设不成立 | digest 第 4 项 | 门控自动降级（t→Welch→MWU；ANOVA→Welch ANOVA→KW），记录 reason_code |
| 单位不明 | 图注「单位未注明」 | 保留分析，limitations 标注；可在 decide 用 rename 不影响单位 |
| SQLite 连接失败/无表 | exceptions 记录 | 用 CSV 继续；status=partial 并说明 |
| CSV 无表头 | meta.header=false | 列名 col1..colN；task.md 有「列序」则按列序命名 |
| 数值以 TEXT 存储（wine 类） | cleaning.type_coercion | 强制转数值并记录条数 |
| matplotlib 缺失 | figures.md channel=svg | SVG 兜底，交付不中断 |
| k 组水平 >8 | limitations | 不自动做全水平 k 组检验；task 给两个焦点水平则做两组比较 |
| 审计违例 | 违例码 | 按码修复：补图/重跑 forge/decide 加 waiver/删违例条形图 |

## 文件清单

```
SKILL.md            本文件
GITHUB_URL.txt      GitHub 树 URL + SKILL.md
README.md           用途与维护
scripts/statcore_c.py    stdlib 统计核心（分布函数/检验/效应量，scipy 已交叉校验）
scripts/pipeline_c.py    一键 baseline：run / decide / finalize
scripts/figure_forge.py  重心1：规则引擎 + PNG/SVG 双通道渲染
scripts/figure_audit.py  重心2：图表证据机器审计（5 违例码）
references/figure-selection.md       选图规则表与反例
references/caption-rules.md          图注必备要素与机读格式
references/dual-channel-rendering.md 双通道等价要素与降级策略
examples/make_synthetic.py   合成数据生成器（合成示例）
examples/run_example.sh      端到端自测：好例 exit 0 + 埋雷三连 exit 1
examples/minimal-example.md  最小示例说明（合成示例）
examples/example_output/     真实文本产物（result.json/report.md/digest.md/figures.md/fig*.svg/audit_pass.log）
```
