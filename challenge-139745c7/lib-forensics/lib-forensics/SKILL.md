---
name: lib-forensics
description: 上游数据真实性方向。在回答任何检索提问之前，先对科研文档库做法医级入库审计：魔数识别真实文件类型（不信扩展名）、sha256 登记与精确副本归组、改名副本/别名侦测、权限/损坏/加密/无文本层逐项隔离并写恢复记录，产出"哪些文件可信、哪些被排除、为什么"的可复核清单；后续作答只允许引用通过审计的文件，被排除项如实列入 uncertainty。当任务涉及盘点输入文件、整理资料、去重、识别副本与正式版、或对文件库可信度存疑时使用；输入为 /input/case.json + task.md + 文档库。
---

# lib-forensics：文档库法医审计（上游数据真实性）

## 重心

本技能解决的不是"怎么搜"，而是"**搜的东西能不能信**"。科研库常见病灶：
扩展名与真实格式不符、改名副本被当成独立证据、损坏/加密文件被静默跳过、
扫描件无文本层却被引用页码。先把库审计成一张可信清单，再作答。

## 运行契约（必须遵守）

1. 先读 `/input/case.json` 与 `/input/task.md`。记录 `case_id`；照抄
   `output_contract` 要求的全部字段名。**不要凭文件名猜内容。**
2. **立刻**写 `/app/output/result.json` 骨架：`case_id` + output_contract
   全部字段（先填占位）+ `"status": "partial"`，之后每完成一步就更新它。
   这样即使预算耗尽也有一份诚实的部分结果。
3. 一切中间产物放 `/app/work`；最终交付放 `/app/output`。
4. `$S` 表示本技能安装目录（通常 `/skills/weekly-skill`）。脚本均为
   Python ≥3.9 标准库，**不要安装第三方包**。`pdftotext` 若存在则用于
   PDF 文本探测，缺失时如实记录 `pdf_text_probe: unavailable`。
5. 找不到的键、读不了的文件、无法判断的情况，分别写入 `uncertainty`，
   不得把未完成写成完成。

## 执行步骤

```bash
S=/skills/weekly-skill
mkdir -p /app/work /app/output
# 1. 盘点 case.json 实际结构（库路径与提问的键名以实际为准，
#    常见 library/library_root/data_dir/files 与 searches/questions/queries）
python3 "$S/scripts/forensics_case.py" /input/case.json /app/work/case_profile.json
# 2. 法医审计全库 → inventory.json + FORENSICS_REPORT.md + recovery.jsonl
python3 "$S/scripts/forensics_scan.py" <库根目录> /app/work
# 3. 基于审计结果作答（只允许引用 status=verified 的文件）
python3 "$S/scripts/forensics_answer.py" /app/work/case_profile.json /app/work/inventory.json /app/work/answers.json
# 4. 组装最终 result.json（含 output_contract 全字段）
python3 "$S/scripts/forensics_result.py" /input/case.json /app/work /app/output/result.json
```

每步后检查退出码；失败时把错误原文记入 result.json 的 `uncertainty` 并继续
后续可做的步骤。若库根目录无法确定，退而 `ls -R /input` 盘点并据实记录。

## 审计判定规则（摘要，详见 references/audit-rules.md）

- 真实类型以文件头魔数为准；与扩展名不一致记 `type_mismatch`。
- sha256 相同 = 同一文件的副本，只保留一份为 canonical（路径不含
  `副本/备份/copy/backup` 者优先），其余入 `duplicates`。
- 不可读（权限）、魔数无法识别且非文本、zip 加密标志位置位、PDF 无文本层
  且本机无 OCR → 分别记 `unreadable / unrecognized / encrypted /
  needs_ocr`，全部列入 recovery.jsonl，不静默丢弃。
- 作答时引用任何文件都必须带 sha256 前 16 位与审计状态。

## 异常处理

| 情况 | 处置 |
|-|-|
| 单个文件读失败 | 记入 recovery.jsonl，继续其余文件 |
| pdftotext 缺失/失败 | inventory 标 `pdf_text_probe`，PDF 内容类提问在 uncertainty 声明 |
| 库根目录不存在 | result.json status=partial，uncertainty 记录实际查找过的路径 |
| case.json 缺字段 | 按实际字段工作，缺失字段列入 uncertainty |

## 最小示例

`examples/` 内含一个**合成示例**库（4 个文件：改名副本、扩展名造假、正常
文本）与 `run_example.py`，运行方式与预期输出见 `examples/README.md`。

## 限制

- 不做开放网络检索；不修复文件内容本身（只隔离与记录）。
- OCR 仅在本机有 tesseract 时尝试，否则如实标注。
- 语义级同义检索非本技能重心；它保证的是被引用证据的真实性与可复核性。
