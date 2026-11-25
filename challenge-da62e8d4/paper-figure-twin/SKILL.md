---
name: paper-figure-twin
description: "对真实论文曲线进行可追溯的手工 pixel 数字化，用轴 anchors 和 linear/log 映射对齐两个实际运行的候选数值输出，计算同 x 插值 RMSE/MAE/max error，保存 mapping ledger，并生成 SVG 与真实 PNG 的定量对照报告。适用于真实 PDF 无预抽取层、需要明确区分 digitized 与 paper-reported、拒绝以肉眼近似代替量化比较的任务；缺原图、刻度或 x 重叠时判为不可比。"
---

# Paper Figure Twin

把论文图中的手工 pixel 样本与实际运行的候选数值 series 做**可审计的定量对照**。绝不以“肉眼大概一致”替代数值比较；绝不自动 OCR、猜测刻度、自动识别曲线或补造 paper points。合成图的容差通过只表示与合成手工采样点一致，不叫论文复现、作者代码复现或科学结论验证。

## 平台契约（正式场景）

- 入口是 `/input/case.json` 与 `/input/task.md`；`/input` **只读**。真实论文 PDF 没有预抽取文本/曲线层，必须由人工查看页面或人工渲染后采样。不要把 PDF 文本抽取结果当作 manual digitization。
- 所有截图、手工标注草稿、候选 stdout/stderr、方法中间结果放 `/app/work`。最终 comparison、mapping、report、result 和图放 `/app/output`。不修改输入，不把验证预览 PNG 写入 Skill bundle。
- 正式端到端总时限 **900 秒**。保留材料清点、参数固定与渲染审计的时间；单候选超时也受 case/全局更小预算约束。
- 逐 case 读取 `output_contract`，不得按示例硬编码字段。`result.json` 顶层始终含 `case_id/status/sources/uncertainty/change_records`，并把合同声明的每一个字段直接平铺在顶层；这些标准字段也允许出现在合同中。额外工具字段只使用 `artifacts/comparison/mapping/report/errors/reproduction_verdict`，`summary` 仅在合同声明时生成。支持 list、直接 field mapping、`fields`/`required_fields` 与 JSON Schema，详见 reference。
- **任务状态与科学判定分离**：`status=success` 只表示材料、运行和合同交付完整；此时 `reproduction_verdict=pass/fail` 表示全部 pair 是否满足事前容差，数值 fail 仍是 `status=success` 且退出 2，数值 pass 退出 0。材料、映射、重叠、运行、渲染或交付不全为 `status=partial` 并退出 1；完全无法读取 case 时可 `status=unable` 并退出 1。`refused` 保留给明确拒绝执行的任务，本脚本不虚构该状态。partial 若有完整数值结论可保留其科学 verdict；缺 anchor、无重叠等不可比时为 `reproduction_verdict=not_comparable`。
- partial/unable 同样按能够读取的合同平铺动态字段，只写真实已产生的证据、失败原因和可用的 `result.json`；未生成的 comparison/mapping/report 为 null，不得伪造文件或曲线点。未知自定义字段只能取 `spec.contract_values` 中有证据的值，否则写 `{status:"unavailable", reason:..., evidence_required:true}` 并使交付保持 partial，绝不猜值。
- 所有生成路径字段相对于 `/app/output`（可用 `../work/...` 指向审计材料）；实际执行的 argv 原样保存用于复现。成功前回读 JSON 并检查合同字段和每个声明产物。
- `sources` 如实记录 PDF/图页/panel、文件 hash、每个候选 argv/cwd/exit code、运行输出 hash、实现来源和任务容差来源。`uncertainty` 记录逐点 pixel 不确定度、传播方法和范围限制。`change_records` 列出创建/修改的产物与未完成事项；不得把组织方合成输入或方法署名为作者代码。

完整字段与输入 schema 见 [references/contract.md](references/contract.md)。

## 必要材料与不可比条件

开始计算前必须同时具备：

