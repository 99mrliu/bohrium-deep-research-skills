# digest — case-plants-synthetic（agent 只需读本文件）

## 发现了什么
- 主数据源：`plants.csv`（csv），行数 29 → 清洗后 27（重复剔除 2 行）
- 缺失（report_and_exclude，按变量有效 n）：{'height_cm': 2, 'notes': 1}
- 异常值（1.5×IQR，只标记）：{'height_cm': 1}
- 跨源一致性：consistent_with_type_coercion（plants.csv ↔ plants.db，值不一致 0 处）
- ⚠ SQLite numeric-in-text 列（TEXT affinity 存数值）：height_cm
- 分组列默认：group；推断变量数：1

## 待确认裁决（5 项；确认默认值则无需任何操作）
- **group_column**：分组列选择 ｜ 默认：`group` ｜ 理由：auto(score=7: 列名命中分组提示词+文本列+唯一值数=2≤10)
  - 覆盖命令：`python3 ${SKILL_DIR}/scripts/pipeline_a.py decide --work-dir /app/work --output-dir /app/output --key group_column --value <新值> --reason "理由"`
- **alpha**：显著性水平 ｜ 默认：`见 constraints（默认 0.05）` ｜ 理由：来自 case.json constraints；任务另有约定时覆盖
  - 覆盖命令：`python3 ${SKILL_DIR}/scripts/pipeline_a.py decide --work-dir /app/work --output-dir /app/output --key alpha --value <新值> --reason "理由"`
- **primary_source**：主数据源（csv/db） ｜ 默认：`csv` ｜ 理由：默认 CSV 优先；跨源不一致时可切换为 db 重跑
  - 覆盖命令：`python3 ${SKILL_DIR}/scripts/pipeline_a.py decide --work-dir /app/work --output-dir /app/output --key primary_source --value <新值> --reason "理由"`
- **outlier_action**：异常值处置（flag/drop） ｜ 默认：`flag` ｜ 理由：默认只标记不删除；确认录入错误才可 drop 并必须写理由
  - 覆盖命令：`python3 ${SKILL_DIR}/scripts/pipeline_a.py decide --work-dir /app/work --output-dir /app/output --key outlier_action --value <新值> --reason "理由"`
- **variables**：推断变量白名单（逗号分隔） ｜ 默认：`全部数值变量` ｜ 理由：task.md 聚焦特定指标时可收窄，减少无关比较
  - 覆盖命令：`python3 ${SKILL_DIR}/scripts/pipeline_a.py decide --work-dir /app/work --output-dir /app/output --key variables --value <新值> --reason "理由"`

覆盖后执行：`python3 ${SKILL_DIR}/scripts/pipeline_a.py finalize --work-dir /app/work --output-dir /app/output`
