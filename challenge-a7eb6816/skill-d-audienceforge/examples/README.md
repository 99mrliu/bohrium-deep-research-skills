# examples/ — 合成示例（非正式案例结果）

**声明：本目录全部为合成示例，研究内容（某藻类固碳改造）系虚构，非正式案例结果，**
**仅用于验证脚本行为与退出码。**

## 文件

| 文件 | 说明 |
| --- | --- |
| glossary.tsv | 合成术语表（4 条：批准译法 / 首次展开 / 禁用同义词 / 英文译法约定） |
| draft_public_bad.md | 公众向差稿：未展开缩写 CCUS、LCA；行话密度超标；禁用同义词混用（三角藻、褐藻黄素、固碳效率）；批准术语首次出现未展开 |
| draft_public_good.md | 公众向修正规：缩写首次展开、行话密度达标、术语统一 |
| zh.md / en.md | 双语对：批准译法两稿对齐，出现次数比例 ≤ 3.0 |
| expected/ | 以下为真实运行输出，非手工编写 |

## 真实运行命令与结果（在本目录下执行）

```bash
# 1. 受众路由（public 画像 + 术语表注入）→ 退出码 0
python3 ../scripts/audience_route.py --audience public --glossary glossary.tsv \
  --out expected/adaptation_plan.json

# 2. 行话扫描：差稿 → 退出码 6（密度 9.453 > 上限 1.0；CCUS、LCA 未展开）
python3 ../scripts/jargon_scan.py --text draft_public_bad.md --audience public \
  --glossary glossary.tsv --out-json expected/jargon_report_bad.json \
  --out-md expected/jargon_report_bad.md

# 3. 行话扫描：好稿 → 退出码 0（密度 0.917 ≤ 1.0；缩写均已展开）
python3 ../scripts/jargon_scan.py --text draft_public_good.md --audience public \
  --glossary glossary.tsv --out-json expected/jargon_report_good.json \
  --out-md expected/jargon_report_good.md

# 4. 术语检查：差稿 → 退出码 7（3 处 inconsistent_term + 1 处 missing_expansion）
python3 ../scripts/glossary_check.py --glossary glossary.tsv --text draft_public_bad.md \
  --out-json expected/glossary_report_bad.json --out-md expected/glossary_report_bad.md

# 5. 术语检查：好稿 → 退出码 0
python3 ../scripts/glossary_check.py --glossary glossary.tsv --text draft_public_good.md \
  --out-json expected/glossary_report_good.json --out-md expected/glossary_report_good.md

# 6. 双语对齐 → 退出码 0（4 条术语两稿译法一致，比例均 ≤ 3.0）
python3 ../scripts/glossary_check.py --glossary glossary.tsv --pair zh.md en.md \
  --out-json expected/glossary_report_pair.json --out-md expected/glossary_report_pair.md

# 7. 异常路径：未知受众标签 → 退出码 2（stderr 列出可用标签）
python3 ../scripts/audience_route.py --audience investor
# 异常路径：--fallback 兜底 → 退出码 0，输出中 fallback=true 且带声明
python3 ../scripts/audience_route.py --audience investor --fallback --out /tmp/plan_fb.json
```

## 实测退出码汇总（2026-11-24 本机真实运行）

| 用例 | 退出码 | 关键检出 |
| --- | --- | --- |
| route public | 0 | adaptation_plan.json 含画像全量 + 执行清单 |
| route investor（无 --fallback） | 2 | stderr 列出 4 个可用标签 |
| route investor --fallback | 0 | fallback=true，declaration 声明保守画像 |
| jargon bad | 6 | 密度 9.453/百字 > 1.0；未展开缩写 CCUS（第 3 行）、LCA（第 5 行） |
| jargon good | 0 | 密度 0.917/百字；无未展开缩写 |
| glossary bad | 7 | 禁用同义词 三角藻/褐藻黄素/固碳效率；碳捕集利用与封存首次出现未展开 |
| glossary good | 0 | 无问题 |
| glossary pair zh/en | 0 | 中/英批准译法计数 2:1、2:3、1:1、1:1，比例均 ≤ 3.0 |

注：开发过程中 zh.md 标题曾含未展开的「三角褐指藻」，被 glossary_check 正确判为
missing_expansion（退出码 7）；改标题后双语对全部通过。该插曲验证了检查 (b) 的真实有效性。
