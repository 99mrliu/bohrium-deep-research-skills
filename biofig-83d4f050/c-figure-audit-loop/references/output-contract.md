# result.json 输出契约

**必须写 `/app/output/result.json`**，含以下必需字段（模板见 `assets/result.template.json`，
组装与校验用 `scripts/build_result.py`）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `case_id` | string | 来自 `/input/case.json` 的 case 标识 |
| `status` | string | `success` \| `partial` \| `failed`，**必须诚实**：有未解决违例/exceptions 时不得为 success（build_result.py 会自动降级） |
| `editable_source` | string[] | 可编辑源文件路径列表（SVG、claims.json、绘图脚本等） |
| `export_artifact` | string[] | 导出产物路径列表（PNG/PDF） |
| `content_map` | object | 图面元素 → 来源定位，键建议用 `entity:<id>` / `edge:<id>` / `encoding:<channel>:<field>` / `legend:<item>`，值为页码/图号/句子/数据文件行列定位 |
| `compliance_checks` | array | 每项 `{check, result, note?}`；审计结论逐条列出，**skipped 必须如实写 skipped** |
| `exceptions` | string[] | 所有未解决问题：残留违例、跳过的检查、证据不足标 uncertain 的边、工具缺失等 |

## 各 case 类型要点

1. **机制图（论文 → 图）**：content_map 的每个实体/边都要能回溯到论文页码/图/句子；
   encodings 若来自论文数据须给表/图号。
2. **数据 → 图表**：encoding 数值须给出数据文件+列/行定位；像素审计的 color_checks
   区域从 SVG 元素 bbox 自动映射，或在 claims 中以画布分数坐标显式给出。
3. **保源编辑**：claims.json 必须含 `edit_expectations{changed_elements, unchanged_sample}`；
   audit_edit_diff 的全量差异表路径写入 compliance_checks；计划外改动必须进 exceptions。

## 预算策略（~64 请求 / 900s）

先写**部分 result.json**（status=partial，骨架+已完成的检查），再迭代改进：
claims → 绘图 → 审计 → 修复 → 更新 result.json。任何时刻中断都留有诚实快照。
