# 交付验收门报告

- 结论：**PASS**（退出码 0）
- case_id：syn-b-deliverline-001
- 检查总数：34；通过 34；失败 0

## 失败项

（无）

## 警告

（无）

## 全部检查

- ✅ `case_id_match` — case.json case_id='syn-b-deliverline-001', result case_id='syn-b-deliverline-001'
- ✅ `field_present:case_id`
- ✅ `field_type:case_id` — 期望类型 string，实际 str（值 'syn-b-deliverline-001'；注意 boolean 不可当 integer）
- ✅ `required_nonempty:case_id` — 必填字符串去空白后为空
- ✅ `field_present:status`
- ✅ `field_type:status` — 期望类型 string，实际 str（值 'complete'；注意 boolean 不可当 integer）
- ✅ `required_nonempty:status` — 必填字符串去空白后为空
- ✅ `field_enum:status` — 值 'complete' 不在枚举 ['complete', 'partial'] 内
- ✅ `field_present:title`
- ✅ `field_type:title` — 期望类型 string，实际 str（值 '高效稳定钙钛矿光伏组件封装技术——成果转化推介书'；注意 boolean 不可当 integer）
- ✅ `required_nonempty:title` — 必填字符串去空白后为空
- ✅ `field_present:summary`
- ✅ `field_type:summary` — 期望类型 string，实际 str（值 '面向产业投资人的钙钛矿光伏组件封装技术成果转化推介书：涵盖成果概述、知识产权与成熟度、市场竞争分析、转化方案（作价入股+里程碑许可）与风险对策，附 HTML 与分页 SVG 可检查预览。'；注意 boolean 不可当 integer）
- ✅ `required_nonempty:summary` — 必填字符串去空白后为空
- ✅ `field_present:deliverables`
- ✅ `field_type:deliverables` — 期望类型 array，实际 list（值 ['preview.html', 'preview_page1.svg', 'preview_page2.svg', '../manuscript.md']；注意 boolean 不可当 integer）
- ✅ `required_nonempty:deliverables` — 必填数组为空
- ✅ `field_present:word_count`
- ✅ `field_type:word_count` — 期望类型 integer，实际 int（值 814；注意 boolean 不可当 integer）
- ✅ `field_present:reviewed`
- ✅ `field_type:reviewed` — 期望类型 boolean，实际 bool（值 True；注意 boolean 不可当 integer）
- ✅ `field_present:confidence`
- ✅ `field_type:confidence` — 期望类型 number，实际 float（值 0.85；注意 boolean 不可当 integer）
- ✅ `field_present:limitations`
- ✅ `field_type:limitations` — 期望类型 array，实际 list（值 []；注意 boolean 不可当 integer）
- ✅ `field_present:notes`
- ✅ `field_type:notes` — 期望类型 string，实际 str（值 '合成示例运行产物：由保底脚手架回填真实内容；word_count=814 由程序实测；status=complete 且 limitations 为空，已经过 deliverable_gate 验收。'；注意 boolean 不可当 integer）
- ✅ `required_nonempty:notes` — 必填字符串去空白后为空
- ✅ `artifact_exists:deliverables=preview.html` — 解析路径 expected/preview.html 不存在（base_dir=expected）
- ✅ `artifact_exists:deliverables=preview_page1.svg` — 解析路径 expected/preview_page1.svg 不存在（base_dir=expected）
- ✅ `artifact_exists:deliverables=preview_page2.svg` — 解析路径 expected/preview_page2.svg 不存在（base_dir=expected）
- ✅ `artifact_exists:deliverables=../manuscript.md` — 解析路径 expected/../manuscript.md 不存在（base_dir=expected）
- ✅ `status_value` — status='complete'，应为 complete 或 partial
- ✅ `status_limitations_consistency` — status=complete 时 limitations 必须为空数组，实际 []
