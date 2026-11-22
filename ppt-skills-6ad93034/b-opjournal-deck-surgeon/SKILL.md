---
name: opjournal-deck-surgeon
description: 操作日志外科式学术演示稿构建与改编。当任务提供底稿（create 模式的 target-template.pptx 或 edit/adapt 模式的 starting-deck.pptx）与论文 PDF，要求生成或改编可编辑学术 PPT 时使用。核心方法：底稿冻结为 v000 快照，之后一切改动（加页、改题、写要点、插图、删页、替换文字）都以带 why 与 anchor 的操作追加入册（journal.jsonl），apply.py 纯重放成稿——任何一页可回退、任何一版可复现、每轮改了什么为什么改自动形成 change_journal.md。操作入册时即校验数字命中锚定页、图来自真实裁剪；apply 后 verify.py 独立审计页数/备注/来源戳/图片比例/模板字节级一致。适用于多轮迭代的学术汇报制作与旧稿改编；不适用于无 PPTX 底稿的自由设计。
---

# opjournal-deck-surgeon：操作日志外科式演示稿构建

## 方法论一句话

**底稿冻结，改动入册，重放成稿。** 演示稿迭代的最大风险是"改一页顺手改坏全稿、多轮之后回不到上一版"。本 Skill 把一切修改变成可审计、可回退的操作日志：v000 底稿永不动，成稿永远等于 v000 + journal 重放。

## 输入 / 输出

| 项 | 内容 |
|-|-|
| 输入 | `/input/case.json`、`material.json`、`artifacts/slide-workorder.json`、`*.pdf`、`target-template.pptx` / `starting-deck.pptx` |
| 输出 | `/app/output/presentation.pptx`、`change_journal.md`、`presentation.pdf`、`previews/`、`result.json`；`work/versions/` 快照链 |
| 完成标准 | verify.py 全过；journal 每条操作有 why；content_map 每页有锚点；status=completed |

## 执行序列（严格按序）

```bash
export CASE_INPUT_DIR=/input CASE_WORK_DIR=/app/work CASE_OUTPUT_DIR=/app/output
mkdir -p /app/work /app/output
S=<SKILL_DIR>/scripts   # 如 /skills/weekly-skill/scripts
```

**① 接收与快照（纯脚本）**：`python3 $S/intake.py`
冻结底稿为 `work/versions/v000_base.pptx`，抽取论文文本层/图表清单/真实图裁剪，写 `work/paper_brief.md`。打印的 `figures_ok` 是唯一可引用的图。

**② 开册**：`python3 $S/op.py init`

**③ 你的手术（1–3 轮，每轮一次模型调用）**：读 `work/paper_brief.md`（不要读整篇论文），把本轮操作写成一个 JSON 文件，如 `work/ops_round1.json`：

```json
[
 {"op":"add_slide","layout":"title","role":"title","why":"封面"},
 {"op":"set_title","slide":1,"text":"论文标题：一句话定位","why":"封面标题"},
 {"op":"add_slide","layout":"body","role":"result","why":"主结果页"},
 {"op":"set_title","slide":2,"text":"英德翻译 28.4 BLEU 刷新纪录","why":"页级主张"},
 {"op":"set_bullets","slide":2,"items":[{"text":"大模型英德翻译 28.4 BLEU，超前作 2.0 以上","anchor":"p8"}],"why":"主数据"},
 {"op":"insert_figure","slide":2,"fig":"fig1","why":"架构图支撑方法页"},
 {"op":"set_notes","slide":2,"text":"这页讲主结果……","why":"讲稿"}
]
```

提交：`python3 $S/op.py add work/ops_round1.json`
**入册即校验**：数字必须命中 anchor 页、bullet ≤6 条、图必须有裁剪、why 必填。被拒操作进 `journal.rejected.jsonl`，修正后重新提交。

edit 模式：底稿已有页。用 `set_title/set_bullets/set_notes` 改写对应页码；`remove_slide` 删除废页；`replace_text` 做局部精确替换；保留不动的页**不需要任何操作**。

**④ 重放成稿**：`python3 $S/apply.py`
重放全部操作 → `output/presentation.pptx` + 里程碑快照 + `output/change_journal.md`。有 apply 失败的操作会列出——修复后重新 `op.py add` 或 `op.py rollback N` 回退再改。

**⑤ 独立审计**：`python3 $S/verify.py`
不信任 journal，直接开成稿检查：页数 == 工单、每页备注与来源戳、图片原生比例、模板部件字节级一致、字体零覆盖。hard 失败回到 ③。

**⑥ 导出**：`python3 $S/render_export.py`（无 soffice 不阻塞，记 exceptions）

**⑦ 交付**：`python3 $S/finalize.py` → `output/result.json`

## 多轮迭代与回退（本 Skill 的核心能力）

- 第二轮修改：再写一个 `ops_round2.json` 提交，`apply.py` 重放即得新版；`change_journal.md` 自动累计两轮记录；
- 改坏了：`python3 $S/op.py rollback 3`（回退最后 3 条）→ `python3 $S/apply.py` 重建；被回退的操作留在 `journal.rejected.jsonl` 供审计；
- 任意中间版：`work/versions/` 快照链 + 截断的 journal 可精确复现。

## 禁止事项

- 禁止用 python-pptx 直接改 `output/presentation.pptx`——绕过 journal 就破坏了可回退性；
- 禁止写无 why 的操作（入册校验强制拒绝）；
- 禁止数字不写 anchor 或凭印象取整（入册校验对 anchor 页文本逐字核对）；
- 禁止引用 `figures_ok` 之外的图或自制曲线图；
- 禁止手写 result.json（只能 finalize.py 组装）。

## 异常处置

| 情形 | 处置 |
|-|-|
| replace_text 找不到原文 | 操作被拒；先 `op.py list` 核对目标页当前文本 |
| 页数不足/超出 | 用 add_slide / remove_slide 调整，verify 会复核 |
| 图裁剪失败 | 该图不可引用（入册拒绝）；改用文字+anchor |
| 扫描件无文本层 | intake 记问题；数字校验自动跳过范围外锚点并告警；result 记 partial |
| soffice 缺失 | 导出具实记录，deck 照常交付 |

## 资源

- `resources/op_cookbook.md`：七种操作的适用场景与典型手术流程（新建整稿 / 旧稿翻新 / 局部修订）；
- 依赖 python3 + python-pptx；pdftotext/pdftoppm/soffice/pymupdf 可用性自动降级。
