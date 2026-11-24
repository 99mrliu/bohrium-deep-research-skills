# 阶段门（G0–G7）设计与处置手册

阶段门的目标：把"丢工作、契约缺失、数字不可追溯、报告漂移、裁决悬空"变成
**机器可判定的 FAIL**，任一 FAIL 即 exit 1 并打印门号与违例码。执行：
`python3 scripts/gate_check.py --input /input --work /app/work --output /app/output`

## 各门语义与失败处置

### G0 登记一致性
- 语义：manifest.json 登记的输入 sha256 可复算一致；阶段产物/交付物哈希未被篡改。
- 失败含义：`G0_INPUT_CHANGED` = 输入在 run 之后被改动（统计结论已失效）；
  `G0_STAGE_CHANGED` = 阶段产物与登记不符（有人手工改了中间产物）。
- 处置：输入变化 → 从 `pipeline_e run` 完整重跑；阶段产物被改 → 重跑，不要手改 JSON。

### G1 清洗闭合律
- 语义：`rows_raw == rows_kept + rows_dropped`，且 result.cleaning 与 stage_02 一致。
- 失败含义：清洗账目不闭合，存在"悄悄消失的行"。
- 处置：只可能由手工编辑引起；重跑 pipeline。闭合律是清洗可信的最小不变量。

### G2 契约骨架先行
- 语义：stage_05_result_draft.json 存在、`skeleton_fields` 覆盖 case.json
  output_contract.required_fields、status=partial，且 seq 序号小于 stage_04（推断）。
- 失败含义：流水线没有"先写骨架再填数"，崩溃将丢全部工作。
- 处置：正常流程不会失败；失败说明产物被拼装过，重跑。

### G3 数字可溯源（UNTRACEABLE_NUMBER）
- 语义：result.json 中每结局每组的 n、均值、主 p、主统计量必须与 stage_03/04 完全一致。
- 失败含义：交付数字没有可追溯来源（手工编数、四舍五入二次加工）。
- 处置：重跑 pipeline；任何数字调整必须改流水线而非改 result.json。

### G4 诚实声明非空
- 语义：uncertainty、limitations 均非空。空列表=未声明剩余不确定性，不合格。

### G5 status 纪律
- 语义：status ∈ {complete, partial, failed}；partial 必须 exceptions 非空。
- 注意 `"success"` 不在枚举内（与平台评分口径对齐，contract_lint 同步拦截）。

### G6 报告数字不漂移（REPORT_NUMBER_DRIFT）
- 语义：report.md 中每个 `p = x.xxxx` / `p < 0.0001` / `<kind> = x.xxxx`
  （hedges_g/eta2/omega2/eps2/rank_biserial）必须能在 result.json 找到同写法来源；
  反之 result.json 的每个主 p、主效应量必须在 report.md 出现。双向核对。
- 失败含义：报告被手工改过（哪怕一个数字），或报告漏报主结果。
- 处置：改 pipeline 的报告模板，不要手改 report.md；改后 finalize + 复查。

### G7 裁决清零
- 语义：digest.md 不允许残留 `- [PENDING]` 行。所有自动裁决必须经 agent
  confirm（`decide --confirm-all` 或 `--confirm DEC-xxx`）或 override（`--set key=value`）。
- 设计意图：把 ≤5 个关键判断（分组列、结局、子集、DB 口径、单位）显式化，
  既不浪费模型请求，又保留人类/agent 的最终责任。

## 与 manifest / lint / replay 的关系
- run_manifest check 管"哈希与登记一致"（防篡改、防输入漂移）；
- contract_lint 管"交付物结构合法"（契约层面）；
- gate_check 管"过程与内容一致"（语义层面）；
- replay_diff 管"换个目录重跑字节级相同"（确定性层面）。
四层互相独立，任一 exit 1 都不得交付。
