# 量表选择与设计协议（rubric_design）

## 1. 按研究类型选量表

| 纳入研究类型 | 思路来源 | 建议维度（可裁剪） |
|---|---|---|
| 随机对照试验（RCT） | RoB 2 | 随机化过程（随机序列+分配隐藏）、偏离既定干预、结局测量盲法、不完整结局数据、选择性报告 |
| 观察性研究（队列/病例对照） | ROBINS-I | 混杂偏倚、研究对象选择、干预/暴露分类、偏离既定干预、缺失数据、结局测量、选择性报告 |
| 诊断准确性研究 | QUADAS-2 | 病例选择、待评价试验、金标准、病例流程和进展情况 |
| 已有系统综述/Meta 分析 | AMSTAR 2 | 方案注册、检索全面性、纳排依据、质量评价、综合方法、发表偏倚、利益冲突 |

要点：选的是"思路"，落到本引擎时一律转成**声明式 JSON 量表**（rubric.json）。
维度命名用 snake_case 的 `dim_id`，人类可读名放 `name`。

## 2. 声明式 JSON 的字段语义

```json
{
  "scale_id": "mini-rob2-lite",        // 量表唯一标识，kebab-case
  "version": "1.0.0",                  // 语义化版本，见第 3 节纪律
  "dimensions": [ {
      "dim_id": "rand_seq",            // 维度 id，全局唯一
      "name": "随机序列生成",
      "levels": [ {
          "level_id": "low",           // 等级 id，维度内唯一
          "score": 1.0,                // 数值分；该维度满分 = 各 level score 的最大值
          "definition": "……≥10字符的判定定义……"  // 写给判定者看的操作化定义
      } ],
      "weight": 0.2                    // >0；全部维度之和必须 = 1.0（容差 1e-6）
  } ],
  "grade_rules": [ {
      "grade": "low",                  // 风险等级名（如 low / some_concerns / high）
      "min_score": 0.8, "max_score": 1.0,   // [min, max)，最顶层右端点闭合
      "implication": "该等级如何影响结论权重"     // 必填，见 grade_rules.md
  } ]
}
```

- 等级区间必须**无缝覆盖 [0,1] 且不重叠**：本引擎按 `[min_score, max_score)`
  解释，最顶层区间右端点闭合（0.8 落入 [0.8,1.0]）。
- `definition` 必须可操作：写清"看到什么证据判哪一级"，而非"质量较高"。
- 评分公式（确定性，脚本重算）：
  `total = Σ weight × (level.score / 该维度满分)`，满分即该维度 levels 中最大 score。

## 3. 版本化纪律

1. 量表一旦用于某次综述的评价，**冻结**该版本文件（写入 result.json
   可复核制品），不得在判定中途修改。
2. 任何修改（增删维度、调权重、改等级阈值、改 definition 措辞）→
   升 `version` 并记入 result.json 的 `change_records`（旧版本号 → 新版本号、
   修改原因、是否需重做已完成的判定）。
3. 改 `definition` 或 level 分数 → 所有受影响维度的判定必须重做；
   只改措辞澄清（不改语义）→ 至少重跑 `appraise.py` 复核。
4. 不同研究类型混入同一综述时，**每类各配一份量表**（如 RCT 用 rob2 思路、
   观察性用 robins-i 思路），record 标注所用 scale_id，不要强行共用。

## 4. 常见失败模式（本引擎要治理的）

- "质量较高"一句话带过 → 强制：每研究 × 每维度一条判定，且带
  `basis_location` + verbatim `basis_quote`（A1/A2 硬校验）。
- 量表藏在脑子里 → 量表必须是可 diff、可复跑的 JSON 文件，先过
  `rubric_check.py`（R1–R4）再开始判定。
- 等级与结论脱钩 → `grade_rules[].implication` 必填，且敏感性分析
  （sensitivity.py）显式重算剔除高等级后的结论支撑。
