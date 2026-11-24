# audience-levers.md — 听众与时长杠杆的定量依据

本文件是 `scripts/workorder_compile.py` 推导杠杆（derived levers）的依据文档。
所有数值为可配置的工程默认，不是普适真理；修改默认请同时改本文件。

## 1. 工作订单六字段

| 字段 | 取值（受控） | 抽取优先级 |
|---|---|---|
| audience | specialist / mixed / general | case.json 结构化字段 → task.md 关键词 → TO_FILL |
| duration_min | 正整数（分钟） | 结构化 → 正则 `(\d+)\s*(minutes?|mins?|分钟)` → TO_FILL |
| slide_count | 整数或区间 [min,max] | 结构化 → 区间/单值正则 → TO_FILL |
| venue | review / defense / group_meeting / generic | 结构化 → 关键词（defense、group_meeting 先于 review 匹配）→ TO_FILL |
| language | en / zh | 结构化 → 关键词 → task.md CJK 占比启发式 → TO_FILL |
| goal | 自由文本 | 结构化 → `^goal:/目标：` 行 → TO_FILL |

**TO_FILL 纪律**：抽不到就写 `TO_FILL` 并把推导所用默认值记入 `assumptions`。
默认值：audience=mixed、duration_min=10、slide_count=round(duration)（约 1 页/分钟
启发式）、venue=generic（无场合特化规则）、language=en（或 CJK 占比启发式）、
goal 不参与定量推导但 storyboard 的 message 必须服务于它。

## 2. 背景比例带（S5 的依据）

背景页 = 角色 ∈ {hook, problem, gap} 的主故事线页（backup 不计入分母）。

| audience | 背景比例带 | 理由 |
|---|---|---|
| specialist | 0.05 – 0.15 | 同行专家共享先验；铺垫超过 15% 被视为浪费时间，问题定义一页即可。 |
| mixed | 0.15 – 0.30 | 评审委员会等混合听众：需要共同语境，但超过 30% 说明主线被背景挤占。 |
| general | 0.30 – 0.45 | 面向公众/跨领域：术语与动机必须充分铺垫，但超过 45% 就没有内容页了。 |

带边界为闭区间。页数少时取整注意：10 页 mixed 意味着背景页只能是 2 或 3 张
（1 张 = 0.10 低于下限），规划 storyboard 时先算可行整数解。

## 3. 语速与时间模型（S3 的依据）

- **wpm = 130 词/分钟**（Latin）：学术英语讲演的常用规划值；快速母语者可达
  150+，但含数字、公式口述时应取低值。`--wpm` 可覆盖。
- **cjk_cpm = 240 字/分钟**（CJK 表意文字按字计）：中文正式讲演约 220–260
  字/分钟。`--cjk-cpm` 可覆盖。混合文本按词与字分别计时后相加。
- **min_seconds_per_slide = 20s**：(a) 求和时的每页下限（转场、翻页、指图都
  消耗时间，备注为零的页也不是零成本）；(b) 非备用页备注的原始估计低于该值
  即判 S3"备注过短"——没有讲稿的页在台上必然超时或冷场。
- **总时长带 = [0.85, 1.15] × duration**：低于 0.85 说明内容不足以支撑时长
  （台上会提前尬场），高于 1.15 必然超时；12 分钟合同的可行区间为
  612–828 秒。
- **每页时间预算 = duration_seconds / slide_count_nominal**：只是参照值，
  不要求每页均匀；S3 只校验总量与下限。

### 由时间预算反推备注长度

`target_words ≈ per_slide_seconds × wpm / 60`。例如 12 min / 10 页 = 72 s/页，
wpm=130 时约 156 词/页；中文场合约 288 字/页。写备注时按此定量落笔，
而不是"写一段看看"。

## 4. 结论位置规则（S4 场合子规则的依据）

| venue | 规则 | 机理 |
|---|---|---|
| review | conclusion_first：首个 conclusion 页 0 基序号 ≤ ceil(n_main/3) | 评审先听结论再判证据；结论压尾的 deck 在前 2/3 都在消耗评委耐心。 |
| defense | limitations_before_conclusion：存在 limitation 页且先于 conclusion | 答辩委员会最忌"结论大于证据"；先亮边界再下结论是防御性姿态。 |
| group_meeting | methods_progress_emphasis（不设硬门控） | 组会听众关心方法细节与进度风险；结论位置自由。 |
| generic | standard_spine（仅主干顺序） | 场合未知时的保守默认。 |

0 基序号 ≤ ceil(n_main/3) 的含义：n=10 时 conclusion 可出现在第 5 页及以前
（第 1–4 页留给 hook/problem/approach/首个 result），即"前约 1/3 加一页容差"。

## 5. 结构化与文本冲突

case.json 结构化字段优先于 task.md 文本抽取；两者都抽到但取值不同时，
以结构化为准并在 `assumptions` 记录冲突（task.md 里出现 "specialists" 之类
词不代表听众类型就是 specialist——这正是不能只做文本匹配的原因）。
