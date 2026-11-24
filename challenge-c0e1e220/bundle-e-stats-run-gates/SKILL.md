---
name: stats-run-gates
description: >-
  统计分析与结果解读的过程质量控制技能：一键确定性 baseline 流水线 + G0–G7 阶段门 +
  契约 lint + manifest 哈希登记 + 影子复跑。Use when the task requires statistical
  analysis of tabular data (CSV/SQLite) under /input with a strict output contract
  (/app/output/result.json), especially when work loss, missing contract fields, or
  non-reproducible results are the main failure modes. 何时触发：需要"统计比较 + 契约
  交付 + 可复跑核验"的案例。不做什么：不做因果推断、不做机器学习建模、不替 agent 解释
  业务含义（解释模板已内置但仍需 agent 核对 digest 裁决）。
---

# stats-run-gates — 过程质量控制、契约强制与确定性复跑

## 1 何时使用 / 边界

适用：
- 输入为 `/input/case.json` + `/input/task.md` + 表格数据（CSV 有/无表头、SQLite，数值可能以 TEXT 存储）；
- 任务要求按分组变量比较一个或多个数值结局（两组或多组），交付带固定 output_contract 的 `result.json`；
- 你担心：中途崩溃丢工作、契约字段缺失被扣分、数字无法追溯、复跑结果不一致。

不适用（不要硬套）：
- 回归/预测建模、时间序列、生存分析、贝叶斯推断；
- 需要领域知识判断结论业务含义的环节（本技能只保证统计与工程正确性）；
- 数据非表格（图像、文本、JSON 流）。

## 2 运行契约

- 输入：`/input/case.json`（含 case_id、data_files、output_contract.required_fields、constraints）、`/input/task.md`、数据文件。
- 中间产物：`/app/work/`：`stage_01_ingest.json`（输入 sha256+解析参数）、`stage_02_clean.json`（清洗账本+闭合律+cleaned 哈希）、
  `stage_03_descriptive.json`、`stage_04_inference.json`、`stage_05_result_draft.json`（**契约骨架先于推断落盘**）、
  `digest.md`（待确认裁决）、`manifest.json`（哈希登记）、`seq.log`、`decisions.json`。
- 交付：`/app/output/result.json`（含 case_id 与 required_fields 全部 9 字段）+ `report.md` + `figure.svg`。
- 诚实 partial：失败/部分完成时 `status="partial"` 且 `exceptions` 非空记录原因，**绝不静默、绝不预制答案**；
  流水线第一步先把 status=partial 的契约骨架写到交付位，崩溃也留下诚实中间态。
- status 枚举仅 `complete / partial / failed`（注意：`"success"` 是非法值，会被 lint 拦截）。
- 所有数字必须真实运行得出：G3 门检会把 result.json 的每个 n/均值/主 p 与阶段产物逐一核对。

## 3 精确命令工作流

