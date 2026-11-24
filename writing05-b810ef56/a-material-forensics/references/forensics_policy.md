# 取证策略与异常矩阵（Forensics Policy）

## 1. 来源分级口径

| 级别 | 判据 | 写作中的使用 |
|---|---|---|
| OK | 提取成功、字符数 ≥100、乱码率 ≤1% | 可支撑事实句；摘录可逐字定位并回填真实页码 |
| DEGRADED | 提取成功但字符数 <100、乱码率 >1%，或经 OCR 获得 | 只能支撑带〔材料质量受限〕标注的表述；结论性表述不得单独依赖它 |
| UNUSABLE | 无提取器、提取失败、文件损坏 | 不得支撑任何事实句；在 limits 说明需要什么人工处置（如提供可读版本） |

## 2. 登记字段规范（sources_registry.json）

每个文件一条记录：`file`（相对路径）、`bytes`、`sha256`（完整 64 位）、
`format`、`role`（case-metadata / material）、`status`、`reason`、
`text_path`、`pages`、`chars`。证据表中引用来源时写
`file` + sha256 前 8 位，例：`paper_a.pdf#a1b2c3d4`，使读者能核对
引用的是同一份文件。

## 3. 摘录定位失败的常见原因与修正

| 现象 | 原因 | 修正 |
|---|---|---|
| 肉眼可见但 found=false | 跨页断行：quote 含 `\f` | 缩短 quote 到单页内，或拆成两条证据 |
| found=false 且文本来自 PDF | `pdftotext -layout` 引入多余空格对齐 | 规范化（NFKC+折叠空白）后重试；脚本已内置 |
| found=false 且含引号/破折号 | 全半角差异 | 重新从提取文本中复制，不凭记忆重打 |
| 页码为空 | 该来源无 pages.json | 文本类单页来源页码恒为 1；PDF 必有索引 |
| 多处命中 | quote 过短或原文重复 | 加长 quote 至唯一命中，或在证据表记全部命中页 |

## 4. 异常矩阵

| 异常 | 处置 | result.json 体现 |
|---|---|---|
| `pdftotext` 不在 PATH | 该 PDF 记 UNUSABLE，流程继续 | limits：PDF 不可读 + 需要的工具 |
| 零可用来源（退出码 1） | 停止写作，产出 honest-failed | status=failed，deliverable 为空或说明，limits 写明原因 |
| case.json 无 `case_id` | result.json 填 `"unknown"` | limits 记录该缺陷 |
| case.json 声明的材料缺失 | 不补造内容 | limits：缺失清单 + 对写作范围的影响 |
| 存在未声明的材料 | 照常取证登记 | change_log 记录 |
| 材料语言/学科与任务不符 | 如实记录，不据此补造数据 | uncertainty 说明 |
| 提取文本与任务要求的关键数据缺失 | 论断标〔待证〕，不写入事实句 | uncertainty + limits |

## 5. 诚实 partial 的判定

- 任一 output_contract 键无法完成 → `status` 不得为 `complete`；
- partial 的 result.json 必须在 `limits` 逐项说明：缺什么、为什么、
  需要什么输入或人工确认才能补齐；
- failed 只允许在零可用来源或输入契约本身损坏时使用，且仍要交付
  完整取证报告作为证据。
