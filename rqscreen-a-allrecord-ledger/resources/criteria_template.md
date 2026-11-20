# 筛查条款（criteria.json）模板与修订守则

## 模板

```json
{
  "year_from": 2022,
  "year_to": 2025,
  "include_terms": ["perovskite", "passivation", "ammonium"],
  "min_term_hits": 1,
  "exclude_terms": ["photocatalysis"],
  "exclude_types": ["review", "perspective", "editorial"],
  "require_device_data": false,
  "subquestion_map": {
    "SQ-1 界面钝化": ["interface", "interfacial", "capping layer"],
    "SQ-2 晶界钝化": ["grain boundary", "grain-boundary"]
  }
}
```

## 修订守则（Agent 核对 criteria.auto.json 时）

1. **年份窗**以 research_question/case.json constraints 为准；问题未提年份则删除 year_from/year_to，不臆造窗口。
2. **纳入词**控制在 5–15 个：对象词（材料/体系）、机制词（现象/干预）、方法词各留 2–4 个；去掉"method/results/study"类无区分度词。
3. **排除词**只放与研究问题明确互斥的主题；宁缺毋滥，防止误杀边界文献。
4. **exclude_types**：题目要求"原始研究"时，把 review/perspective/editorial/comment 列入；题目未限定类型则留空。
5. **subquestion_map**：按问题拆解出的子问题各配 2–5 个判别词；作用是台账自动标注 SQ 归属，宁少勿错。
6. 改完保存为 `criteria.json`（与 auto 草案分开），重跑 `screen.py --criteria ...`。