```bash
# 0. 定向（1 次模型请求内完成阅读）
cat /input/case.json /input/task.md; ls -la /input

# SKILL_DIR 探测（技能安装目录，通常 /skills/weekly-skill）
SKILL_DIR="${SKILL_DIR:-/skills/weekly-skill}"
[ -f "$SKILL_DIR/scripts/pipeline_e.py" ] || \
  SKILL_DIR="$(dirname "$(find / -maxdepth 4 -name pipeline_e.py -path '*scripts*' 2>/dev/null | head -1)")/.."
SCR="$SKILL_DIR/scripts"

# 1. 一键 baseline（0 模型请求；从原始数据到 result.json+report.md+figure.svg+manifest.json）
#    分组列/结局/子集由 task.md 判定；规则见第 5 节。三案例对应写法：
#      iris-like（无表头，末列类别）:   --group-by col4 --outcomes col0,col1,col2,col3 --unit cm
#      wine-like（首列 1/2/3 类别）:    --group-by col0 --outcomes col7,col1
#      concrete-like（按龄期焦点子集）: --group-by age --outcomes strength --groups 28,90 --unit MPa
python3 "$SCR/pipeline_e.py" run --input /input --work /app/work --output /app/output \
  --group-by <分组列> --outcomes <结局1,结局2> [--groups <子集标签>] [--unit <单位>]

# 2. 深度审计（本 bundle 机器可检核心，全部本地脚本，0 模型请求）
python3 "$SCR/run_manifest.py" check --input /input --work /app/work --output /app/output

# 3. 读 digest，确认/覆盖裁决（≤5 项；这是唯一需要判断的环节）
cat /app/work/digest.md
python3 "$SCR/pipeline_e.py" decide --work /app/work --confirm-all          # 逐项确认用 --confirm DEC-001
#    如需覆盖（如改用焦点子集）：--set groups=28,90  /  --set group_column=col4

# 4. finalize 重写全部交付物（应用裁决后确定性复跑）
python3 "$SCR/pipeline_e.py" finalize --input /input --work /app/work --output /app/output \
  --group-by <同上> --outcomes <同上> [--groups <同上>] [--unit <同上>]

# 5. 交付前自查（全部 exit 0 才可交付）
python3 -m json.tool /app/output/result.json > /dev/null && echo JSON_OK
python3 "$SCR/gate_check.py"     --input /input --work /app/work --output /app/output   # G0–G7
python3 "$SCR/contract_lint.py"  --case /input/case.json --result /app/output/result.json
python3 "$SCR/replay_diff.py"    --input /input --work /app/work --output /app/output   # 影子复跑逐字节一致
```

## 4 阶段门与违例码（gate_check，任一 FAIL 即 exit 1）

| 门 | 内容 | 违例码 |
|---|---|---|
| G0 | 输入/阶段产物/交付物 sha256 与 manifest 登记一致 | G0_INPUT_CHANGED / G0_STAGE_CHANGED / G0_*_MISSING |
| G1 | 清洗闭合律 rows_raw == rows_kept + rows_dropped | G1_CLOSURE / G1_INCONSISTENT |
| G2 | 契约骨架先于推断落盘（seq 顺序）且覆盖 required_fields | G2_SKELETON_* / G2_ORDER |
| G3 | result.json 每组 n/均值/主 p/统计量可在 stage_03/04 找到一致来源 | UNTRACEABLE_NUMBER |
| G4 | uncertainty 与 limitations 非空 | G4_*_EMPTY |
| G5 | status 枚举合法；partial 时 exceptions 非空 | G5_INVALID_STATUS / G5_DISHONEST_PARTIAL |
| G6 | report.md 的 p 值/效应量与 result.json 一致（双向核对） | REPORT_NUMBER_DRIFT |
| G7 | digest.md 无残留 [PENDING] 裁决 | G7_PENDING_DECISION |

contract_lint 违例码：`MISSING_FIELD`、`INVALID_STATUS`、`CASE_ID_MISMATCH`、`DANGLING_REFERENCE`、
`PARTIAL_WITHOUT_EXCEPTIONS`、`EXCEPTION_SHAPE`、`SKELETON_SHIPPED`。

## 5 方法决策规则（硬性）

| 情形 | 规则 |
|---|---|
| 分组列选择 | task.md 明确指定（如"按 species/龄期/cultivar"）→ 用 `--group-by` 显式指定；未指定才用自动判定并确认 DEC-001 |
| 组数 > 6 | 任务指定的焦点子集用 `--groups a,b`；否则全组 omnibus 并确认 DEC-003 |
| 两组检验路线 | 全正态+方差齐→Student t；正态不齐→Welch t；否则 Mann-Whitney U（tie 校正） |
| k 组检验路线 | 全正态+齐→ANOVA；正态不齐→Welch ANOVA；否则 Kruskal-Wallis（tie 校正） |
| 正态性 | D'Agostino K²，n<8 保守按非正态；方差齐性 Levene（median 中心），α 读 constraints.alpha（默认 0.05） |
| 效应量 | 两组 Hedges g（bootstrap B=2000，seed=20240501，percentile CI）；k 组 η²/ω²（KW 路线 ε²）；位置差：参数法 Welch CI、非参 Hodges-Lehmann |
| 多重比较 | 事后两两与主检验同路线，Holm 校正 |
| 缺失 | report_and_exclude：分组变量缺失整行剔除；结局变量按逐变量有效 n，不零填不插补 |
| 完全重复 | 默认 flag_and_report（只标记不删除）；constraints.duplicate_policy="dedupe_exact_keep_first" 时删至首行 |
| 异常值 | 1.5×IQR 栅栏只标记不删除，报告影响行数 |
| 路线与经典结果冲突 | 主结论以门控路线为准；经典 ANOVA/Welch t 作为 reference 一并报告 |
| 解释措辞 | 区分统计显著与实际意义；禁用"证明"；携带单位；标注不适用条件 |

