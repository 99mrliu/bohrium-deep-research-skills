# dual-track-topic-query-strategist

技术主题检索式构造与专利/非专利文献双轨筛选 Skill（Bohrium Playground challenge-ad3e9357，方向 C）。

## 一句话

把"技术主题检索"做成可解释、可复跑的检索式工程：概念块分解（每词带 intent）→ 分面组合 →
专利/NPL 双轨不同逻辑执行 → PRISMA 筛选留痕 + 排序依据 + 遗漏说明 → 诚实填充 result.json。

## 文件结构

```
skill/
├── SKILL.md                      # 技能定义（触发条件、运行时契约、调用序列、案例路由、异常处理表）
├── README.md                     # 本文件
├── scripts/
│   ├── build_query.py            # 概念块检索式构造器（库+CLI），R1-R9 结构校验
│   ├── search_corpus.py          # 检索式执行器：语料发现、双轨分类、族/DOI 去重、定位+词项明细
│   ├── screen_rank.py            # PRISMA 筛选（重算比对）+ 文档化特征排序 + 遗漏说明
│   ├── scaffold_result.py        # result.json 骨架，镜像 output_contract，诚实 status
│   └── selfcheck.py              # 合成夹具端到端自测（正例全链 + 负例拒绝），exit 0/1
├── rules/
│   ├── topic_query_construction.md   # 概念块方法、intent 纪律、查全/查准迭代协议
│   ├── dual_track_logic.md           # 专利 vs NPL 检索逻辑差异、kind code、OCR 合并处理
│   └── screening_protocol.md         # 纳排理由代码表、PRISMA 口径、排序特征定义
├── templates/
│   ├── result_fields.md          # result.json 字段口径
│   └── query_log.md              # 检索式版本迭代留痕模板
└── examples/
    ├── example_walkthrough.md    # 端到端示例解读（虚构数据，illustrative only）
    └── fixtures/                 # 合成夹具（全部虚构，标注 illustrative）
```

## 快速开始

```bash
# 自测（应输出 SELF-CHECK PASSED）
python3 scripts/selfcheck.py

# 实际任务（Harbor 契约）：见 SKILL.md "调用方式"一节的命令序列
```

## 方法要点

1. **检索式是工程产物，不是关键词堆砌**：主题拆成 2-5 个概念块，块内 OR、块间 AND；
   每个词项必须回答"为什么这个词能识别相关文献"（intent），否则 R6 拒绝。
2. **双轨不同逻辑**：专利轨道分类号优先、同族去重、kind code 感知；
   NPL 轨道关键词优先、DOI/标题规范化去重。无法判定的记录如实列出，不强行归轨。
3. **筛选留痕**：查全（宽式）→ 查准（阈值）两阶段；排除必给 E1-E7 理由码，
   纳入必给 I1-I4 依据；PRISMA 计数由脚本重算，自报不一致即失败。
4. **排序可解释**：score = 块覆盖(≤40) + 字段强度(≤30) + 分类号重合(≤15) + 年份接近(≤15)，
   每条候选输出分解。
5. **诚实优先**：零命中、无法判定、法律状态未核验、外部库未检索——全部写入
   status/omissions/uncertainty，绝不编造。

## 约束

- 全部脚本仅依赖 Python 标准库；全部文件 UTF-8 文本。
- examples/fixtures/ 中数据全部虚构，仅用于 selfcheck 与演示，不构成任何真实案例答案。
