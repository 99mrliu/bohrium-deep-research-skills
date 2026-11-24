# 归并裁决报告（identity-merge-court）

- 候选组总数: 10
- merge: 7  keep_separate: 2  human_queue: 1
- 记录数: 21 → 13
- 重定向条目: 8

## G001 — merge
- 成员: R001, R002, R003
- canonical: R001（被吸收: R002, R003）
- 证据分级: strong
  - [strong] same_doi: 规范化 DOI 相同: 10.55555/jnmc.2024.001
  - [moderate] same_title: 规范化题名相同（坐标一致数=3/3）
  - [strong] same_doi: 规范化 DOI 相同: 10.55555/jnmc.2024.001
  - [moderate] same_title: 规范化题名相同（坐标一致数=3/3）
  - [strong] same_doi: 规范化 DOI 相同: 10.55555/jnmc.2024.001
  - [moderate] same_title: 规范化题名相同（坐标一致数=3/3）
- 裁决理由: M1：三条记录规范化 DOI 完全一致（仅大小写/前缀差异，R003 从 url 提取同一 DOI），书目坐标（年/卷/期/页）规范化后一致，确认为同一文献的跨库重复；canonical 取字段最全的 Crossref 记录 R001，保留 R002 的 PMID 与 R003 的机构信息。
- 逐字段冲突表:
  - title（规范化一致）: R001='Neural Circuit Motifs for Adaptive Motor Control'; R002='Neural circuit motifs for adaptive motor control'; R003='Neural Circuit Motifs for Adaptive Motor Control'
  - pages（规范化一致）: R001='210–229'; R002='210-229'
  - doi（规范化一致）: R001='10.55555/JNMC.2024.001'; R002='10.55555/jnmc.2024.001'; R003='[from url] https://doi.org/10.55555/JNMC.2024.001'
- exception list（已并入 canonical 但需人工抽查的字段）:
  - title: canonical='Neural Circuit Motifs for Adaptive Motor Control' vs R002='Neural circuit motifs for adaptive motor control'
  - pages: canonical='210–229' vs R002='210-229'

## G002 — merge
- 成员: R004, R005
- canonical: R005（被吸收: R004）
- 证据分级: moderate
  - [moderate] same_title: 规范化题名相同（坐标一致数=3/3）
- 裁决理由: 规范化题名完全相同（仅大小写与冒号差异），缺 DOI 但坐标三重佐证（同第一作者 Kowalski、同年 2023、同容器同卷）， corroboration 充分；canonical 取含页码的出版方记录 R005。
- 逐字段冲突表:
  - title（规范化一致）: R004='Attention is not all you need: revisiting recurrent inductive biases'; R005='Attention Is Not All You Need Revisiting Recurrent Inductive Biases'
- exception list（已并入 canonical 但需人工抽查的字段）:
  - title: canonical='Attention Is Not All You Need Revisiting Recurrent Inductive Biases' vs R004='Attention is not all you need: revisiting recurrent inductive biases'

## G003 — merge
- 成员: R006, R007
- canonical: R007（被吸收: R006）
- 证据分级: moderate
  - [moderate] author_year_title_jaccard: 同第一作者姓(nakamura)+同年(2022)+题名 token Jaccard=0.889
- 裁决理由: 同第一作者 Nakamura、同年 2022、题名 token Jaccard=0.889（正式版多副标题 a review），且容器与卷完全一致，moderate 证据成立；canonical 取带页码的 R007，题名差异入 exception list 备查。
- 逐字段冲突表:
  - title（规范化不一致）: R006='Uncertainty quantification for graph neural network force fields'; R007='Uncertainty quantification for graph neural network force fields: a review'
- exception list（已并入 canonical 但需人工抽查的字段）:
  - title: canonical='Uncertainty quantification for graph neural network force fields: a review' vs R006='Uncertainty quantification for graph neural network force fields'

## G004 — merge
- 成员: R008, R009
- canonical: R009（被吸收: R008）
- 证据分级: strong
  - [weak] same_title: 规范化题名相同（坐标一致数=1/3）
  - [strong] preprint_published: 预印本 R008（arXiv:2401.98765） ↔ 正式版 R009；材料内 note 字段声明版本关系
