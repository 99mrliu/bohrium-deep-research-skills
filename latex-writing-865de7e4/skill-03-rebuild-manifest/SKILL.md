---
name: latex-rebuild-manifest
description: >-
  当任务涉及 LaTeX 工程的“可重复构建 / 复现得了”时触发：需要把一次构建的环境（引擎与
  TeX 发行版版本、文档类与宏包逐版本清单、使用字体）、精确编译命令序列与轮次、全部
  输入文件 SHA256、PDF 页数与全文文本哈希固化为构建谱系 manifest，或需要在干净目录
  按 manifest 模拟他人环境重建并逐判据比对一致性。脚本只做确定性机械工作：capture.py
  在独立构建目录内有界多轮编译（≤4 轮 + bibtex 按需，aux 哈希收敛判据）并从日志
  \listfiles 区块提取版本清单（\listfiles 仅注入构建目录内的临时副本，绝不改用户
  原文件）；rebuild.py 用 zipfile 打包源码、解压到干净目录重放命令序列，逐条输出
  same/different/missing 比对，对 PDF 字节级不确定性（/ID 与时间戳）如实说明，版本
  漂移明确判 not-reproducible-identical 不含糊带过；finalize.py 装配 /app/output 并
  归一化 output_contract 四种历史方言生成 result.json。Agent 负责读 task.md、理解
  manifest 与比对报告、做语义判断（版本漂移是否可接受、如何固定版本、契约字段如何
  取值）并写入 result_fields.json。红线：脚本不得修改用户源文件、不得自动改写 LaTeX
  源码、不得填充编造契约字段值；pdflatex/bibtex/pdftotext 运行时探测，缺失时诚实
  降级并写入报告，禁止假装成功。不适用场景：纯写作润色、无 LaTeX 工程输入、或不
  需要构建复现证据的任务。
---

# latex-rebuild-manifest：构建谱系固化与异地重建一致性验证

一句话定位：把 LaTeX 工程的每次构建固化为可核验的 manifest，并能在干净目录按
manifest 重建、逐判据回答“他人能否得到同一份产物”。

## 环境与预算

- 运行契约：输入 `/input/case.json`、`/input/task.md`，材料路径相对 `/input` 解析；
  工作目录 `/app/work`；最终产物与 `result.json` 放 `/app/output`。
- 脚本仅依赖 Python3 标准库；`pdflatex`/`bibtex`/`pdftotext` 运行时探测，缺失时
  诚实降级（见“异常处置”）。
- 预算：64 次模型请求 / 900 秒 / 每次响应 16384 tokens。建议时刻表：
  1. 0–60 秒：读输入、定位工程与主文件，跑 capture.py（编译是耗时大头，先启动）；
  2. 60–150 秒：读 manifest.md，确认轮次收敛、版本清单非空，必要时用 `--main` 重跑；
  3. 150–500 秒：跑 rebuild.py（含两轮以上真实编译）；
  4. 500–650 秒：**先跑一版 finalize.py 落盘 result.json（即使 partial 也先交付）**；
  5. 650–850 秒：读 rebuild_report.md 做语义判断，写 `result_fields.json`，再跑
     finalize.py 增量改进 result.json。

## 运行流程

设 Skill 安装目录为 `SKILL_DIR`（评测时为 `/skills/weekly-skill`）。

```bash
# 0. 定位工程目录 PROJ 与主文件 MAIN（相对 PROJ）；从 case.json 的 materials 解析
# 1. 固化构建谱系（编译在独立构建目录进行，原工程零改动）
python3 "$SKILL_DIR/scripts/capture.py" \
    --project "$PROJ" --main "$MAIN" \
    --outdir /app/work/manifest --work-root /app/work

# 2. 阅读 /app/work/manifest/manifest.md，确认构建完整（Agent 判断，见下节）

# 3. 模拟他人环境：打包 zip -> 干净目录解压 -> 按 manifest 重放 -> 逐判据比对
python3 "$SKILL_DIR/scripts/rebuild.py" \
    --project "$PROJ" \
    --manifest /app/work/manifest/manifest.json \
    --workdir /app/work/rebuild

# 4. 阅读 rebuild_report.md，做语义判断后把契约字段值写入
#    /app/work/result_fields.json（JSON 对象，键为契约字段名）

# 5. 装配交付（可先跑一版 partial 落盘，再增量改进）
python3 "$SKILL_DIR/scripts/finalize.py" \
    --input /input --workdir /app/work --outdir /app/output
```

