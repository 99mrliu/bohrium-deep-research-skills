# identity-merge-court

方向 D（文献去重与身份归并）的竞赛 skill bundle。立场：**去重不是字符串相似度问题，
而是身份判定问题**——候选挖掘与裁决分离，裁决保守、逐案给理由、可回退。

## 组成

```
SKILL.md                        技能说明（运行时契约、五阶段流程、异常处理表）
scripts/dedup_candidates.py     候选挖掘：五类信号 + 证据分级 + 逐字段冲突表（不做合并）
scripts/merge_adjudicate.py     裁决校验与施加：M1–M5 门检，违规退出码 1 且原子不写产物
scripts/redirect_check.py       引用重定向复核：检出仍引用被并标签的残留（残留即退出码 1）
references/adjudication_rules.md  M1–M5 精确定义、正反例、证据分级、human_queue 升级路径、谱系格式
references/record_formats.md      records/candidates/decisions/merged/redirect_map 字段级格式
examples/                         全虚构合成示例 + 三个脚本的真实运行产物
```

## 三步走（本地复现，仓库根目录）

```bash
python3 scripts/dedup_candidates.py --records examples/input/records.jsonl --out examples/output
python3 scripts/merge_adjudicate.py --candidates examples/output/candidates.json \
  --records examples/input/records.jsonl --decisions examples/input/decisions.json --out examples/output
python3 scripts/redirect_check.py --manuscript examples/input/manuscript.txt \
  --redirect_map examples/output/redirect_map.json --out examples/output   # 预期退出码 1（演示残留检出）
```

竞赛环境中脚本路径为 `/skills/weekly-skill/scripts/`，中间产物写 `/app/work`，最终产物与
`result.json`（逐字 case_id + output_contract 全部原始字段，先骨架后回填）写 `/app/output`。

## 关键性质

- 三态裁决：merge / keep_separate / human_queue；只有 merge 需要过 M1–M5 门检。
- M2：同规范化 DOI 但书目坐标冲突 → 禁止自动并；M3：仅题名相似 → 禁止并；
  M4：预印本并入正式版且留谱系；M5：同姓同年不同文献显式保护。
- 确定性、仅 Python 标准库、无网络；同一输入必得同一输出。
- examples/ 全为虚构合成数据（DOI/arXiv/PMID/人名/刊名均编造），仅供演示。
