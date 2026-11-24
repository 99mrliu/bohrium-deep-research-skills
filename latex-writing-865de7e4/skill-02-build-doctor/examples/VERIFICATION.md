# VERIFICATION（合成示例的验证记录，非正式案例结果）

本文件记录对 `broken/`、`fixed/` 两个**合成示例**工程的本地端到端验收。
示例只证明接口可运行，不代表正式案例表现。验收后已删除
`examples/_run/`（含 PDF/PNG 二进制），页数/大小/抽查文本以文字形式记录如下。

## 运行环境

- macOS arm64；Python 3.12；TeX Live 2026（`$HOME/texlive/2026/bin/universal-darwin`，
  pdflatex/xelatex/bibtex/biber 均在）；poppler 工具（pdftotext/pdftoppm）来自
  `~/Library/Application Support/com.bohrium.runtime/.../poppler/bin/`。
- 复现命令：`bash examples/run.sh`（脚本内部依次执行下述 5 步）。

## 步骤 1/5：broken/ 有界多轮编译（texbuild.py）

命令：`python3 scripts/texbuild.py --project examples/broken --builddir <run>/work/build-broken --report <run>/work/build-broken-report.json`

观察（退出码 1，符合预期）：

- 探测：main_file=`main.tex`，engine=`pdflatex`，bib_tool=`bibtex`；
  `mirrored_dirs=["chapters"]`（`\include{chapters/methods}` 的子目录镜像生效，
  未出现 `I can't write on file 'chapters/methods.aux'`）。
- **宏包预检**：`preflight_missing_packages=[{"file":"ghostmath.sty","via":"\\usepackage"}]`，
  编译前就锁定了故障 1。
- 日志在 `File 'ghostmath.sty' not found` 后进入 `Enter file name:` 提示，
  nonstopmode 无法读终端而 Emergency stop，未产出 PDF；
  报告 `status="failed"`、`pdf=null`、`pdf_fresh=false`——没有拿旧 PDF 冒充成功。

## 步骤 2/5：broken/ 日志诊断（texlog.py）

命令：`python3 scripts/texlog.py --log <run>/work/build-broken/main.log --project examples/broken --outdir <run>/work/diagnosis --map references/package-map.md`

观察（退出码 0）：2 条错误聚为 2 个根因，其中 1 条级联折叠：

- R1 `LaTeX Error: File 'ghostmath.sty' not found.`，位置 `main.tex`，建议给出
  **引用位置 main.tex:5** 与处置（映射表记录该包为虚构包名；真实场景应安装或替换）。
- R2 `Emergency stop.` 标注 **cascade-of R1**（级联折叠生效，上下文含
  `l.6 \title` 与 `*** (cannot \read from terminal in nonstop modes)`）。

## 步骤 3/5：模拟 Agent 修掉故障 1 后的二次诊断

run.sh 复制 broken/ 到 `_run/work/stage2` 并用 sed 删除 `\usepackage{ghostmath}`
（模拟 Agent 按 R1 建议修稿），重跑 texbuild+texlog。观察：

- texbuild 退出码 1（latex_errors，PDF 仍产出）；构建目录出现
  `chapters/methods.aux`，子目录镜像再次生效。
- texlog 聚类出 **3 个独立根因**，无一条被误折叠为级联：
  - R1 `Undefined control sequence.`，位置 `chapters/methods.tex:5`，
    上下文 `l.5 Let the input vector be $\vect`，建议命中 package-map：
    宏包 esvect（或改用 \mathbf/\vec）；
  - R2 `Missing } inserted.`，位置 `chapters/methods.tex:7`，
    上下文 `l.7 $\hat{y} = \sum_{i=1^{n} w_i x_i$`，建议检查花括号配对；
  - R3（警告级）`Citation 'knuth1997' ... undefined on input line 13`，
    建议列出 .bib 现有键 knuth1984、lamport1986。
- 79 列包裹的日志被正确拼行（跨行的 `\vect` 上下文完整呈现）。

## 步骤 4/5：fixed/ 修复后重编译验证（texverify.py）

命令：`python3 scripts/texverify.py --project examples/fixed --case examples/case.json --task examples/task.md --workdir <run>/work/verify --out <run>/output --skill-dir .`

观察（退出码 0，`status="complete"`）：

- 真实重编译 **3 轮收敛**：第 1 轮 pdflatex + bibtex，第 2 轮仍有 Rerun 提示，
  第 2、3 轮 aux 哈希一致且无 Rerun 提示 → `converged=true`。
- 最终日志 **0 错误**；PDF 为本次构建新产出（构建前删旧、构建后 mtime 校验）。
- **页数 3 页**（pdftotext `\f` 计数）；PDF 大小 **120413 字节**。
- 首页文本抽查：实际文本开头为 `Synthetic Broken Demo / Example Author /
  2026-01-01 / 1 Introduction / This synthetic demo exercises the
  build-diagnose-fix-verify loop. ... references are [1] (key exists) and [2]
  (fix 4: known key).`；关键词 Synthetic/Broken/Demo 全部命中。
- pdftoppm 渲染首页 `preview-1.png`（993×1404，36501 字节），目检排版正常
  （标题、作者、日期、Introduction 节与两条文献引用）。
- result.json：`case_id="synthetic-latex-build-doctor-001"` 原样复制；
  契约四字段逐字段镜像（compiled_pdf=真实路径、page_count=3、
  diagnosis_report=真实路径、warnings=列表）；`artifacts` 只列 3 个真实存在
  的文件；`uncertainty=[]`。
- 契约归一化单测：`{字段:{type,required}}`、自然语言描述、JSON Schema、
  字段名列表四种方言均正确解析（后者 `可选` 描述被识别为非必填）。

## 步骤 5/5：降级验证

- **无 TeX 环境**：`env PATH=/usr/bin:/bin python3 scripts/texbuild.py ...`
  退出码 3，报告 `status="blocked"`、`missing_tools=["pdflatex","bibtex"]`，
  并写清需要安装 TeX Live；未伪造任何编译结果。
- **case.json 缺失**：texverify 以 `--case /nonexistent/case.json` 运行，
  result.json 照常落盘，`case_id=null`，uncertainty 记录"case.json 缺失，
  按材料如实降级"，编译验证部分仍正常完成。

## 约束检查（验收时实测）

- 文件 16 个（不含本文件与 `_run/`），总计约 72.8 KB；全部 UTF-8；
  无符号链接；无 >500KB 单文件；无二进制（PDF/PNG 验收后已删除）。
