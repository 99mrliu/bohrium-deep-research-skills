# 工件契约与目检要点（delivery-studio）

## 交付工件清单

| 工件 | 形态 | 核验方式 |
|---|---|---|
| `result.json` | 合同交付物（机读） | check_delivery 校验 case_id/status/必需字段 |
| `notes.md` | 人读笔记 | 目检：目录可跳转、锚点内联、章节序同原文 |
| `preview.html` | 自包含预览 | 浏览器直接打开；无外部资源依赖 |
| `preview.png` | 卡片+章节地图一页摘要（可选） | matplotlib 可得时渲染；不可用时 preview 报告 unavailable |
| `notes.jsonl` | 复用索引（每行一条） | grep/diff 友好 |
| `manifest.json` | 输入/产物 sha256 | 复算可验证来源字节 |
| `change_records.md` | 修正留痕 | 人读 |
| `delivery-report.json` | 交付核验结论 | gaps 为空才可宣称 deliverable |

## 目检要点（Agent 自己也要做）

1. notes.md 通读一遍：不打开原文也能理解核心发现与其边界。
2. preview.html 打开检查：锚点是否高亮、对比表是否成形、打印是否掉样式。
3. preview.png（若生成）确认卡片字段无截断乱码；中文字体缺失时如实记录，不伪造预览。
4. manifest.json 的 inputs 必须包含真实论文文件哈希——这是“笔记对应哪份字节”的唯一证据。
5. check_delivery 的每个 gap 要么修复，要么写进 result.limits；不允许静默通过。

## 降级规则

- 工具缺失一律如实降级并在 result.uncertainty 记录；HTML 永远产出。
- 平台运行时若任务要求可编辑 Office/图表工件，还须用平台渲染器产出真实 PDF/PNG 预览；本 Skill 的 HTML/PNG 是笔记类交付的预览层。