- 裁决理由: M4：预印本 R008（arXiv:2401.98765v2）与正式版 R009 题名相同、作者相同；材料内 note 字段明确声明版本关系并给出正式版 DOI 10.55555/SPLS.2025.017，证据 strong。并入正式版 R009，保留谱系（preprint id、版本关系、重定向），年份差 2024/2025 属预印本-正式版正常现象，入 exception list。
- 逐字段冲突表:
  - year（规范化不一致）: R008=2024; R009=2025
  - type（规范化不一致）: R008='preprint'; R009='inproceedings'
- exception list（已并入 canonical 但需人工抽查的字段）:
  - year: canonical=2025 vs R008=2024
  - type: canonical='inproceedings' vs R008='preprint'
- 谱系:
  - R008（arXiv:2401.98765, 2024）--published_version_of--> R009；重定向 R008 -> R009；证据: 材料内 note 字段声明版本关系

## G005 — merge
- 成员: R010, R011
- canonical: R011（被吸收: R010）
- 证据分级: strong
  - [strong] same_doi: 规范化 DOI 相同: 10.55555/cip.2023.005
  - [strong] translation_pair: R011 的 translation_of 字段指向 R010，且共享规范化 DOI
- 裁决理由: 中英题名对：R011 的 translation_of 字段指向 R010，且共享规范化 DOI（仅大小写差异），M1 成立；容器与作者差异为中英译名/罗马化所致，不属书目坐标冲突，入 exception list；canonical 取字段更全的 R011，保留 R010 的中文原始题名为 title_original。
- 逐字段冲突表:
  - title（规范化不一致）: R010='面向低资源场景的医疗文本结构化抽取方法'; R011='Structured Extraction of Medical Texts in Low-Resource Scenarios'
  - container（规范化不一致）: R010='中文信息学报'; R011='Journal of Chinese Information Processing'
  - doi（规范化一致）: R010='10.55555/CIP.2023.005'; R011='10.55555/cip.2023.005'
  - first_author_family（规范化不一致）: R010='王'; R011='Wang'
- exception list（已并入 canonical 但需人工抽查的字段）:
  - title: canonical='Structured Extraction of Medical Texts in Low-Resource Scenarios' vs R010='面向低资源场景的医疗文本结构化抽取方法'
  - container: canonical='Journal of Chinese Information Processing' vs R010='中文信息学报'

## G006 — merge
- 成员: R012, R013
- canonical: R013（被吸收: R012）
- 证据分级: strong
  - [strong] same_doi: 规范化 DOI 相同: 10.55555/jos.2024.088
- 裁决理由: M1：CNKI 与 Crossref 导出共享规范化 DOI（仅大小写差异），卷期页规范化后一致（连字符 vs en dash 为格式差异）；题名/刊名/作者差异为中英导出惯例，入 exception list；canonical 取含 URL 的 Crossref 记录 R013。
- 逐字段冲突表:
  - title（规范化不一致）: R012='多模态情感分析中的跨语言对齐研究'; R013='Cross-lingual alignment for multimodal sentiment analysis'
  - container（规范化不一致）: R012='软件学报'; R013='Ruan Jian Xue Bao (Journal of Software)'
  - pages（规范化一致）: R012='3561-3574'; R013='3561–3574'
  - doi（规范化一致）: R012='10.55555/JOS.2024.088'; R013='10.55555/jos.2024.088'
  - first_author_family（规范化不一致）: R012='陈'; R013='Chen'
- exception list（已并入 canonical 但需人工抽查的字段）:
  - title: canonical='Cross-lingual alignment for multimodal sentiment analysis' vs R012='多模态情感分析中的跨语言对齐研究'
  - container: canonical='Ruan Jian Xue Bao (Journal of Software)' vs R012='软件学报'
  - pages: canonical='3561–3574' vs R012='3561-3574'