## 6 预算表（典型 6 次模型请求，上限 64 内）

| 步骤 | 请求数 | 内容 |
|---|---|---|
| 定向 | 1 | 读 case.json/task.md/ls，定 plan 参数 |
| baseline | 1 | 发 run 命令（脚本 0 请求） |
| digest 裁决 | 1 | 读 digest.md + decide + finalize |
| 自查修复 | 1 | 跑 4 个检查脚本；若 FAIL 按违例码修 |
| 报告核对 | 1 | 读 result.json/report.md 确认解释一致 |
| 余量 | 1–3 | 异常处置、复跑确认 |

## 7 异常处理表

| 异常 | 识别 | 处置 |
|---|---|---|
| 样本量 n<8 | assumptions.normality note | 保守按非正态→秩检验路线；limitations 注明 |
| 组内方差为零 | Levene 退化 / t 检验 se=0 | 检验返回保护值并记 exceptions；解释降级为描述 |
| 缺失比例过高 | cleaning.missing_by_variable | 有效 n<2 的组剔除并记 GROUP_SMALL_N；结局整体不可用记 OUTCOME_SKIPPED（partial） |
| 假设不成立 | Levene/D'Agostino p≤α | 门控自动换路线（Welch/秩），理由码写入 hypothesis_test.reason_code |
| 单位不明 | task.md 无单位 | unit=unspecified，DEC-005 待确认，limitations 注明 |
| SQLite 连接失败/无表 | stage_01 db_consistency.checked=false | 记 limitations，以 CSV 为准继续，不中断 |
| CSV/SQLite 不一致 | db_consistency.match=false | DB_MISMATCH exception（status=partial），DEC-004 待确认口径 |
| CSV 无表头 | parse_params.has_header=false | 列名 col0..colN，用位置引用（如 petal length=col2） |
| 数值以 TEXT 存储 | db column_types=TEXT | 一致性核对前 float 强转；CSV 侧 90% 可解析即按数值列 |
| 找不到分组列 | run 退出 FATAL | result.json 已留诚实 partial（SKELETON_NOT_FILLED）；用 --group-by 显式指定 |
| 复跑漂移 | replay_diff NONDETERMINISTIC_ARTIFACT | 按漂移字段路径排查：禁未播种随机、禁字典序依赖、禁时间戳外易变字段 |

## 8 文件清单

```
SKILL.md                      本文件
GITHUB_URL.txt                仓库地址
README.md                     用途与维护
scripts/statcore_e.py         独立 stdlib 统计核心（分布函数/检验/效应量/bootstrap/Holm）
scripts/pipeline_e.py         一键 baseline：run / decide / finalize，五阶段落盘+骨架先行
scripts/run_manifest.py       manifest 构建与校验（输入/阶段/交付物哈希登记）
scripts/gate_check.py         G0–G7 阶段门
scripts/contract_lint.py      result.json vs case.json 契约 lint
scripts/replay_diff.py        影子复跑逐字节确定性核验
references/stage-gates.md     阶段门设计与处置手册
references/contract-mapping.md 契约字段填充规则与诚实降级
references/determinism.md     确定性约定（种子/排序/浮点格式/易变字段）
references/honest-partial.md  诚实 partial 规范
examples/make_synthetic.py    合成示例数据生成器（合成示例）
examples/run_example.sh       端到端自检（好例 exit 0 + 埋雷拦截断言）
examples/minimal-example.md   最小调用说明（合成示例）
examples/example_output/      真实跑出的文本产物（含 manifest、stage 摘录、检查日志）
```
