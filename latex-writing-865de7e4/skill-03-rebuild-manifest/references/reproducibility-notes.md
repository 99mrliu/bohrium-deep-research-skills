# LaTeX 构建不可复现的常见来源与对策

按出现频率整理，供 Agent 阅读 manifest 与比对报告时做语义判断。

## 1. 宏包/类版本漂移（最常见）

同一源码在不同年份的 TeX Live 下产出不同排版，甚至编译失败（命令被废弃、
默认值变更）。表现：比对报告 `versions` 出现 `different` 或 `missing`。
对策：
- 用 `\listfiles` 固化逐版本清单（本 Skill 的 manifest 即做此事）；
- 论文投稿随源码附关键宏包的同名 .sty 副本，或在 README 注明 TeX Live 年份；
- 期刊模板类文件（.cls/.bst）务必随工程分发，不要依赖对方环境自带。

## 2. 字体缺失或替换

系统字体（尤其 OTF/TTF 商用字体、CJK 字体）在他人机器上不存在时，pdfTeX 直接
报错，XeLaTeX/LuaLaTeX 可能静默回退到近似字体，导致行距、分页变化。表现：
fonts 清单中出现非 TeX Live 自带字体名，或页数/文本哈希不一致。对策：
优先使用发行版自带字体；必须用系统字体时在 manifest 中记录精确字体名并随附
授权允许的字库或替代方案说明。

## 3. 随机性与非确定性

- `pgfmath` 随机数、`lipsum`/`blindtext` 示例文本、某些绘图宏包默认种子不固定，
  同一源码两轮编译结果不同。对策：显式 `\pgfmathsetseed{固定值}`；
- 并行构建工具（latexmk -j、缓存目录残留）可能掩盖未收敛。对策：干净构建目录
  + aux 哈希收敛判据（本 Skill 默认行为）。

## 4. 时间戳与 PDF 元数据（字节级不确定性）

pdfTeX 把创建时间写入 PDF `/CreationDate`，并据时间与输出路径生成 `/ID`。
**因此同一环境连续两次编译的 PDF 字节哈希通常也不同，这是正常的，不是不可复现。**
判据应落在语义层：全文文本一致 + 页数一致 + aux 收敛 + 版本清单无漂移。
若确实需要字节级一致，可设 `SOURCE_DATE_EPOCH` 环境变量固定时间戳并加
`-output-directory` 无关的固定路径；但多数场景没有必要。

## 5. `-output-directory` 与相对路径行为

- `-output-directory` 只改产物落点，不改输入搜索路径；`bibtex`/`makeindex`
  不知道该参数，需进入产物目录运行或设 `TEXMFOUTPUT`，否则 .bbl 生成错位；
- `\include{chapters/x}` 要求 `chapters/` 子目录在输出/构建目录中**已存在**，
  否则写 chapters/x.aux 失败；本 Skill 通过整体镜像工程目录规避；
- 在工程根目录直接编译会污染源码树（.aux/.log 散落），且旧 .aux 可能掩盖
  版本变化。对策：始终在独立构建目录编译（本 Skill 默认行为），输入哈希在
  复制前对原始工程计算。

## 6. 行尾与编码

CRLF/LF、BOM 会改变源码字节哈希（changed），但通常不影响排版。比对报告把它
归入源码层差异，由 Agent 判断是否实质问题；跨平台分发建议统一 LF + UTF-8 无 BOM。
