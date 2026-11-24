# 通用实验失效模式库（failure_mode_library.md）

本文件是 `risk_fmea.py map` 的**唯一失效模式来源**。脚本抽取本文第一个 ` ```json ` 代码块，
按"步骤原型（prototype）关键词 → 失效模式"进行映射。扩展方法（保持 JSON 合法即可）：

- 新步骤类型：在 `prototypes` 加一条，给 `keywords` 和 `failure_modes`（引用 id）。
  匹配规则：纯 ASCII 关键词按**词边界**匹配（`tem` 不会误中 `temperature`），
  含中文的关键词按小写子串匹配。
- 新失效模式：在 `failure_modes` 加一条，字段必须齐全，然后在相关 prototype 中引用。
- 步骤匹配不到任何原型时，脚本会给该步骤打 `ORPHAN-WARN`；也可在步骤 JSON 上加
  `"prototype_hint": ["PROT-XXX"]` 强制指定原型。
- 评分：severity / occurrence / detection 各 1–5，RPN=乘积（最大 125）。库内为通用基准分；
  具体案例可在步骤的 `overrides` 里按证据上调/下调并写 `reason`（科学诚实：理由必须可定位
  到 case.json 路径或标注为假设）。

## 失效模式字段约定

| 字段 | 含义 |
|---|---|
| `detection_criterion` | 可观测判据：什么现象算此异常发生（必须可观察、可操作，禁止"注意安全"式空话） |
| `confirm_method` | 判据确认方法：如何排除误报（对照/标准样/记录复核） |
| `stop_loss` | 止损点：确认后**先于原因分析**立即执行的动作 |
| `fallback` | 替代路径：止损后方案如何继续 |
| `owner` | 责任人或确认项归属 |
| `escalation` | 何时停止自主处置、升级人工/专家确认 |
| `design_feedback` | 反向设计要求：该失效模式为高优先级时必须如何改设计（预防优于处置） |

## 八大通用失效模式模板（人读版）

1. **FM-CONTAM 污染**（S4/O3/D3）：判据=溶液浑浊·沉淀·变色、薄膜针孔/异常颗粒、空白对照异常任一；
   止损=隔离受污染批次并标记、停止共用耗材；替代=重开试剂+更换耗材+清洁腔体后重做；
   升级=连续 2 批污染 → 专家确认环境洁净度。
2. **FM-NOSIGNAL 无信号/无响应**（S4/O3/D2）：判据=信号低于基线噪声 3σ 或目标特征峰/条带缺失；
   止损=暂停同参数批次、保留样品勿丢弃；替代=标准样校验仪器→重做样品→参数域内重新制备；
   升级=标准样也异常 → 设备管理员。
3. **FM-REPRO 重复性差**（S3/O4/D3）：判据=同条件 3 次重复关键指标 RSD>15%；
   止损=暂停批量制备、回到单变量排查；替代=固定环境条件、追加对照组、小步扫描预实验矩阵；
   升级=两轮排查仍 RSD>15% → 专家复核方案。
4. **FM-SAMPLE 样本不足**（S3/O3/D2）：判据=可用样品数 < 计划测量数或 n<3 统计功效不足；
   止损=停止破坏性测试、优先关键表征；替代=缩减测量矩阵至关键参数点、按预算追加批次；
   升级=预算/时间不足以补足 → 人工决策缩减研究目标。
5. **FM-EQBUSY 设备占用/排期已满**（S3/O4/D1）：判据=预约系统无可约时段，或所需 slot 数
   超过 slots_per_week × 剩余周数（用 case.json booking 字段对账）；
   止损=不无约到场排队、冻结依赖该设备的后续步骤；替代=换替代设备、调整步骤顺序先做非依赖步骤；
   升级=deadline 内排期缺口 >1 周 → 人工调整合同或申请延期。注意：组织方合同为前瞻约定，
   排期状态写入 confirmation_items，不得当作已确认事实。
6. **FM-REAGENT 试剂缺货/耗尽**（S4/O2/D1）：判据=库存低于单批用量×2 或货期超 deadline 余量；
   止损=停用最后一份库存做非关键实验；替代=启用双供应商备选（写入 confirmation_items）、
   更换等效规格并做验证批；升级=无等效替代 → 人工确认变更方案。
7. **FM-DRIFT 参数漂移**（S3/O3/D4）：判据=设备读数与校准标准偏差超手册允差（如温度 ±2°C）；
   止损=暂停依赖该参数的所有批次；替代=校准后复跑标准样、第二台同类设备交叉验证；
   升级=校准失败 → 设备管理员维修，排期影响转 FM-EQBUSY 处理。
8. **FM-SAFETY 安全事故**（S5/O2/D1）：判据=烟雾/异味/泄漏/报警触发/人员不适任一；
   止损=立即停止实验、切断相关电源气源、按应急预案撤离；替代=无替代路径，安全员确认后方可恢复；
   升级=立即升级安全员与 PI。severity=5，**无论 RPN 一律进入决策树**。

附加：**FM-DATA 数据丢失/记录不全**（S3/O2/D2）：判据=原始数据文件缺失或记录缺关键参数项；
止损=暂停依赖该数据的结论；替代=双备份（本地+服务器），缺失批次按记录重测；
升级=无法重测 → 写入 uncertainty 并人工确认。

## 机器可读库（脚本读取此块，修改请先读字段约定）

```json
{
  "version": "1.0",
  "prototypes": [
    {"id": "PROT-SOLUTION", "name": "溶液配制",
     "keywords": ["溶液", "配制", "溶解", "前驱体", "precursor", "solution", "dissolve"],
     "failure_modes": ["FM-CONTAM", "FM-REAGENT", "FM-SAFETY", "FM-SAMPLE"]},
    {"id": "PROT-SPIN", "name": "旋涂/涂布",
     "keywords": ["旋涂", "涂布", "刮涂", "喷涂", "spin", "coating", "成膜"],
     "failure_modes": ["FM-CONTAM", "FM-REPRO", "FM-DRIFT", "FM-EQBUSY", "FM-SAMPLE"]},
    {"id": "PROT-ANNEAL", "name": "退火/热处理",
     "keywords": ["退火", "热处理", "加热", "烧结", "固化", "anneal", "bake"],
     "failure_modes": ["FM-DRIFT", "FM-EQBUSY", "FM-SAFETY", "FM-REPRO"]},
    {"id": "PROT-CHAR", "name": "结构表征",
     "keywords": ["表征", "xrd", "sem", "tem", "衍射", "显微", "物相", "形貌", "characteriz"],
     "failure_modes": ["FM-NOSIGNAL", "FM-EQBUSY", "FM-DRIFT", "FM-SAMPLE"]},
    {"id": "PROT-MEASURE", "name": "性能测量",
     "keywords": ["测量", "测试", "光谱", "吸收", "电学", "效率", "iv", "pl", "uv", "measure"],
     "failure_modes": ["FM-NOSIGNAL", "FM-DRIFT", "FM-EQBUSY", "FM-DATA"]},
    {"id": "PROT-CULTURE", "name": "培养/生长",
     "keywords": ["培养", "细胞", "生长", "孵育", "传代", "接种", "culture", "incubat"],
     "failure_modes": ["FM-CONTAM", "FM-SAMPLE", "FM-REPRO", "FM-EQBUSY", "FM-SAFETY"]},
    {"id": "PROT-REPLICATE", "name": "重复性验证",
     "keywords": ["重复", "复现", "批次", "统计", "replicat", "reproducib"],
     "failure_modes": ["FM-REPRO", "FM-SAMPLE", "FM-DATA"]},
    {"id": "PROT-DATA", "name": "数据记录与分析",
     "keywords": ["数据", "记录", "汇总", "分析", "归档", "data", "record"],
     "failure_modes": ["FM-DATA", "FM-REPRO"]}
  ],
  "failure_modes": [
    {"id": "FM-CONTAM", "name": "污染", "category": "质量",
     "severity": 4, "occurrence": 3, "detection": 3,
     "detection_criterion": "溶液浑浊/沉淀/变色、薄膜出现针孔或异常颗粒、空白对照信号异常，任一出现即判污染",
     "confirm_method": "同批空白对照与未开封试剂对照并行观察，排除仪器背景误判",
     "stop_loss": "立即隔离受污染批次并贴标，停止一切共用耗材/共用腔体操作",
     "fallback": "重开新批次试剂、更换全部耗材、清洁腔体后重做该步骤",
     "owner": "操作者",
     "escalation": "连续 2 批污染 → 停止自主处置，升级专家确认环境洁净度（写入 confirmation_items）",
     "design_feedback": "关键配制步骤加空白对照与洁净度预检；污染敏感步骤预留 1 次重做的试剂与时间余量"},
    {"id": "FM-NOSIGNAL", "name": "无信号/无响应", "category": "质量",
     "severity": 4, "occurrence": 3, "detection": 2,
     "detection_criterion": "目标信号低于基线噪声 3σ，或目标特征峰/条带/读数完全缺失",
     "confirm_method": "用标准样（或已知阳性样）同机复测，区分样品问题与仪器问题",
     "stop_loss": "暂停同参数批次制备，保留全部样品与原始数据，不得丢弃",
     "fallback": "标准样校验仪器→重制样品→在有限参数域内换参数点重新制备",
     "owner": "操作者",
     "escalation": "标准样复测仍异常 → 升级设备管理员检修；样品两次重制无信号 → 专家确认方案可行性",
     "design_feedback": "表征/测量步骤前置标准样校验环节；每个表征步骤指定一个可判读的成功判据"},
    {"id": "FM-REPRO", "name": "重复性差", "category": "质量",
     "severity": 3, "occurrence": 4, "detection": 3,
     "detection_criterion": "同条件 3 次重复的关键指标 RSD>15%，或批次间趋势方向不一致",
     "confirm_method": "复核原始记录确认操作一致（环境温湿度、陈化时间、操作者），排除记录错误",
     "stop_loss": "暂停批量制备与结论外推，回到单变量排查",
     "fallback": "固定环境条件，追加对照组，按预实验矩阵在参数域内小步扫描定位敏感变量",
     "owner": "操作者",
     "escalation": "两轮单变量排查后 RSD 仍>15% → 专家复核方案与参数域（写入 confirmation_items）",
     "design_feedback": "关键步骤加预实验（小规模单变量矩阵）并预设可接受 RSD 阈值；方案必须含 ≥3 次独立重复"},
    {"id": "FM-SAMPLE", "name": "样本不足", "category": "资源",
     "severity": 3, "occurrence": 3, "detection": 2,
     "detection_criterion": "可用样品数 < 计划测量数，或关键对比组 n<3 统计功效不足",
     "confirm_method": "盘点样品台账与测量矩阵，确认缺口数量",
     "stop_loss": "停止破坏性/消耗性测试，把剩余样品优先分配给关键表征",
     "fallback": "缩减测量矩阵至关键参数点；按预算与排期余量追加制备批次",
     "owner": "操作者",
     "escalation": "预算/时间不足以补足统计功效 → 升级人工决策：缩减研究目标并在 result.json 标注 partial",
     "design_feedback": "按测量矩阵 + 1 次重做余量反推样品制备数；破坏性测试样品单独多备"},
    {"id": "FM-EQBUSY", "name": "设备占用/排期已满", "category": "资源",
     "severity": 3, "occurrence": 4, "detection": 1,
     "detection_criterion": "预约系统无可约时段，或所需 slot 数 > booking.slots_per_week × 剩余周数（按 case.json booking 字段对账）",
     "confirm_method": "查预约系统并对账 case.json 中 booking.window_days/slots_per_week/slot_hours",
     "stop_loss": "不无约到场排队；冻结依赖该设备的后续步骤，避免半成品积压失效",
     "fallback": "改用替代设备（如加热台替代烘箱）；调整步骤顺序，先做不依赖该设备的步骤",
     "owner": "设备协调人",
     "escalation": "deadline 内排期缺口 >1 周 → 升级人工调整前瞻合同或申请延期（写入 confirmation_items）",
     "design_feedback": "排期紧张的设备写双设备/替代设备策略入 confirmation_items；步骤排序把紧俏设备步骤错峰"},
    {"id": "FM-REAGENT", "name": "试剂缺货/耗尽", "category": "资源",
     "severity": 4, "occurrence": 2, "detection": 1,
     "detection_criterion": "库存低于单批用量×2，或供应商货期超过 deadline 剩余天数",
     "confirm_method": "盘点库存台账，并按前瞻合同 reagents 的 pack_size/unit_price 估算可支撑批次数",
     "stop_loss": "停用最后一份库存做任何非关键实验",
     "fallback": "启用双供应商备选渠道（写入 confirmation_items）；更换等效规格试剂并先做验证批",
     "owner": "采购责任人",
     "escalation": "无等效替代且货期不可接受 → 升级人工确认变更研究方案（honest partial）",
     "design_feedback": "关键试剂采用双供应商策略并写入 confirmation_items；下单时点早于首批实验 ≥1 个货期"},
    {"id": "FM-DRIFT", "name": "参数漂移", "category": "设备",
     "severity": 3, "occurrence": 3, "detection": 4,
     "detection_criterion": "设备读数与校准标准偏差超出设备手册允差（如温度 ±2°C、转速 ±50rpm）",
     "confirm_method": "用校准标准件/标准样复测读数，与设备手册 spec 字段对账",
     "stop_loss": "暂停依赖该参数的所有批次，隔离漂移期间产出的样品并单独标记",
     "fallback": "校准后复跑标准样确认恢复；或用第二台同类设备交叉验证后继续",
     "owner": "设备管理员",
     "escalation": "校准失败 → 升级设备管理员维修；停机排期影响按 FM-EQBUSY 流程处理",
     "design_feedback": "温控/转速敏感步骤前置校准确认点；漂移敏感批次保留同期标准样作为事后对账依据"},
    {"id": "FM-SAFETY", "name": "安全事故", "category": "安全",
     "severity": 5, "occurrence": 2, "detection": 1,
     "detection_criterion": "烟雾、异味、泄漏、报警触发、人员不适任一发生",
     "confirm_method": "无需排除误报：任何安全信号一律按真实事故先行处置",
     "stop_loss": "立即停止实验、切断相关电源/气源、按实验室应急预案撤离并报告",
     "fallback": "无替代路径：事故处置完毕且安全员书面确认前，方案全面暂停",
     "owner": "安全员",
     "escalation": "立即升级安全员与 PI；恢复条件写入 confirmation_items（安全类）",
     "design_feedback": "涉危险化学品/高温/高压步骤强制写 PPE 与应急处置卡；安全确认项永远是 confirmation_items 第一类"},
    {"id": "FM-DATA", "name": "数据丢失/记录不全", "category": "数据",
     "severity": 3, "occurrence": 2, "detection": 2,
     "detection_criterion": "原始数据文件缺失/损坏，或实验记录缺少关键参数项（温度、转速、批号等）",
     "confirm_method": "对账数据目录与样品台账，逐批核对记录完整性",
     "stop_loss": "暂停依赖该数据的一切结论与下游分析",
     "fallback": "执行双备份（本地+服务器）；记录不全的批次按台账重测关键项",
     "owner": "操作者",
     "escalation": "无法重测的数据缺口 → 写入 result.json 的 uncertainty 并升级人工确认是否接受",
     "design_feedback": "每个产数据步骤规定当日记账（记录模板含关键参数项）；交付前做一次数据完整性对账"}
  ]
}
```