1. 真实 PDF 和可查看的 source figure 文件（由 PDF 页面/panel 渲染）；记录原始 PDF 定位、渲染 DPI 及 `figure/page/panel`。本 Skill 不内嵌二进制，渲染 PNG 只放 work/output。
2. 每条目标 paper series 的**手工 pixel points**。每点都有 `pixel_x/pixel_y`、`source.locator`、`source_file`、`figure/page/panel`、`uncertainty.pixel_x/pixel_y` 和 `value_status: digitized`。
3. 每轴至少两个像素-数值 anchor；`pixel_scale` 为 `linear` 或 `log`。log 轴值必须为正，并保留每个 anchor 的拟合残差。
4. 两个候选数值方法的独立、可执行命令和预期 JSON/CSV 输出。不得只拿预存结果声称运行过。报告必须保留命令、环境、参数和退出码；预存 CSV/JSON 只是可检查的 fixture。
5. paper 与 candidate 的 y unit、x definition 完全一致，容差由 task 或运行前 spec 明确声明并注明单位；没有任务容差时必须在候选运行前声明，不能看结果后调整。

缺 source figure、缺轴刻度/anchor、不可信 locator、单位或 x 定义不一致、paper 点并非实际 pixel 采样、candidate x 与 paper 没有正宽度重叠，均不可比。停止并输出 partial，绝不造点。`paper-reported` 表格值不能改标记为 digitized 后混入 pixel 误差。

## 操作工作流

### 1. 固定来源、环境、参数和容差

读取 `/input/case.json` 和 `/input/task.md`，清单化 PDF、图页、panel、方法入口与参数。记录 Python/数值库/渲染器版本。把 PDF 页面手工渲染至 work 中的 source figure，人工确认坐标方向（SVG/图像 y pixel 通常向下）、log/linear 类型及单位。

根据任务指定 anchors 和容差生成 work 中的 spec。禁止 OCR 和自动 curve tracing。若采用半自动鼠标记录器，点击和选点仍由人完成，样本文件必须写 `manual_pixel_click`。源图与每点 uncertainty 一起冻结；候选运行后不得为使结果通过而修改它们。

### 2. 人工采样并保存 mapping ledger

逐点使用 paper figure 坐标，而非屏幕缩放后的未校正坐标。记录每条线的 figure/page/panel、locator 和像素误差。至少覆盖极值、转折及 candidate 需要对照的 x；不能把看到论文正文中的数值表当成 pixel 曲线。不要把平滑曲线补成额外“观测点”。

映射定义为：

- linear：`value = a * pixel + b`。
- log：`ln(value) = a * pixel + b`，所以 `value = exp(a * pixel + b)`。

两 anchors 可解得 `a,b`；更多 anchors 用最小二乘拟合并公开残差。pixel uncertainty 在线性轴上用 `|a| * pixel_uncertainty`；log 轴上用一阶传播 `|value*a| * pixel_uncertainty` 并说明只是局部估计。将 original pixel、转换值、anchor 残差、逐点 source/uncertainty 全量写入 `mapping.json`。

### 3. 真实运行两个候选

正式 case 为每个 candidate 给 argv 数组。脚本不用 shell 拼接，在设定 cwd 中执行并捕获 stdout/stderr、退出码与耗时。示例入口：

```bash
python3 /app/work/paper_figure_twin.py compare \
  --case /input/case.json \
  --spec /app/work/comparison_spec.json \
  --work /app/work \
  --output /app/output
```

脚本从本 Skill 的 `scripts/paper_figure_twin.py` 复制到 work 即可；若直接引用只读 Skill 路径，也可替换为实际安装路径。输入/输出均显式给出。任何 candidate 非零退出、超时、未生成声明输出均为错误而非“图上稍差”。

CSV 需要 `series_id,x,y,unit,x_definition`；JSON 需要 series id、unit、x_definition、points 和 source。每个 candidate series x 必须唯一；重复 x 不能任意排序成单调序列。数值需有限。

### 4. 同量纲、同 x、只插值不外推

逐 pair 校验 paper 和 candidate 的 unit 与 x_definition 字符串和语义。工具不做隐式单位换算，也不把 wall time、index、归一化 time 与 physical time 混为同 x。确需换算时，先在上游明确换算、记录依据并再进入比较。

