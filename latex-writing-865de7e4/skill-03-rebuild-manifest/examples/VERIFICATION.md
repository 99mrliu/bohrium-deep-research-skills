# 本地端到端验收记录（合成示例（synthetic example）验证记录，非正式案例结果）

验收时间：2026-11-24（Asia/Shanghai）。本文件记录对合成示例的真实运行命令与
观察到的输出摘要；运行中间产物（构建目录、PDF、zip、manifest/报告实体文件）
已按公共规范删除，仅保留输入、本记录与命令。

## 0. 验收环境

- macOS 24.6.0 arm64；Python3（仅标准库）；
- `pdflatex`：pdfTeX 3.141592653-2.6-1.40.29 (TeX Live 2026)
  （`export PATH="$HOME/texlive/2026/bin/universal-darwin:$PATH"`）；
- `pdftotext`：25.01.0（poppler 运行时已加入 PATH）。

## 1. 合成输入

- `examples/project/main.tex`：article + booktabs 三线表 + `\include{content/methods}`
  + 1 条 bibtex 文献（refs.bib）+ 工程自带 `\listfiles`；
- `examples/case.json`：`case_id = synthetic-rebuild-001`，output_contract 采用
  `{字段: {type, required}}` 方言（build_manifest / rebuild_verdict /
  version_differences）。

## 2. 正向流程（真实执行）

```bash
export PATH="$HOME/texlive/2026/bin/universal-darwin:<poppler bin>:$PATH"
cd bundles/skill-03-rebuild-manifest
python3 scripts/capture.py  --project examples/project --main main.tex \
    --outdir examples/_run/work/manifest --work-root examples/_run/work
python3 scripts/rebuild.py  --project examples/project \
    --manifest examples/_run/work/manifest/manifest.json \
    --workdir examples/_run/work/rebuild
# （模拟 Agent 读报告后）写入 examples/_run/work/result_fields.json
python3 scripts/finalize.py --input examples --workdir examples/_run/work \
    --outdir examples/_run/output
```

观察到的关键输出：

- capture：`status=complete, passes=3, file_versions=10`；命令序列为
  pdflatex → bibtex → pdflatex → pdflatex（退出码全 0），aux 第 3 轮收敛；
  版本清单 10 条（article.cls 2026-06-04 v1.4n、size11.clo、booktabs.sty
  2020/01/12 v1.61803398、geometry.sty 2026/03/07 v6.0、keyval.sty、
  ifvtex.sty、iftex.sty、l3backend-pdftex.def、content/methods.tex、main.bbl）；
  引擎 pdfTeX 3.141592653-2.6-1.40.29 (TeX Live 2026)；字体 6 个
  （cmbx12/cmr10/cmr12/cmr17/cmti10/cmtt10.pfb）；PDF 3 页；
  全文文本哈希 `5e522df4…`（822 字符）；输入文件哈希 3 个。
- rebuild：zipfile 打包 3 个源文件 → 干净目录解压 → 重放同一命令序列。
  `verdict = reproducible-identical`：源码 3/3 same、版本清单 10/10 same、
  引擎 same、轮次 3=3、aux 收敛、页数 3=3、全文文本一致；
  PDF 字节哈希基线 `0df946f0…` vs 重建 `3cc9d1ac…` 不同，报告如实标注
  “/ID 与时间戳所致，不作判据”。
- finalize：`status=complete, artifacts=5`（manifest.json/md、
  rebuild_report.json/md、source_snapshot.zip）；result.json 的 case_id
  原样为 `synthetic-rebuild-001`，契约 3 字段按方言解析并逐字段镜像，
  非 `{}` 空壳。

## 3. 降级场景 A：版本清单被改动（必须判 different，不得误判一致）

把 manifest 中 booktabs.sty 的版本改为 `v9.99tamp` 后重新 rebuild：

- `verdict = not-reproducible-identical`；
- 原因明确列出：“版本清单存在差异条目：booktabs.sty”；
- 差异条目逐条给出双侧版本：baseline `2020/01/12 v9.99tamp` vs
  rebuild `2020/01/12 v1.61803398`。

## 4. 降级场景 B：缺失输入（case.json 缺失）

对空输入目录运行 finalize：`status=blocked`，`case_id=null`，
uncertainty 逐条说明“case.json 缺失已遍历 /input 降级”“各产物不存在未复制”，
artifacts 为空列表，未填充任何编造值。

## 5. 降级场景 C：pdflatex 不可用

以 `PATH=/usr/bin:/bin` 运行 capture：`status=partial`，仅记录 3 个输入哈希，
limitations 写明“pdflatex 不可用：只记录输入哈希，无法编译与提取版本清单”，
不假装成功。

## 6. \listfiles 临时副本注入验证

在工程副本中删除 `\listfiles` 行后运行 capture：
`listfiles_injected_on_copy=true`，仍提取到 10 条版本清单；注入只发生在
构建目录副本，原工程文件经 grep 确认未被改动（检测逻辑按“行首 \listfiles
命令”判定，不会被 `\verb|\listfiles|` 等纯文本提及误伤——此缺陷已在验收中
发现并修复）。

## 7. output_contract 方言归一化自测

对 finalize.normalize_contract 的直接调用结果：`{字段:{type,required}}` →
正确取字段名与 type/required；JSON Schema（properties/required）→ 正确；
字段名列表 → 正确；自然语言（反引号标识符）→ best-effort 提取并声明限制；
缺省 → 空字段 + 说明。

## 8. 运行约束检查

- 文件数：13（含本文件），≤16 目标内；
- 总计 73,995 字节（约 72KB），单文件 ≤500KB；全部 UTF-8 文本；无符号链接；无二进制
  （PDF/zip 等运行产物已删除，未留在 bundle 中）；
- 检查方式：`find` 枚举 + Python 逐文件 UTF-8 解码与大小统计（脚本未保留，
  命令见第 2 节风格的标准组合）。
