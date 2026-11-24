---
name: latex-build-doctor
description: >-
  LaTeX 编译错误的真实诊断与修复验证闭环，适用于"工程编译不过、需要改到编译得通并交付
  PDF"的任务：文档类/宏包缺失、未定义命令或环境、数学模式与花括号不配平、文献键未定义、
  交叉引用不收敛等。核心分工是脚本做确定性机械工作、模型做语义修复：texbuild.py 探测
  主文件/引擎（CJK 或 fontspec 判 xelatex）/文献工具（biber 或 bibtex），在独立构建目录
  做有界多轮编译（≤4 轮，预先镜像 \include 子目录，aux 哈希收敛判据，构建前删旧 PDF、
  构建后校验 mtime，绝不用旧 PDF 冒充成功）；texlog.py 解析日志（处理 79 列包裹与文件栈），
  把每条错误定位到具体文件+行号+根因，同签名合并、级联错误标注 cascade-of，并按
  references/package-map.md 给出宏包建议，只建议不改稿；texverify.py 在 Agent 修复后真实
  重编译验证（0 错误、新鲜 PDF、页数与首页关键词抽查、pdftoppm 首页预览）并装配
  result.json（output_contract 四种方言归一化，缺材料诚实 null）。红线：脚本不做侵入式
  改写、不预生成正式答案、不伪造编译结果；pdflatex/xelatex/bibtex/biber/pdftotext/pdftoppm
  运行时探测，缺失即诚实 blocked/降级并写清缺什么。不适用：无编译需求的纯写作润色、
  需要安装整个 TeX 发行版才能继续且无法联网的环境（此时只能给诊断不能给验证）。
---

# latex-build-doctor

一句话定位：脚本负责"编译、读日志、验证"的确定性工作，Agent 负责读诊断、理解
任务、动手修稿，最终交付一份**真实重编译验证通过**的 PDF 与诚实的 result.json。

## 环境与预算

- 输入：`/input/case.json`（case_id 与 output_contract）、`/input/task.md`、case.json
  指向的 LaTeX 工程材料（相对路径相对 /input 解析；case.json 缺失时遍历 /input 找
  含 `\documentclass` 的工程并如实降级）。
- 工作目录 `/app/work`；最终产物（PDF、诊断、首页预览、result.json）放 `/app/output`。
- 预算：64 次模型请求 / 900 秒 / 每次响应 16384 tokens。时刻表建议：
  - 0–2 次请求：读 task.md 与 case.json，跑 texbuild + texlog，拿到诊断；
  - 3–10 次：按诊断逐个根因修复（每次改动只动根因，不动级联派生）；
  - 之后立即跑 texverify 落盘第一版 result.json（先交付再改进）；
  - 剩余预算：处理残余警告、复核首页预览、补 uncertainty。
- 预留最后 1 次请求检查 result.json 字段齐全、artifacts 全部真实存在。

## 运行流程

以下命令中 `SKILL_DIR` 为 Skill 安装目录（平台上为 `/skills/weekly-skill`），
`PROJ` 为待修工程目录。

```bash
# 0. 读任务与契约（人工/Agent 阅读）
cat /input/task.md /input/case.json

# 1. 探测 + 有界多轮编译（构建目录独立于工程，避免污染源文件）
python3 "$SKILL_DIR/scripts/texbuild.py" \
  --project PROJ --builddir /app/work/build \
  --report /app/work/build-report.json

# 2. 日志诊断：错误签名聚类、级联折叠、修复建议（只建议，不改稿）
python3 "$SKILL_DIR/scripts/texlog.py" \
  --log /app/work/build/<主文件名>.log --project PROJ \
  --outdir /app/work/diagnosis --map "$SKILL_DIR/references/package-map.md"

# 3. Agent 阅读 /app/work/diagnosis/diagnosis.md，逐个根因修稿
#    （改动由 Agent 决定并用编辑器执行，脚本不代改）

# 4. 修复后真实重编译验证 + 装配 result.json
python3 "$SKILL_DIR/scripts/texverify.py" \
  --project PROJ --case /input/case.json --task /input/task.md \
  --workdir /app/work/verify --out /app/output --skill-dir "$SKILL_DIR"
```

texverify 返回非零或 status 非 complete 时，回到第 2 步对新日志再诊断，
迭代至 0 错误或预算将尽（届时落盘 partial 并写清限制）。

## Agent 判断规则

1. **只修根因，不追级联**：diagnosis 中标注 `cascade-of Rx` 的条目不要单独改，
   修好根因后它们会自然消失。
2. **建议只是建议**：texlog 的宏包建议来自 references/package-map.md 的静态映射，
   采用前先确认与工程已有宏包不冲突（如 subfig 与 subcaption 不可混用）；能不加
   新宏包就用等价内核命令（如 `\mathbf` 代替 `\vect`）。
3. **未知文献键**先核对 `.bib` 现有键（诊断里已列出）再决定改 `\cite` 还是补条目；
   不得为了让警告消失而删除有信息量的引用。
4. **收敛问题不动源码**：`Rerun to get ...` 类提示由 texbuild 的多轮机制处理。
5. 引擎不要手工强切：CJK/fontspec 工程必须 xelatex，texbuild 会自动判定；
   仅在诊断明确指向引擎误配时才用 `--engine` 覆盖。

## 脚本产出说明

- `texbuild.py` → `build-report.json`：主文件、引擎、文献工具、镜像的子目录、
  每轮返回码/aux 哈希/错误行数、收敛结论、PDF 路径与新鲜度（mtime 校验）。
  退出码 0=成功、1=有 LaTeX 错误、3=blocked（缺工具）、4=找不到主文件。
- `texlog.py` → `/app/work/diagnosis/diagnosis.{md,json}`：根因列表
  （file:line、上下文、出现次数、cascade-of、建议）、警告清单、未定义文献键。
- `texverify.py` → `/app/output/`：`<主文件名>.pdf`、`diagnosis.md`、
  `preview-1.png`（有 pdftoppm 时）、`result.json`。result.json 中 case_id 原样
  复制，output_contract 逐字段镜像（四种方言均可归一化），status 取
  complete/partial/failed/blocked 据实值，artifacts 只列真实存在的文件。

## 异常处置（识别 → 降级 → 记录）

- **pdflatex/xelatex 缺失**：texbuild 退出码 3，报告写明缺哪个工具、需要装什么；
  texverify 落盘 status=blocked 的 result.json，不伪造编译。
- **bibtex/biber 缺失**：同上 blocked；若工程无 .bib 则不触发。
- **pdftotext/pdftoppm 缺失**：编译结论不受影响；页数回退为 PDF 字节正则估计并
  标注方法，首页预览跳过，均写入 uncertainty。
- **找不到主文件**：退出码 4，报告说明；Agent 应检查材料是否完整解压。
- **轮数上限未收敛**：报告 `converged=false`，PDF 仍给出但标注，Agent 排查
  循环变化的 `\label` 或文献键。
- **case.json 缺失/契约无法解析**：case_id 置 null、契约字段为空、uncertainty
  说明，继续完成可完成的部分。

## 红线

1. 脚本不得修改工程源文件；一切改动由 Agent 决定并执行。
2. 绝不用旧 PDF、旧日志冒充成功：构建前删目标 PDF，构建后校验 mtime。
3. 契约字段缺材料时给 null 并写 uncertainty，禁止编造页数、禁止填充占位值。
4. blocked/failed 也要尽早落盘 result.json，先交付再改进。
5. 示例均为自造合成示例，不代表正式案例表现；不得在本 Skill 内预置针对
   正式案例的输出。
