# placement-surgeon（论断级引用位置外科）

**核心立场**：引用管理的质量首先取决于"挂得对"——每个引用标记必须贴着
它所支撑的命题。本技能审计并修复稿件中引用标记的**位置**质量：段末漂
移、错挂邻句、图表注误挂、未覆盖论断、超距覆盖、标记先于命题
（P1–P6），全程可回溯、零伪造。

## 什么时候用 / 不用

- 用：核查引用是否插到真正需要来源支撑的那句话；把飘在段末、图注里或
  跨越多句的标记归位；补挂文献表中已存在但未被引用的条目；修复后复审。
- 不用：纯著录格式转换（GB/T 7714 ↔ APA）、文献内容真伪核查、无稿配
  文献、PDF/DOCX 版面级直接编辑（只处理文本层）。

## 五个阶段

0. 盘点与契约骨架（读 /input，写 result.json 骨架）
1. 论断切分与标记清点 —— `scripts/claim_scan.py`
2. 位置审计（P1–P6）—— `scripts/placement_audit.py`，有违规退出码 1
3. 修复计划与原子施加 —— `scripts/placement_plan.py`，校验失败不写盘
4. 全稿复读与收口（重跑审计清零、diff 确认正文零改动、回填 result.json）

## 快速开始（本地复现）

```
cd skill/
python3 scripts/claim_scan.py --manuscript examples/input/manuscript.txt --out work/scan
python3 scripts/placement_audit.py --sentences work/scan/sentences.jsonl \
    --markers work/scan/markers.jsonl --out work/audit        # 预期退出码 1，4 条违规
python3 scripts/placement_plan.py --manuscript examples/input/manuscript.txt \
    --plan examples/input/plan.json --out work/apply           # 预期退出码 0
# 复审应清零，详见 examples/minimal_example.md
```

评测环境中脚本路径为 `python3 /skills/weekly-skill/scripts/xxx.py`。

## 特性

- 纯 Python 标准库、确定性、无网络；单文件 ≤500KB。
- 施加原子性：锚点/marker 原文/重叠校验任一失败，整体不写任何输出。
- 铁律：无已核验来源的缺口只标 `[缺来源]`，绝不虚构引用。

详见 `SKILL.md`、`references/placement_rules.md`、
`references/placement_plan_format.md`。`examples/` 全部为虚构合成数据。
