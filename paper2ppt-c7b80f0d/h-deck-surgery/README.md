# ppt-deck-surgery

起始稿手术与版本化编辑：把"按新任务改造一本已有学术汇报 PPT"当作变更工程——
先诊断后动刀、ops 日志、幂等应用、版本快照与回滚、机器 diff 与最小改动校验。

## 依赖与版本

- Python ≥ 3.10（本地验证用 3.12）
- 可选依赖（全部软导入，缺失走降级路径，不崩溃）：
  - `python-pptx` ≥ 1.0（编辑 pptx；缺失时 probe/diff/lint 降级为 stdlib 只读，
    deck_ops 退出码 3 明确报错，不伪造编辑）
  - `pymupdf` 或 `pypdf`（PDF 文本提取降级链：pdftotext → pymupdf → pypdf）
  - `matplotlib`（仅 examples/make_synthetic_case.py 生成合成论文 PDF 用）
- 外部工具：LibreOffice `soffice`（渲染，缺失时 render_check 退出 3 + tool_missing）、
  `pdftoppm`（PNG 预览）。并发渲染必须隔离 profile：
  `-env:UserInstallation=file:///tmp/lo-<key>`（render_check 的 --profile-key）。

安装：`pip install python-pptx pymupdf pypdf matplotlib`

## 脚本与调用顺序

```bash
# 0.（本地演示）生成合成输入
python3 examples/make_synthetic_case.py --out runs/e/input
# 1. 证据锚点扫描
python3 scripts/evidence_scan.py input/paper.pdf --report work/evidence.json
# 2. 起始稿诊断（逐页 text_hash 基线、主题 sha1）
python3 scripts/deck_probe.py input/starting-deck.pptx --report work/probe_report.json
# 3. 手术建议骨架（Agent 据此手工填 ops_journal.json）
python3 scripts/plan_ops.py --probe work/probe_report.json --task input/task.md \
    --evidence work/evidence.json --suggest work/ops_suggested.json
# 4. 幂等应用 + 版本快照（重跑同一 journal 全部 skipped）
python3 scripts/deck_ops.py input/starting-deck.pptx --ops work/ops_journal.json \
    --out output/deck_final.pptx --versions-dir work/versions --log work/ops_log.json
# 5. 机器 diff + 最小改动校验
python3 scripts/deck_diff.py work/versions/v1.pptx output/deck_final.pptx --report work/deck_diff.json
python3 scripts/surgery_lint.py work/versions/v1.pptx output/deck_final.pptx \
    --ops work/ops_journal.json --log work/ops_log.json --report work/surgery_report.json
# 6. 真实渲染（soffice → PDF → PNG）
python3 scripts/render_check.py output/deck_final.pptx --out-dir output/render \
    --report work/render_report.json --profile-key e
# 7. 汇总 result.json（output_contract 从 case.json 运行时读取）
python3 scripts/make_result.py --case input/case.json --task input/task.md \
    --deck output/deck_final.pptx --evidence work/evidence.json \
    --ops-log work/ops_log.json --diff work/deck_diff.json \
    --render work/render_report.json --out output/result.json
```

每个脚本支持 `--help`；同输入同输出（确定性）；幂等。

## 退出码约定

| 脚本 | 0 | 非零 |
|---|---|---|
| evidence_scan | 提取成功 | 2=输入缺失；3=PDF 引擎全缺（tool_missing，仍写空骨架） |
| deck_probe / plan_ops / deck_diff | 成功 | 2=输入缺失或无法解析 |
| deck_ops | 全部 applied/skipped | 2=有 failed；3=缺 python-pptx |
| surgery_lint | 无 error | 1=有 error（账外改动/主题被改/记录不全/failed op）；2=输入缺失 |
| render_check | 渲染成功 | 2=输入缺失；3=soffice/pdftoppm 缺失；4=soffice 转换失败 |
| make_result | 全 compliance pass 且无 exception | 1=partial/failed；2=输入缺失 |

## 适用范围

- edit 模式：/input 提供起始稿 pptx，要求按新任务/模板/时长改造（主场景）。
- generate 模式：无起始稿时从模板用 insert_slide/set_bullets ops 搭建，之后修订同流程。
- 支持 op：set_title / replace_text / set_bullets / insert_slide / delete_slide /
  move_slide / set_notes / add_figure（schema 见 references/ops-schema.md）。

## 限制

- replace_text 按段落整体重写 run，段落内混合格式（粗体/斜体并存）可能退化为首 run 格式。
- 文本哈希不含形状位置/字号；纯排版微调不在 op 集合内，lint 也不覆盖（主题级篡改除外）。
- add_figure 不做自动避让，位置需按版式估算（4:3 页面 10×7.5 英寸）。
- evidence 匹配是逐字子串级别：改述（paraphrase）后的 claim 挂不上 quote，
  会在 uncertainties 暴露而不是伪造匹配。
- stdlib-fallback（无 python-pptx）下页顺序按 slideN.xml 编号近似，仅供只读诊断。

## 失败处理

任何脚本失败：先读 stderr 具体信息 → 修正输入/journal → 重跑（幂等，已 applied
的 op 自动 skipped）。渲染失败不阻塞可编辑产物交付，result.json 记 tool_missing 诚实 partial。

## 维护

- 版本：v1.0（2026-11）。作者：bohrium-deep-research-skills 项目组。
- 变更请保持：脚本确定性、软导入降级、退出码约定、ops schema 向后兼容。
