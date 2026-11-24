# 三态交付一致性契约

## 三种形态，一个来源

| 形态 | 文件 | 受众 |
|-|-|-|
| 机器态 | `result.json` | 程序与评分 |
| 人读态 | `atlas/report.html`、`review_report.md` | 评审与作者 |
| 图形态 | `atlas/pages/*.svg`（增强时含 PDF/PNG） | 快速定位复核 |

三态必须**同源生成**：人读态与图形态由脚本从机器态渲染，禁止手工改写任何一态的内容字段（quote、verdict、severity、locator）。发现内容错误时改 result.json 并**重渲染**，不允许在 HTML/SVG 里打补丁。

## 渲染门禁语义

- `build_atlas.py` 退出码 1 的含义：存在 quote 回查失败的证据卡。这**不是渲染失败**，是证据断裂警报；卡片照出但带 VERIFICATION FAILED 徽标。修复路径只有两条：从页文本重取真实 quote，或将该条降级待复核。
- `atlas_manifest.json` 记录输入文件 SHA-256：复核者重新计算 result.json 与 pages.jsonl 的哈希即可确认图谱与数据同源，未遭事后修补。
- `page_maps.py` 的高亮失败（quote 跨行折叠后仍定位不到）不算证据断裂（quote 已在 build_atlas 逐字验证），但必须在 maps_manifest.json 记 `highlight=false`，不得静默出一张无高亮图。

## 复核者十分钟流程（设计目标）

1. 打开 `atlas/report.html` 看执行摘要与覆盖状态表；
2. 点任意证据卡，核对 quote 与页图 SVG 的高亮行；
3. 对存疑条目按 recheck 字段的命令/来源复核；
4. 用 manifest 哈希确认图谱未被事后改动。
