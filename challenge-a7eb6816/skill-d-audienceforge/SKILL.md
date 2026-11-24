---
name: audienceforge-terminology
description: >-
  当同一科研成果需要面向不同读者（公众科普、项目评审、跨学科研究者、投资人、双语出版等）改写，
  且需要控制解释深度与术语密度、规范缩写首次展开、锁定全文术语统一（同义词收敛、缩写首次展开、
  双语术语对齐）时使用。触发场景：把论文/项目材料改写给特定受众；检查稿件行话是否超标；
  检查缩写是否首次展开；按术语表收敛禁用同义词；核对中英双语稿批准译法是否一致。
---

# AudienceForge · 受众适配与术语一致性

## 重心与边界

**重心**：受众画像 → 解释深度/术语密度策略路由；行话与未展开缩写检测；可锁定术语表
（同义词收敛、缩写首次展开、双语术语对齐）。

**边界（不做什么）**：

- 不替你写文章：本技能只做「路由 + 检测 + 清单」，正文改写由模型完成，脚本不预生成答案。
- 不做事实核查、不做数据/图表核对、不做交付格式校验（那是其他技能的方向）。
- 内置行话表是通用小表，领域术语必须通过 `--glossary` 注入，否则结论有局限（须声明）。
- 密度口径是启发式（命中数/百字），不是语言学测量；阈值应按真实运行行为调整并记录。

## 运行契约

- 输入：`/input/case.json` 与 `/input/task.md`（只读，绝不修改）。
- 工作目录：`/app/work`（中间产物：adaptation_plan.json、jargon_report.*、glossary_report.*）。
- 最终产物：`/app/output/`，必须含 `result.json`。
- `result.json` 契约：必须包含 `case_id` 与 case 自带 `output_contract` 的全部字段；
  字段值来自本次真实运行的报告内容，**不预制答案**。
- **诚实 partial**：任一检查未达标（退出码 6/7）、受众标签未知走了 fallback、
  或术语表缺失只能做通用缩写检测时，`result.json` 中 `partial` 置 `true` 并在
  `notes` 写明原因与局限；不粉饰、不造假。
- 脚本仅用 Python 3 标准库，输出确定性（无时间戳、无随机数），只读输入文件。
- 退出码约定（非 0 即失败，分类见下表）：

| 脚本 | 0 | 非 0 |
| --- | --- | --- |
| audience_route.py | 成功（含 --fallback 声明式兜底） | 1=用法/IO 错误；2=未知受众标签 |
| jargon_scan.py | 达标 | 6=行话超标/缩写未展开；1=用法/IO 错误 |
| glossary_check.py | 全部通过 | 7=同义词/首次展开/双语对齐问题；1=用法/IO/格式错误 |

## 标准流程

以下命令可直接复制执行；`$SK` 代指技能安装目录（标准位置 `/skills/weekly-skill`），
带 fallback 定位：

```bash
SK=/skills/weekly-skill
if [ ! -f "$SK/scripts/audience_route.py" ]; then
  P=$(find / -maxdepth 6 -name audience_route.py 2>/dev/null | head -n 1)
  SK=$(dirname "$(dirname "$P")")
fi
mkdir -p /app/work /app/output

# 0. 读取案例输入，确定受众标签 AUDIENCE 与稿件路径 DRAFT（可能来自 case.json 指定的路径）
AUDIENCE=public            # 可选：public / grant_review / cross_discipline / bilingual_editor
DRAFT=/app/work/draft.md   # 待检查稿件

# 1. 受众路由：生成改写执行清单（画像全量 + 缩写处理 + 段落骨架 + 禁用表达）
python3 "$SK/scripts/audience_route.py" --audience "$AUDIENCE" \
  --glossary /app/work/glossary.tsv \
  --out /app/work/adaptation_plan.json
# 未知标签时上一条返回退出码 2；决定兜底策略后改用：
# python3 "$SK/scripts/audience_route.py" --audience "$AUDIENCE" --fallback --out /app/work/adaptation_plan.json

# 2. 行话密度与缩写展开检查（退出码 0=达标，6=超标/未展开）
python3 "$SK/scripts/jargon_scan.py" --text "$DRAFT" --audience "$AUDIENCE" \
  --glossary /app/work/glossary.tsv \
  --out-json /app/work/jargon_report.json --out-md /app/work/jargon_report.md

# 3. 术语一致性检查（退出码 0=通过，7=存在问题）
python3 "$SK/scripts/glossary_check.py" --glossary /app/work/glossary.tsv --text "$DRAFT" \
  --out-json /app/work/glossary_report.json --out-md /app/work/glossary_report.md

# 3b. 双语稿对齐（可选；比例阈值可调）
python3 "$SK/scripts/glossary_check.py" --glossary /app/work/glossary.tsv \
  --pair /app/work/zh.md /app/work/en.md --ratio-threshold 3.0 \
  --out-json /app/work/glossary_report_pair.json --out-md /app/work/glossary_report_pair.md

# 4. 汇总：把 1–3 的真实报告内容填入 /app/output/result.json
#    （case_id + output_contract 全部字段；有未达标项则 partial=true 并写 notes）
```

## 异常处理

- **未知受众标签**：`audience_route.py` 退出码 2，stderr 列出全部可用标签。
  处理：优先从 case.json / task.md 重新推断标签；确实无法归类时用 `--fallback`
  采用保守画像（密度上限 0.8/百字、全部缩写首次展开、默认面向非专业读者），
  并在 adaptation_plan.json 的 `declaration` 与 result.json 的 `notes` 中显式声明。
- **术语表缺失**：`--glossary` 不可用时，jargon_scan 仅用内置通用行话表 + 通用缩写检测，
  glossary_check 无法运行；此时 result.json 必须 `partial=true` 并标注
  「未加载领域术语表，同义词收敛与双语对齐未执行」。
- **稿件缺失/不可读**：脚本退出码 1，不生成报告；result.json 记 partial 并说明。
- **双语次数比例超标**：先检查是否漏译或偷换译法；确属行文需要才调高
  `--ratio-threshold`，并在 notes 中记录调整理由。

## 最小合成示例

`examples/` 内置虚构的「某藻类固碳研究」合成示例（非正式案例结果）：
术语表 `glossary.tsv`、公众向差稿 `draft_public_bad.md`（未展开缩写 CCUS/LCA、
行话密度 9.453/百字超标、3 处禁用同义词、1 处批准术语未首次展开）、
修正规 `draft_public_good.md`（全部通过）、双语对 `zh.md` / `en.md`（对齐通过）。
真实运行命令与退出码记录在 `examples/README.md`，真实输出保存在 `examples/expected/`。

## 局限

- 行话表为小型通用表，覆盖有限；不接 glossary 时检测会漏领域术语。
- 缩写识别只覆盖「全大写 ≥2 字符」形态；混合大小写缩写（如 RuBisCO）靠行话表命中。
- 「首次展开」判定依赖紧邻括号模式（全称（ABBR）/ full name (ABBR)），
  其他展开写法（破折号、同位语）会被误报为未展开。
- 密度按去空白字符数归一，中英混排时英文按字母计数，口径偏严。
- 双语对齐只核对批准译法出现次数比例，不做语义等值判断。
