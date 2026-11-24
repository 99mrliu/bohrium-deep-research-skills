# 缺陷分类法（R1–R8）— ppt-redteam-tribunal

所有规则由 `scripts/redteam_scan.py` 确定性执行，机器可判，不依赖模型主观判断。
severity 含义：**error** 阻塞收敛门禁；**warn** 不阻塞，但必须入账并处置
（fix 或 disposition），不得静默删除。

## R1 数值漂移/幻觉（error）
- **定义**：页面文本（标题/bullet/claim）中出现的「数字+单位」token 不在
  facts.json 的 numeric_anchors 事实池中。
- **判定**：单位表精确匹配（空白归一化后）。事实池来自论文 PDF 分页文本。
- **典型失败**：模型把 92.4 % 记成 99.9 %；把 37 ms 改写成 "about 40 ms"。
- **修复**：删除无出处数值 bullet（宁删不假），或替换为事实池锚点并补逐字 quote。
  `apply_fixes.py` 可自动删除。

## R2 悬空引用（error）
- **定义**：slides 中引用（figures[] 或正文提及）的 Figure N / Table N 不在
  caption 索引中。
- **典型失败**：论文只有 Figure 1，deck 却引用 "Figure 2 shows the ablation"。
- **修复**：删除该引用，或降级为不含编号的文字描述（"the cited figure"）。
  `apply_fixes.py` 可自动处理。

## R3 引文不逐字（error）
- **定义**：claim 的 source.quote（空白归一化后）不能在论文分页文本拼接结果中
  逐字命中。
- **典型失败**：quote 是模型"转述"的句子，看着像原文实则不存在。
- **修复**：人工从 facts.json pages 中复制可逐字命中的句子替换。
  **机器不可修**（机器无法知道该 claim 对应论文哪句话），由 Agent 处理后
  `tribunal_log.py --fix` 销账。

## R4 栏目名标题（warn）
- **定义**：标题是 "Experimental Results" 式栏目名而非主张句。
- **启发式**：≤5 词、无数字、词尾落在通用栏目词表
  （results/method/background/conclusion/overview/discussion 等）。
- **典型失败**：每页标题都是章节名，听众抓不到结论。
- **修复**：改写为句子式主张标题（带数值锚点或结论性动词），人工修复。

## R5 段落搬运（warn）
- **定义**：内容页序与论文章节顺序同构——页数与章节数相等、角色互不相同、
  各页引用页码严格递增。
- **典型失败**：Introduction→Method→Experiments→Conclusion 逐节复制，
  没有面向受众的叙事重排。
- **修复**：按汇报叙事线重排（结论先行、合并过渡页、增加动机页）。
- **说明**：这是简化启发式，宁缺勿滥；误判可走 disposition。

## R6 备读者复读（warn）
- **定义**：备注与页面文字（标题+bullets）的词集 Jaccard 相似度 > 0.6。
- **典型失败**：把 bullet 原句粘进备注，演讲者备注失去增量价值。
- **修复**：备注改写为讲者提示（时间分配、强调点、过渡话术、应答预案）。

## R7 局限缺失（error）
- **定义**：论文含 limitation/limitations/future work 线索
  （facts.json limitation_hints 非空），但 deck 无 role=limitations 页面。
- **典型失败**：只讲贡献不讲局限，学术汇报完整性缺陷。
- **修复**：新增 limitations 页，逐字引用论文 limitation 句。

## R8 示意图当数据（warn）
- **定义**：role=results 页面引用的图，其 caption 含 schematic/diagram/
  illustration/architecture/overview 关键词。
- **典型失败**：拿方法框架图充当实验结果证据。
- **修复**：换用真正的数据图；若该图确实承载数据结论，走 disposition
  accept-risk 并在理由中说明。

## 处置纪律
- 每条 finding 终态只能是 fixed 或 dispositioned（accept-risk / reject 需理由），
  或保持 open（仅 warn 允许带着 open 过门禁）。
- 台账禁止物理删除条目；所有操作追加 history（逻辑序号排序，不记墙钟时间）。
