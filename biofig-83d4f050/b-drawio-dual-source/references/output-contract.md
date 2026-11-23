# result.json 输出契约与诚实规则

每个 case 必须在 `/app/output/result.json` 写出（建议用
`scripts/build_result.py` 组装，它会校验必填字段与产物存在性）。

## 必填字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `case_id` | string | 来自 /input/case.json |
| `status` | `success` \| `partial` \| `failed` | 见下方诚实规则 |
| `editable_source` | string[] | 第一可编辑源，至少含 `figure.drawio`；通常同时列 `figure.svg` |
| `export_artifact` | string[] | 导出产物（PNG/PDF；缺 matplotlib 时可为空并记 partial） |
| `content_map` | object | 元素 → 来源定位映射 |
| `compliance_checks` | object[] | 来自 verify_exports.py 的 `{name,status,detail}` |
| `exceptions` | object[] 或 string[] | 异常与限制；success 时可为空数组 |

## content_map 定位写法

- 论文：`"entity:egfr": "paper.pdf p.4 Fig.2 panel B"`
- 段落证据：`"edge:e3": "paper.pdf p.5 ¶2 'AKT phosphorylates MYC at Ser…'"`
- 数据列：`"entity:akt#fill": "data.csv:log2FC row AKT = 1.80"`
- 图表标记：`"chart:expr#bar:2": "data.csv row 4: log2FC = -1.40"`
- 每个实体、每条边、每种视觉编码都要有一条；没有来源的元素**不允许出现在图上**。

## 诚实规则

1. `partial` 必须在 `exceptions` 里点名限制（例："matplotlib 缺失，无 PNG/PDF，
   仅交付 drawio+SVG"；"edge e5 方向仅见于综述表述，evidence=uncertain"）。
2. `failed` 必须说明失败点与已完成的部分（result.json 仍要写）。
3. 不允许编造数据值、文献定位或校验结果；compliance_checks 必须来自
   verify_exports.py 的真实输出（fail 也照实写）。
4. 工具缺失用 `shutil.which` 探测后如实降级，不得假装成功。
5. 示例/合成内容必须在 note 字段标注 synthetic（见 assets/example-geometry.json）。

## 时间预算（约 64 次模型请求 / 900 s）

第一套完整产物（drawio + SVG + PNG/PDF + verify）一旦生成，**立即**写一版
result.json（哪怕是 partial），之后再迭代改进并覆盖；任何时刻中断都留有可评估结果。
