# blocks.jsonl 输入 Schema

上游 PDF 解析步骤的产出：每行一个 JSON 对象（JSON Lines，UTF-8 编码）。

## 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | 是 | 块唯一标识，非空；全文不得重复 |
| `page` | int ≥ 1 | 是 | 1-based 页码 |
| `column` | int ≥ 0 | 否 | 栏序号（0-based）；缺省按 0 处理 |
| `bbox` | `[x0, y0, x1, y1]` 或 `null` | 是（可为 null） | 块外接框，**PDF points**（1/72 英寸），原点左上，y 向下；要求 x0≤x1 且 y0≤y1；几何未知时显式给 `null`（渲染照常，QC 记 warning） |
| `kind` | enum | 是 | `heading` \| `body` \| `caption` \| `equation` \| `reference` \| `header` \| `footer` \| `unresolved` |
| `text` | string 或 `null` | 是（可为 null） | 块文本；仅 `kind=unresolved` 允许为 null |
| `reason` | string | 条件 | `unresolved` 且 `text=null` 时应给出无法解析的原因 |

## 类型语义

- `header` / `footer`：页面功能性文字（刊名、页码等）。渲染时移入附录并置灰，**不丢弃**。
- `unresolved`：上游无法恢复文本的区域（矢量图、旋转条带、扫描噪声等）。必须保留，
  渲染时高亮并展示 `reason`。
- `equation`：公式文本（线性表示即可，不要求 TeX）。渲染为等宽字体。
- `caption`：图/表题。渲染为斜体。

## 校验规则（anchor_map.py 实现）

- 逐行 JSON 解析失败、`id` 缺失/重复、`page` 非正整数、`bbox` 形状或端点顺序错误、
  `kind` 越出枚举、非 unresolved 块 `text=null` —— 均记为 schema error；
  任一 error 使 `schema_valid=false` 且进程以退出码 3 结束，逐行原因写入
  `anchor_map.json.schema_errors` 与 stderr。
- 文件不是合法 UTF-8：拒绝处理，退出码 3。
- `column` 缺失：容忍，按 0。

## 示例行

```json
{"id": "b0001", "page": 1, "column": 0, "bbox": [72.0, 70.0, 523.0, 96.0], "kind": "heading", "text": "1. Introduction"}
{"id": "b0002", "page": 1, "column": 0, "bbox": null, "kind": "body", "text": "几何信息缺失但文本完整的段落。"}
{"id": "b0003", "page": 2, "column": 1, "bbox": [330.0, 150.0, 500.0, 172.0], "kind": "equation", "text": "E = m c^2"}
{"id": "b0004", "page": 2, "column": 0, "bbox": [72.0, 210.0, 285.0, 250.0], "kind": "unresolved", "text": null, "reason": "vector figure region; no recoverable text"}
{"id": "b0005", "page": 2, "column": 0, "bbox": [72.0, 760.0, 523.0, 774.0], "kind": "footer", "text": "— 2 —"}
```

## 锚点分配

校验通过后，每页内按输入顺序编号：`p{page}-b{seq}`（seq 从 1 开始）。例如第 1 页
第 6 个块 → `p1-b6`。锚点写入 `anchor_map.json`，并作为两份交付物中对账的唯一键。
