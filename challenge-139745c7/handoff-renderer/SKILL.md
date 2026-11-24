---
name: handoff-renderer
description: 下游交付与渲染工程方向。把检索/整理结果做成"可交接"的交付包：manifest 保证每个输入文件恰好映射到一条交付记录（完整性自检，缺漏即报），INDEX.md 与自包含 index.html 供人阅读，metadata.csv 与 tree.md 构成可检索知识结构，库结构/版本关系渲染为 SVG 图，并用纯 Python（zlib+位图字体，无第三方依赖）生成真实 PNG 预览供目检；所有可编辑产物都带渲染预览，交付前跑交接自检清单。当任务强调"输出可检索、可交接的清单或知识结构、可编辑产物需带真实预览"时使用；输入为 /input/case.json + task.md + 文档库。
---

# handoff-renderer：交付工程与渲染预览

## 重心

检索做对只值一半分，**交接不出去等于没做**。本技能的重心在下游：
交付包的完整性（每个输入文件恰好出现一次）、人读与机读双格式、
可编辑产物（SVG/HTML/CSV）全部带**真实渲染的 PNG 预览**，
以及一张不过自检就不准交付的检查清单。

## 运行契约（必须遵守）

1. 先读 `/input/case.json` 与 `/input/task.md`：记录 `case_id`，照抄
   `output_contract` 全部字段；库路径与提问以实际键名为准，找不到就
   `ls -R /input` 盘点。**不凭文件名猜内容。**
2. **立刻**写 `/app/output/result.json` 骨架（case_id + 全字段占位 +
   `"status":"partial"`），随后逐步填充。
3. 中间产物 `/app/work`，交付 `/app/output`；`$S` 为技能安装目录
   （通常 `/skills/weekly-skill`）。Python ≥3.9 标准库，**零第三方依赖**；
   PNG 由自带位图字体渲染，不依赖 PIL/matplotlib。

## 执行步骤

```bash
S=/skills/weekly-skill
mkdir -p /app/work /app/output
# 1. 盘点 + 回答提问（回答体本身从简，重心在交付）
python3 "$S/scripts/handoff_scan.py" /input/case.json /app/work
# 2. 组装交付包：manifest.json（完整性自检）、INDEX.md、index.html、
#    metadata.csv、tree.md、structure.svg → 全部写入 /app/output
python3 "$S/scripts/handoff_build.py" /input/case.json /app/work /app/output
# 3. 为可编辑产物渲染真实 PNG 预览（structure.svg→preview，INDEX→preview）
python3 "$S/scripts/handoff_preview.py" /app/output
# 4. 交接自检 + 组装 result.json（output_contract 全字段）
python3 "$S/scripts/handoff_result.py" /input/case.json /app/work /app/output/result.json
```

第 4 步自检不过（有输入文件未映射/预览缺失/契约缺字段）时退出码非 0：
修复后重跑，不得带病交付。

## 交付包结构（/app/output）

```
result.json          契约结果（case_id + output_contract 全字段）
manifest.json        输入→交付映射；completeness 自检结果
INDEX.md             人读总览（库结构、提问与回答、异常清单）
index.html           自包含 HTML（无外部资源，可直接浏览器打开）
metadata.csv         全文件元数据（路径,类型,大小,mtime,版本标记,sha16）
tree.md              目录树 + 版本族
structure.svg        库结构/版本关系图（可编辑矢量）
preview_structure.png  structure.svg 内容的真实 PNG 预览
preview_index.png      INDEX.md 首页内容的真实 PNG 预览
answers.json         提问回答（机读）
```

## 交接自检清单（handoff_result.py 执行，详见 references/output-contract.md）

- [ ] 库中每个输入文件在 manifest.json 恰好出现一次；
- [ ] 每个可编辑产物（svg/html/md/csv）存在对应 PNG 预览或在
      `preview_exempt` 中说明理由；
- [ ] result.json 含 case_id 与 output_contract 全部字段；
- [ ] 未能回答的提问以 no_match 如实列出，无虚构回答。

## 异常处理

| 情况 | 处置 |
|-|-|
| 文件读失败 | manifest 记 `unreadable`，不静默漏项（完整性仍覆盖它） |
| 提问无命中 | answers.json 记 no_match + 检索词 |
| CJK 文件名进 PNG | 预览图以 F01/F02 编号标注，图例在 INDEX.md 对照 |
| 自检失败 | result.json status=partial + 失败项清单，退出码非 0 |

## 最小示例

`examples/` 为**合成示例**（4 个文件含两版本），运行
`python3 run_example.py`，预期见 `examples/README.md`。

## 限制

- 回答引擎为关键词级，语义深挖非本技能重心。
- PNG 预览为位图字体渲染的示意图，非像素级版式还原；其作用是
  证明产物可被真实渲染并供快速目检。
- 不做开放网络检索。