## Agent 判断规则（脚本不做的事）

1. **选主文件**：多个含 `\documentclass` 的 .tex 时，按 task.md 语义用 `--main`
   指定；capture 自动探测时会提示候选，需人工确认。
2. **读 manifest**：pdflatex 轮次 ≤4 且 aux 收敛才算“稳定构建”；版本清单为空、
   字体清单为空都要追查原因（日志无 *File List* 区块通常是 \listfiles 未生效）。
3. **读比对报告做语义判定**：
   - 版本条目 `different`：判断是记录过期（更新 manifest）还是环境漂移（建议
     固定宏包版本，如随工程附带 .sty 或注明 TeX Live 年份），把结论写入
     `result_fields.json` 对应字段；
   - 条目 `missing`：区分“基线多出来”（他人环境缺包，需补依赖说明）与
     “重建多出来”（基线记录不全）；
   - verdict 为 `inconclusive`：按报告中的限制说明补齐工具后重跑，不得强行宣布
     复现成功。
4. **契约字段取值**：按 task.md 的 output_contract 逐字段映射到真实产物或判断
   结论，写入 `/app/work/result_fields.json`；缺材料的字段留空，由 finalize 输出
   诚实的 null 与说明。

## 脚本产出说明

- `/app/work/manifest/manifest.json` + `manifest.md`：构建谱系（字段定义见
  `references/manifest-schema.md`）。
- `/app/work/rebuild/rebuild_report.json` + `rebuild_report.md`：逐判据比对；
  判据为 文本一致 + 页数一致 + aux 收敛 + 版本清单无 different/missing + 轮次相同；
  PDF 字节哈希只报告、不作判据。
- `/app/work/rebuild/source_snapshot.zip`：源码快照（评测运行时允许二进制交付）。
- `/app/output/`：上述产物的副本 + `result.json`（case_id 原样、契约字段逐字段
  镜像、status 据实、sources/uncertainty/artifacts 齐全）。

## 异常处置（识别 → 降级 → 记录）

- `pdflatex` 缺失：capture 只记录输入文件哈希，manifest 状态 partial，版本清单
  为空并写明原因；rebuild 判 `inconclusive`。
- `bibtex` 缺失且检测到 `\citation`：记录限制，继续 pdflatex 轮次，提示文献未解析。
- `pdftotext` 缺失：文本哈希为 null，重建判 `inconclusive` 而非臆断一致。
- 编译失败（无 PDF）：manifest 记录实际命令与退出码，状态 partial，日志路径写入
  限制说明；finalize 状态 partial。
- 4 轮内 aux 未收敛：如实记录实际轮次与未收敛事实（可能存在不稳定交叉引用）。
- `case.json` 缺失：遍历 `/input` 记入 sources，case_id 置 null，finalize 据实
  给 blocked/partial。

## 红线

1. 绝不修改用户原始工程文件；\listfiles 只注入构建目录内的临时副本。
2. 脚本不自动改写 LaTeX 源码、不替 Agent 做写作/取舍决策，只输出证据与建议。
3. 版本不同必须逐条列出并判 `not-reproducible-identical`，不得含糊带过；PDF
   字节级不同属正常，但同样如实报告。
4. 契约字段缺材料时给 null + uncertainty，禁止填充编造值。
5. 所有产物标注来源；示例为合成示例，不预生成任何正式案例结果。
