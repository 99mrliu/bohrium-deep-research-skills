# 渲染验证标准

## 为什么必须真实渲染

pptx 结构合法 ≠ 投出来正常。字体替换、文本溢出、布局越界只有渲染成像素才能
发现。评测契约要求可编辑产物配真实渲染的 PDF/PNG 预览；**未渲染却声称渲染通过
是禁止行为**。

## 证据链

```
soffice --headless -env:UserInstallation=file:///tmp/lo-c \
    --convert-to pdf --outdir render/ presentation.pptx
pdftoppm -png -r 100 render/presentation.pdf render/slide
```

- 并发/重复运行必须给 LibreOffice 独立 profile（`-env:UserInstallation`），
  否则 profile 锁冲突导致假失败。
- 每张 PNG 记录：字节数、均值亮度、亮度标准差、sha256（亮度优先 PIL，
  缺失时 stdlib 解码 8-bit 非隔行 RGB/RGBA/灰度 PNG）。
- PDF 记录 sha256；previews 写进 result.json `export_artifact.previews`。

## 判别规则

| 度量 | 规则 | 含义 |
|---|---|---|
| 页数匹配 | PNG 数 == pptx 页数 | 渲染链完整；不匹配 exit 1 |
| 近空白页 | 均值亮度 > 248 且标准差 < 4 | 疑似内容没渲染出来（白页）；出现即 exit 1 |
| PNG 字节数 | 记录不判死 | 异常小（<几 KB）通常对应空白页，供人工复核 |
| 渲染 hash | 记录 sha256 | 确定性复核、跨机对比 |

## tool_missing 诚实语义

- 无 soffice 或无 pdftoppm：report 写 `rendered=false`、
  `tool_missing:["soffice"|"pdftoppm"]`，脚本**退出 0**（环境缺失不是内容错误），
  result.json 的 `export_artifact.rendered=false`、exceptions 记 `tool_missing`、
  相关 compliance check 的 actual 写 `"not_rendered"` 且 pass=false → status 至少
  为 partial。
- soffice 转换失败（非缺失）：退出 1，detail 带 stdout/stderr 摘要。
- 任何情况下不得把"没渲染"写成"渲染通过"。