共同 x 区间是两者 support 与 paper sample range 的交集。仅在 candidate 范围内的 paper x 处对 candidate 线性插值：

`c(x) = c_i + (c_{i+1}-c_i) * (x-x_i)/(x_{i+1}-x_i)`。

不插值 paper 再去猜测另一条网格上的“误差”，不外推，不用 pixel 距离代替 y 单位误差。至少两个对齐点且 overlap 正宽度，否则 partial。

### 5. 误差、容差与归因

令 `e_i = candidate_interpolated(x_i) - paper_digitized(x_i)`，以声明的 y unit 给出：

- `RMSE = sqrt(sum(e_i^2)/n)`；
- `MAE = sum(abs(e_i))/n`；
- `max_error = max(abs(e_i))`。

三项均须各自满足容差。同时保存 signed mean error、n、共同的 x min/max 与每行 aligned values。非零 signed bias 可提示系统偏移；max/RMSE 相对 MAE 很大可提示局部偏差或插值敏感性，但这些只是诊断，不能未经机制证据就断言模型因果错误。

材料与来源、环境、参数、两候选实际运行、完整数值表、图、误差归因缺一不可。渲染和视觉检查不能替代表格或数值判定。若任务要求对照 table，也应另存 paper-reported 表的 locator 和值，不能混称 digitized。

### 6. 渲染、目检与交付装盒

纯 stdlib SVG 是固定输出的基础路径，无需 SVG 库；优先保证文本 SVG 可读和可追溯。每个 pair 生成 overlay 与 error SVG，另生成 side-by-side SVG；source figure 用 `<image href="...">` 或相对文件链接嵌入，**不用 base64**。使用已有 numpy/matplotlib 的 Agg 后端生成真实 PNG，不用 `.svg` 改名冒充。matplotlib 缺失导致 PNG 不完整时 partial 并非静默成功。

目检检查 legend、axes、单位、series 标签、error zero line、error curve、中文或 ASCII 是否被裁切或遮挡；发现问题要修布局，但不得为美化改变误差值。交付层按当前 case 的 `output_contract` 动态装盒，不把示例字段列表写死：真实写入并回读 `comparison.json`、`mapping.json`、`report.md`、`result.json` 和全部声明图，路径与 `result.artifacts` 一致且相对 output。逐个断言合同字段位于 result 顶层，并检查 `spec.contract_values` 的证据值或结构化 unavailable。再报告非零退出码、任务 status、独立 reproduction_verdict、partial 限制、sources、uncertainty、change_records。这里是文件未读取/未生成的物理检查，不是基于“应该成功”的预测。

## 示例与验证

最小示例以组织方自创文本 SVG 为“合成论文原图”，含 anchors、9 个 manual paper points、两个可检查 CSV/JSON fixture、case/task/spec、run script 和预期文本。实际命令解析、变量替换、数值计算、文件写入、负例断言均由脚本真实执行，不接受“手动跑过”的替身。

```bash
bash examples/synthetic/run_example.sh /app/work/paper-figure-twin-verification
```

示例 candidate_a 通过，candidate_b 因递增系统偏差超差。因此核心 compare 完整交付后合法返回 **2 / status=success / reproduction_verdict=fail**，wrapper 检查该语义、编译、JSON、真实 PNG、约束和负例后返回 **0**。缺 anchor 与 x 无重叠均真实返回 **1 / status=partial / reproduction_verdict=not_comparable**，且无 comparison.json。自测覆盖 list、mapping、fields/required_fields、JSON Schema；Schema 集成测试通过 `spec.contract_values` 平铺 `custom_delivery`，partial 分支也验证动态字段。未知字段测试确认不伪造值且交付 partial，完全不可读 case 为 unable。

示例的可选参数是独立可写 verification 目录；省略时使用 `mktemp` 临时目录。脚本拒绝把预览写回 bundle，Python cache 也定向到 verification。部署运行同理保持工作目录、最终输出和 Skill 源文件边界。
