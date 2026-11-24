# deck-spec 参考：deck_spec.json 模式（minipptx.py build 的输入）

`minipptx.py` 是 python-pptx 缺席时的真实兜底：从一份 JSON 规格构建合法、可编辑、
带讲稿备注的 .pptx（zipfile + 手写 OOXML，零第三方依赖）。

## 顶层结构

```json
{
  "deck_title": "整个 deck 的标题（写入 docProps，可省，缺省取首页 title）",
  "slide_size": {"cx": 9144000, "cy": 6858000},
  "slides": [ /* 至少 1 页，见下 */ ]
}
```

- `slide_size` 可省：默认 9144000 × 6858000 EMU（10in × 7.5in，4:3）。
  16:9 用 `{"cx": 9144000, "cy": 5143500}`。单位是 EMU（914400 = 1 英寸）。

## slides[i]

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | 是 | 页标题，渲染在页首标题文本框（32pt 粗体深蓝） |
| `bullets` | string[] | 否 | 正文项目符号，每条一个 `•` 段落（18pt）；无图时占整宽，有图时占左半栏 |
| `notes` | string | 否 | 讲稿备注，写入该页 notes slide；`\n` 分段。每页都会生成 notesSlide 部件 |
| `image` | object | 否 | `{"path": "相对/绝对路径.png", "caption": "图题"}`；仅支持 PNG |

## 规则与行为

- **image.path 解析**：绝对路径直接用；相对路径**相对 deck_spec.json 所在目录**。
  PNG 尺寸从文件头 IHDR 读取，插图放右半栏并保持纵横比（过高时按可用高度收缩）。
  同一 PNG 被多页引用只嵌入一次。非 PNG / 文件缺失 → exit 2。
- **文本转义**：XML 特殊字符由写出器转义，spec 里写原始文本即可。
- **结构校验**（build 时）：`slides` 非空、每页 `title` 非空、`bullets` 为字符串数组、
  `notes` 为字符串、`image.path` 为字符串、页面尺寸合理；违例 → exit 1 并指明 slides[i]。
- **验证产物**：build 之后应立刻 `minipptx.py verify deck.pptx`——重开 zip、逐部件校验
  XML well-formed、核对 slide 数与 presentation.xml 声明一致、每页 notesSlide 存在；
  全过 exit 0，违例逐条打印 `V: detail` 并 exit 1。

## 能力边界（如实声明）

minipptx 产出的是**最小合法** pptx：单一空白版式、固定配色（标题深蓝 #1F497D）、
文本框 + 项目符号 + PNG 插图 + 备注。它**不**支持：真实模板母版复刻、表格、
SmartArt、动画、多栏自由布局。契约提供模板 pptx 且 python-pptx 可用时，永远优先
`Presentation(template_path)`；minipptx 是无模板/无库环境下保证"可编辑件真实存在"
的底线。案例若要求严格模板合规而环境两者皆缺，如实交付 partial 并写明限制。
