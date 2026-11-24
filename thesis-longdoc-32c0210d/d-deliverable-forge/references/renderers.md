# 渲染器探测顺序、失败降级与预览命名约定

`scripts/render_preview.py` 的唯一职责：把改后章节 markdown 渲染成**真实**的
PDF/PNG 预览；渲染不出来就如实记录，绝不伪造。

## 1. 探测顺序（先找到先用，每次尝试带 `--timeout`，默认 120s）

| 序 | 渲染器 | 探测方式 | 渲染管线 |
|-|-|-|-|
| 1 | `pandoc` | `PATH` 查找 | `pandoc combined.md -o edited_chapters.pdf --standalone`（pandoc 自己再调 PDF 引擎，失败属正常降级） |
| 2 | `xelatex` | `PATH` 查找 | 内置 stdlib markdown→LaTeX 简转（`ctexart`，失败再试 `article`），`xelatex -interaction=nonstopmode -halt-on-error` |
| 3 | `soffice` | `PATH` 查找；macOS 额外探测 `/Applications/LibreOffice.app/Contents/MacOS/soffice` 等常见路径 | 内置 stdlib markdown→HTML 简转，`soffice --headless --norestore -env:UserInstallation=file://<临时profile> --convert-to pdf` |

- 每个渲染器只尝试一次；成功即停止（`winner`），失败细节（rc、stderr 尾部、
  超时）全部写入 render_report.json 的 `attempts`。
- soffice 使用独立临时 UserInstallation，避免与本机正在运行的 LibreOffice 冲突。
- 内置的 md→HTML / md→LaTeX 转换器是**预览级**（标题、段落、列表、代码块），
  不是出版排版；预览的用途是让评审确认"稿件真实存在且内容可读"。

## 2. PNG 首页图

PDF 生成后调用 `pdftoppm -png -f 1 -l 1 -r 110` 取首页。
`pdftoppm` 缺失：PDF 照常交付，PNG 缺失记入 limits，不算渲染失败。

## 3. 命名约定

```
<out-dir>/edited_chapters.pdf    # 全部改后章节合并渲染（按文件名字典序拼接）
<out-dir>/edited_chapters.png    # PDF 首页
```

result.json `artifacts` 中以相对输出目录的路径登记：
`preview/edited_chapters.pdf`、`preview/edited_chapters.png`。
**只登记真实生成且非空的文件**；终检 C4 对 `preview/` 下的 artifact 额外要求
size > 0（空文件按伪造处理，直接判失败）。

## 4. 失败降级路径

| 情形 | 行为 | 退出码 |
|-|-|-|
| 三个渲染器都找不到/都失败 | result.json `limits` 追加 `renderer_unavailable: ...`，artifacts 不列任何预览；render_report.json 记录全部 attempts | 1 |
| 章节目录无 `*.md` | limits 记录 `render skipped: no chapter markdown found ...` | 1 |
| `FORGE_NO_RENDER=1` | 完全跳过（确定性测试分支），limits 记录 `render skipped via FORGE_NO_RENDER=1 ...`；不探测渲染器，输出确定 | 0 |
| result.json 不可读 | 不改动任何文件，报错 | 2 |

退出码为 1 时交付**不中断**：result.json 已被如实更新，继续跑
`verify_delivery.py` 即可（C4 只核验被声明的预览）。
