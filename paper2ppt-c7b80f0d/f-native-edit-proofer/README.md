# ppt-native-edit-proofer

把论文/PDF 科研材料组织成**原生可编辑**的学术汇报 PPT，并用机器门禁证明可编辑性
（真文本、真表格、主题字体继承、字号合规、无占位符残留、round-trip 重开、真实渲染
度量）。本仓库为 Bohrium Playground 挑战 ppt-c7b80f0d 的 Skill bundle（方向 C）。

## 依赖与版本

- Python ≥ 3.9（开发验证用 3.12）
- 可选依赖（全部软导入，缺失时降级或诚实报错，不崩溃）：
  - `python-pptx` ≥ 1.0（构建/门禁/重开必需；缺失时 build_native 退出 2 诚实失败）
  - `matplotlib`（仅 examples 生成合成输入用）
  - `pymupdf` / `pypdf`（PDF 文本提取降级链；另优先尝试系统 `pdftotext`）
  - `Pillow`（图片解码与 PNG 亮度度量加速；缺失走 stdlib 路径）
- 渲染链：`soffice`（LibreOffice）+ `pdftoppm`（poppler）。缺失时
  render_diff 写 `rendered=false` + `tool_missing`，退出码仍为 0。
- 无第三方依赖安装即不可用的网络服务；全部离线运行。

## 安装

```bash
pip install python-pptx matplotlib pymupdf pypdf pillow   # 可选依赖
# LibreOffice 与 poppler 按平台安装（macOS: brew install --cask libreoffice; brew install poppler）
```

## 调用步骤

```bash
# 0. 生成合成输入（演示用；平台运行时改为读 /input 真实材料）
python3 examples/make_synthetic_case.py --out-dir runs/c/input
python3 examples/make_deck_json.py --paper runs/c/input/paper.pdf \
    --data runs/c/input/data.csv --fig-dir runs/c/work/figs --out runs/c/work/deck.json

# 1-7. 主流程
python3 scripts/font_probe.py --report runs/c/work/font_report.json
python3 scripts/evidence_scan.py --paper runs/c/input/paper.pdf \
    --deck runs/c/work/deck.json --report runs/c/work/evidence_scan.json
python3 scripts/build_native.py runs/c/work/deck.json \
    --template runs/c/input/target-template.pptx --fig-dir runs/c/work/figs \
    --fonts runs/c/work/font_report.json \
    --out runs/c/output/presentation.pptx --report runs/c/work/build_report.json
python3 scripts/edit_lint.py runs/c/output/presentation.pptx \
    --report runs/c/work/editability_report.json        # exit 1 = 有 error
python3 scripts/roundtrip_check.py runs/c/output/presentation.pptx \
    --report runs/c/work/roundtrip_report.json --expect runs/c/work/build_report.json
python3 scripts/render_diff.py runs/c/output/presentation.pptx \
    --out-dir runs/c/output/render --report runs/c/work/render_report.json \
    --profile /tmp/lo-c
python3 scripts/make_result.py --case runs/c/input/case.json \
    --deck runs/c/work/deck.json --work-dir runs/c/work \
    --output-dir runs/c/output --out runs/c/output/result.json
```

每个脚本 `--help` 可用；同输入同输出（确定性）；幂等可重跑。

## 退出码约定

| 脚本 | 0 | 非 0 |
|---|---|---|
| font_probe | 完成（unknown 也返回 0） | — |
| evidence_scan | 全部 quote 逐字命中 | 1=有 miss；2=无可用 PDF 提取器 |
| build_native | 构建成功 | 2=python-pptx 缺失或输入错误 |
| edit_lint | 无 error | 1=有 error；2=pptx 不可读/缺依赖 |
| roundtrip_check | 全部校验通过 | 1=校验失败；2=python-pptx 缺失 |
| render_diff | 渲染且度量通过，或诚实 tool_missing | 1=渲染失败/近空白页/页数不符 |
| make_result | 汇总完成（status 字段承载成功/部分） | 2=case.json 不可读 |

## 适用范围与限制

- 面向 4:3 或 16:9 学术汇报 deck（≤约 20 页）；非设计型 PPT。
- 字号分级只区分"正文类"与"脚注类"（footer/caption/table 单元格），
  由 shape 名称判定；自定义构建需遵守同样命名约定才能被 edit_lint 正确分级。
- PNG 亮度 stdlib 解码仅支持 8-bit 非隔行 RGB/RGBA/灰度；装了 Pillow 则无此限制。
- 主题字体以外的显式字体必须在安全白名单内，否则 edit_lint 报错。
- 不生成科学结论；deck.json 内容源由上游（人或 Agent）提供，本 Skill 负责
  原生构建与可编辑性证明。

## 失败处理

- 任何门禁报错：按 edit_lint/roundtrip/render_diff 报告定位，修 deck.json 后
  重跑 build_native 起的后续阶段（幂等）。
- 渲染工具缺失：result.json `export_artifact.rendered=false`，exceptions 记
  `tool_missing`，status=partial，不伪造渲染证据。

## 维护

- 作者：99mrliu（见 GITHUB_URL.txt）
- 变更请保持：脚本确定性、软导入降级、退出码约定、禁止伪造实测值四条不变式。
- 合成输入的所有文字均为虚构（"Synth et al."/"fictional"/"synthetic"），
  不得冒充真实论文或平台案例结果。
