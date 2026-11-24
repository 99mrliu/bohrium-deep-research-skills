# ppt-talkscript-contract

讲稿契约优先的「论文转学术 PPT」Skill：先写逐字讲稿、按时长切节拍、每拍幂等投影成
一页；备注即讲稿（机器门禁防复读），证据逐字可追溯，产物可编辑、可渲染验证。

本 Skill 不提交任何预制答案；所有输出全部来自对真实输入文件的实时运行。

## 依赖与版本

- Python ≥ 3.9（stdlib 为主）
- 可选依赖（全部软导入，缺失走降级路径，不直接崩溃）：
  - `python-pptx`（slide_forge / notes_lint / rehearse / make_result 必需；
    缺失时明确 stderr + 退出码 2，产物标 tool_missing）
  - `pymupdf` 或 `pypdf`（PDF 文本提取降级链的一环；PDF 页数统计）
  - `matplotlib`（仅 examples/make_synthetic_case.py 生成合成论文 PDF 用）
- 外部工具：`pdftotext`（poppler，文本提取首选）、`soffice`（LibreOffice，渲染
  PDF；缺失时 rendered=false + exceptions 记 tool_missing）、`pdftoppm`（PNG 预览）

开发验证环境：Python 3.12 + python-pptx 1.0.2 + pymupdf 2.1 + pypdf + matplotlib
3.11 + LibreOffice（macOS）。

## 安装

```bash
pip install python-pptx pymupdf pypdf matplotlib   # 按需
# poppler（pdftotext/pdftoppm）与 LibreOffice 用系统包管理器安装
```

平台部署：把本目录（skill/ 的内容）放到 `/skills/weekly-skill` 即可。

## 调用步骤（与 SKILL.md 阶段一一对应）

```bash
# 0. （仅本地演示）生成合成输入
python3 examples/make_synthetic_case.py --out /path/to/input

# 1. 证据扫描
python3 scripts/evidence_scan.py input/paper.pdf --out work/evidence.json

# 2. 写 talkscript.md 与 work/beats.json（schema 见 references/talkscript-format.md），然后校验
python3 scripts/beat_cut.py work/beats.json --evidence work/evidence.json \
    --minutes 10 --max-slides 8 --report work/beat_report.json

# 3. 逐拍幂等投影（对每拍 i 执行一次）
python3 scripts/slide_forge.py output/presentation.pptx --beat work/beats.json#0 \
    --template input/target-template.pptx --evidence work/evidence.json \
    --paper input/paper.pdf --log work/forge_log.json

# 4. 备注门禁 + 彩排
python3 scripts/notes_lint.py output/presentation.pptx --minutes 10 --report work/notes_report.json
python3 scripts/rehearse.py output/presentation.pptx --cpm 240 --wpm 150 --report work/rehearsal.json

# 5. 渲染（并发时加 -env:UserInstallation=file:///tmp/lo-<key>）与组装
soffice --headless --convert-to pdf --outdir output output/presentation.pptx
pdftoppm -png -r 100 output/presentation.pdf output/preview
python3 scripts/make_result.py --case input/case.json --task input/task.md \
    --deck output/presentation.pptx --pdf output/presentation.pdf \
    --previews "output/preview-*.png" --beats work/beats.json \
    --evidence work/evidence.json --notes-report work/notes_report.json \
    --rehearsal work/rehearsal.json --change-records work/change_records.json \
    --out output/result.json
```

每个脚本支持 `--help`；确定性（同输入同输出）；幂等（slide_forge 重跑只更新目标页）。

## 脚本一览

| 脚本 | 职责 | 退出码 |
| --- | --- | --- |
| `evidence_scan.py` | 分页文本 + caption 索引 + 数值锚点 → evidence.json | 0 正常；2 三链全断/参数错 |
| `beat_cut.py` | 校验 beats.json：字段/引用/过渡/拍数/时长 ±10% | 0 PASS；1 有 error；2 输入不可读 |
| `slide_forge.py` | 幂等 upsert 第 i 页；备注=讲稿；页脚引用；缺图放占位框 | 0 正常；2 依赖或参数错 |
| `notes_lint.py` | 备注门禁：存在/Jaccard≤0.5/标记/总时长 | 0 PASS；1 有 error；2 deck 不可读 |
| `rehearse.py` | 逐页口播秒数、超速页、过薄页（仅警告） | 0 正常；2 deck 不可读 |
| `make_result.py` | 按 case.json 的 output_contract 组装 result.json，checks 全实测 | 0 正常；2 输入不可读 |

## 适用范围

- 论文/科研材料 → 有时长预算、页数上限、模板要求的学术汇报 PPT（答辩、组会、会议
  short talk）。
- 特别适合要求"证据可追溯"（每页引用 + 逐字 quote + 页码）与"可复核"（机器门禁 +
  result.json）的评测场景。

## 限制

- 图提取按"caption 上方页面区域"裁剪，密集排版页可能裁进邻近文字；取不到就放带引用
  文字的占位框（诚实 partial），不伪造图。
- 语速是假设值（240 CPM / 150 WPM，可调），真实口播因人而异（result.json 的
  uncertainties 有声明）。
- PDF 文本提取对加密/扫描件无效（三链全断 → 明确报错）。
- notes_lint 的过渡/强调检测基于标记词表，可能漏掉不含标记词的自然过渡（可按需扩充
  MARKERS）。

## 失败处理

任何脚本失败都会给具体 stderr 与非零退出码；组装阶段把失败写入 result.json 的
exceptions（材料缺失 / 无法判断 / 运行失败分类），status 如实标 partial 或 failed。
禁止未渲染声称渲染、禁止凭空断言 checks。

## 维护

- 版本：v1（2026-11，Bohrium Playground 挑战 ppt-c7b80f0d，方向 A）。
- 仓库地址见 GITHUB_URL.txt。
- 本地端到端验证（合成案例）见 examples/minimal_example.md。
