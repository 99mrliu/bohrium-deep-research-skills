---
name: kbqa-ingest-forensics
description: 科研知识库问答的"上游数据真实性"工作流——先对输入资料库做取证级编目（逐文件 SHA-256、七态可读性、字节级重复识别、别名与版本谱系、行政备注优先的当前版本裁定），再用独立复核脚本重算哈希验证编目与磁盘一一对应，产出机器可核验的编目金标准与修复台账；后续一切问答、引用和版本判断都必须落到编目记录上，编目外的文件不得作为证据。Use when a task gives a messy scientific document library (duplicates, aliases, historical versions, administrative version notes) in /input and requires verifiable organization, metadata, version relations or cited QA (编目, 版本关系, 元数据, 重复文件, 修复台账, 证据回链, /input/case.json, result.json).
---

# 上游数据真实性取证编目（kbqa-ingest-forensics）

重心在**输入侧**：回答任何问题之前，先把"库里到底有什么、哪个版本有效、
哪些文件不可读"变成机器可核验的事实。本 Skill 的交付中心是编目金标准
（catalog.json）+ 版本谱系（lineage.json）+ 修复台账（repair_ledger.json），
问答只是编目之上的应用；编目未覆盖或核验不通过的内容一律不得引用。

## 何时使用 / 不适用

适用：平台给出 `/input/case.json` + `/input/task.md` 与真实资料库（跨目录、
多格式、含重复副本与历史版本、可能有行政版本备注），要求盘点文件、维护
元数据/版本关系、输出可检索可交接的清单，或在其上做带来源问答。
不适用：单一干净文件的纯阅读理解（编目开销大于收益，仍可按本流程跑，
但可在 result.json 注明 library_trivial=true）。

## 运行时合同（先读再动手）

1. 先读 `/input/case.json` 与 `/input/task.md`，取出 `case_id`、问题/检索
   列表和 `output_contract`。**第一次工具调用后立刻**把骨架
   `/app/output/result.json` 落盘：`case_id` + output_contract 全部字段
   （先填空值并注明 pending）+ `status:"partial"`。之后每完成一步增量更新。
2. 工作区 `/app/work`（中间产物）；最终交付 `/app/output`：
   catalog.json、lineage.json、repair_ledger.json、catalog_report.md、
   result.json。result.json 必须含 `case_id` 与 output_contract 要求的
   全部字段，外加诚实 `status` / `sources` / `uncertainty` / `change_log`。
3. 预算约 64 次模型请求 / 900 秒：三个脚本都是确定性的、不占模型预算；
   模型预算只花在读题、基于编目作答与收尾。时间过半立即以当前编目收尾，
   未完成问题标 partial 并说明缺什么。

## 工作流（四步，脚本路径以安装位置 $SKILL=/skills/weekly-skill 为准）

```bash
SKILL=/skills/weekly-skill

# 1) 取证扫描：逐文件哈希、七态可读性、文本抽取（PDF 走 pdftotext，缺工具/无文本层如实记录）
python3 $SKILL/scripts/forensic_scan.py --input /input --work /app/work --out /app/output

# 2) 别名与版本谱系：行政备注 > 文件名版本 > mtime；每条判定带机器依据
python3 $SKILL/scripts/lineage.py --work /app/work --out /app/output

# 3) 独立复核 + 修复台账：重遍历输入、重算哈希，验证编目与磁盘一一对应
python3 $SKILL/scripts/catalog_check.py --input /input --work /app/work --out /app/output

# 4) 基于编目回答 case.json 的问题/检索请求，引用坐标 [Fxx|sha8]，
#    只引用 role=current/current_copy 且 text_status=ok 的文件；更新 result.json 收尾
```

## 问答与引用的硬性规则

- 引用坐标用编目编号：`[F07|a3f2c1d9]`（file_id + SHA-256 前 8 位），
  引文为抽取文本中的逐字片段；多版本存在时只把 current 版本当事实依据，
  引用历史版本必须明示用途（见 references/version_rules.md）。
- `text_status` 非 ok 的文件不得引用；相关事实写进 uncertainty：
  "该文件不可读/无文本层，缺 OCR 或权限"。
- 库中确无依据的问题：答案明确写"库中无依据"，uncertainty 写明缺什么
  （缺哪类文件、哪个版本、哪个字段），不得编造或凭训练知识补造。
- 编目核验（catalog_check）出现 hash_mismatch / missing_from_catalog 时，
  先重跑扫描修复编目，再作答；未修复前 result.json 只能为 partial。

## 异常与失败处置

文件不可读→记 unreadable 并继续；目录为空→catalog 正常生成（0 文件），
result.json 标 partial 并说明；行政备注与文件名版本冲突→以行政备注为准，
冲突进台账和 uncertainty；扫描中任何单文件异常只影响该文件的
text_status，脚本整体 exit 0。跳过、冲突、恢复方式全部写入
repair_ledger.json（状态 proposed/failed，不把未执行写成已执行）。

## 自查清单（交付前）

1. result.json 含 case_id 与 output_contract 全部字段？status 诚实？
2. catalog_check 的 independent_reverification 全绿（无 hash_mismatch、
   无 missing_from_catalog）？
3. 六维覆盖：文件类型、元数据字段、目录层级、重复文件、版本差异、
   权限与来源——每维有记录或在 uncertainty 说明空缺原因？
4. 每个答案断言都能落到 [Fxx|sha8] 坐标，且所引文件 text_status=ok、
   role 为 current/current_copy？
5. 换一个评审只凭 catalog.json + repair_ledger.json 能否重算哈希复核
   编目真实性？

最小调用示例见 [examples/minimal_example.md](examples/minimal_example.md)
（**合成示例**，仅说明接口与流程，非正式案例结果）。
