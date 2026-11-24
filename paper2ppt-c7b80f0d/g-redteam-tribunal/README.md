# ppt-redteam-tribunal

对抗式红队复核的论文转学术 PPT Skill：第一稿 deck 是"被告"，R1–R8 确定性
检测器发起结构化攻击，finding 进台账（tribunal），修复或正式裁决后才允许
通过收敛门禁交付成品。

## 依赖与版本

- Python 3.10+（本地验证 3.12）
- 必需（构建/渲染）：python-pptx ≥ 1.0
- 可选（软导入，缺失走降级链）：
  - PDF 文本：pdftotext（poppler，subprocess）→ pymupdf → pypdf
  - 渲染：LibreOffice `soffice`（macOS: `/Applications/LibreOffice.app/Contents/MacOS/soffice`）
  - 预览：pdftoppm（poppler）
  - 合成输入生成：matplotlib
- 除上述外仅用标准库。任何脚本缺依赖都不会崩溃：要么降级并在产物中标记
  （`engine` / `tool_missing`），要么非零退出 + 明确 stderr。

## 安装

```bash
pip install python-pptx pymupdf pypdf matplotlib
# poppler 与 LibreOffice 用系统包管理器安装
```

无需安装即可运行：缺失依赖时脚本走降级路径。

## 调用步骤（完整红队闭环）

```bash
S=scripts
# 0. 合成输入（仅本地验证；平台场景用 /input 真实材料）
python3 examples/make_synthetic_case.py --out /input
# 1. 事实池
python3 $S/extract_facts.py /input/paper.pdf --out work/facts.json
# 2. Agent 撰写 deck_v1.json（第一稿被告，立即落盘）
# 3. Round 1 全量扫描
python3 $S/redteam_scan.py work/deck_v1.json work/facts.json --round 1 --report work/findings_round1.json
# 4. 入账
python3 $S/tribunal_log.py --findings work/findings_round1.json --ledger work/tribunal.json
# 5a. 机器修（R1/R2），其余进 needs_agent
python3 $S/apply_fixes.py work/deck_v1.json --ledger work/tribunal.json --out work/deck_auto.json --report work/fixes_report.json
# 5b. 人工修 deck_auto.json -> deck_v2.json 后销账 / 裁决
python3 $S/tribunal_log.py --ledger work/tribunal.json --fix R3-s4-1 --note "quote 替换为 p3 逐字句"
python3 $S/tribunal_log.py --ledger work/tribunal.json --disposition R8-s4-1 accept-risk --reason "..."
# 6. Round 2 复扫
python3 $S/redteam_scan.py work/deck_v2.json work/facts.json --round 2 --report work/findings_round2.json
# 7. 收敛门禁（exit 0=pass / 1=fail）
python3 $S/converge_gate.py --ledger work/tribunal.json --prev work/findings_round1.json --cur work/findings_round2.json --report work/convergence.json
# 8. 构建
python3 $S/build_deck.py work/deck_v2.json --template /input/target-template.pptx --fig-dir /input/figs --out output/presentation.pptx --report output/build_report.json
# 9. 渲染 + 汇总（内部调 soffice/pdftoppm）
python3 $S/make_result.py --case /input/case.json --task /input/task.md --deck work/deck_v2.json --pptx output/presentation.pptx --build-report output/build_report.json --convergence work/convergence.json --ledger work/tribunal.json --fixes work/fixes_report.json --facts work/facts.json --outdir output
```

所有脚本支持 `--help`，确定性、幂等。

## 适用范围

- 论文/科研材料 → 学术汇报 PPT，且要求证据可追溯、质量可审计的场景。
- deck.json 是本 Skill 的中间表示（schema 见 examples/minimal_example.md）。

## 限制

- R4（栏目名标题）与 R5（段落搬运）是启发式，有误报/漏报空间；误报走
  disposition reject，漏报不阻塞门禁（warn 级）。
- R1 数值锚点为"数字+单位"精确匹配；无单位数字（如 "3 stages"）不受检。
- R3 逐字校验依赖 PDF 文本层；扫描件整体退化为无法校验。
- 检测器为确定性脚本，无法发现"数值在论文中但与语境不符"类语义错误。

## 失败处理

| 退出码 | 含义 |
|--------|------|
| 0 | 成功（converge_gate 例外：0=pass, 1=fail） |
| 1 | converge_gate verdict=fail |
| 2 | 输入文件/参数错误，或 extract_facts 全引擎失败 |
| 3 | build_deck 缺 python-pptx；tribunal_log 非法状态迁移 |

## 维护

- 缺陷规则变更：先改 references/defect-taxonomy.md，再改 redteam_scan.py，
  保持文档与代码一致；finding id 格式变更会破坏跨轮 diff，需谨慎。
- 台账禁止物理删除是硬约束，扩展时不得破坏。