## G007 — merge
- 成员: R014, R015
- canonical: R015（被吸收: R014）
- 证据分级: strong
  - [strong] same_doi: 规范化 DOI 相同: 10.55555/per.2021.004
  - [moderate] same_title: 规范化题名相同（坐标一致数=3/3）
- 裁决理由: M1：EndNote 导出把 DOI 放在 url 字段，规范化后与 Crossref 记录 R015 的 DOI 完全一致，年/卷/页一致；canonical 取带显式 doi 字段的 R015。
- 逐字段冲突表:
  - title（规范化一致）: R014='Soil microbiome responses to permafrost thaw'; R015='Soil Microbiome Responses to Permafrost Thaw'
  - doi（规范化一致）: R014='[from url] https://doi.org/10.55555/PER.2021.004'; R015='10.55555/per.2021.004'
- exception list（已并入 canonical 但需人工抽查的字段）:
  - title: canonical='Soil Microbiome Responses to Permafrost Thaw' vs R014='Soil microbiome responses to permafrost thaw'

## G008 — keep_separate
- 成员: R016, R017
- 证据分级: weak
  - [weak] author_year_title_jaccard: 同第一作者姓(zhang)+同年(2024)+题名 token Jaccard=0.818
- 裁决理由: M5 同名作者保护：R016（Zhang, Wei）与 R017（Zhang, Lei）同姓同年、题名仅一词之差（flow vs speed），但作者给定名不同、共同作者不同、容器/卷/页/DOI 全异，是同名姓作者的两篇不同文献，显式保护不予合并。
- 逐字段冲突表:
  - title（规范化不一致）: R016='Deep learning models for short term urban traffic flow prediction'; R017='Deep learning models for short term urban traffic speed prediction'
  - container（规范化不一致）: R016='IEEE Open Journal of Intelligent Transportation'; R017='Transportation Research Procedia'
  - volume（规范化不一致）: R016='5'; R017='71'
  - pages（规范化不一致）: R016='100–112'; R017='220–231'
  - doi（规范化不一致）: R016='10.55555/OJIT.2024.011'; R017='10.55555/TRP.2024.055'

## G009 — human_queue
- 成员: R018, R019
- 证据分级: strong
  - [strong] same_doi: 规范化 DOI 相同: 10.55555/abl.2021.033
  - [moderate] same_title: 规范化题名相同（坐标一致数=2/3）
- 裁决理由: M2：两记录共享规范化 DOI 10.55555/abl.2021.033，但年份（2021 vs 2022）与页码（77–88 vs 177–188）规范化后冲突，禁止自动并；升级人工核查：解析 DOI 落地页核对真实年份与页码，判定是 R019 导出错误还是 DOI 错配。
- 逐字段冲突表:
  - year（规范化不一致）: R018=2021; R019=2022
  - pages（规范化不一致）: R018='77–88'; R019='177–188'
  - doi（规范化一致）: R018='10.55555/ABL.2021.033'; R019='10.55555/abl.2021.033'
- 后续: 人工核查路径：核对出版方页面/DOI 解析结果后再判；在结果中显式登记为未决不确定性，不得静默跳过。

## G010 — keep_separate
- 成员: R020, R021
- 证据分级: weak
  - [weak] same_title: 规范化题名相同（坐标一致数=0/3）
- 裁决理由: M3：两篇仅规范化题名相同（Digital twins in manufacturing），第一作者、年份、容器、卷、页、DOI 全部不同，无任何 corroboration，属短通用题名的题名撞车，证据 weak，保持分离。
- 逐字段冲突表:
  - title（规范化一致）: R020='Digital twins in manufacturing'; R021='Digital Twins in Manufacturing'
  - year（规范化不一致）: R020=2020; R021=2023
  - container（规范化不一致）: R020='Journal of Industrial Informatics Quarterly'; R021='Manufacturing Systems Letters'
  - volume（规范化不一致）: R020='4'; R021='2'
  - pages（规范化不一致）: R020='10–19'; R021='55–63'
  - doi（规范化不一致）: R020='10.55555/JIIQ.2020.002'; R021='10.55555/MSL.2023.009'
  - first_author_family（规范化不一致）: R020='Rocha'; R021='Asante'
