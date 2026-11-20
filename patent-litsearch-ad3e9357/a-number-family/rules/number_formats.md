# 号码格式规则（rules/number_formats.md）

与 `scripts/patent_numbers.py` 的 PATTERNS 表同步。规范化流程：大写 → 去分隔符（空格 `.` `,` `/` `-` `'` `(` `)`）→ 按模式表顺序匹配 → 多命中给歧义警告，不静默选择。

## 模式表

| 模式 | 类型 | 紧凑格式 | 规范键示例 | 说明 |
|-|-|-|-|-|
| US 申请 | app | US + 2 位 series(01–18) + 6 位 | US-app-15654321 | 裸 8 位与授权号歧义，见下 |
| US 授权 | grant | US + 7–8 位 + kind(B1/B2/A/E/H/P1) | US-grant-10293847 | 序号 zfill 到 8 位 |
| US 再颁/设计/植物 | grant | US + RE5位/D6-7位/PP5-6位 | US-grant-D812345 | 前缀保留 |
| US 公开 | pub | US + 4 位年 + 7 位 + kind(A1/A2/A9) | US-pub-20200123456 | 无 kind 不匹配 |
| WO 公开 | pub | WO + 4 位年 + 5–6 位 + kind(A/A1/A2/A3/A8/A9) | WO-pub-2019123456 | 序号 zfill 到 6 位 |
| EP 公开 | pub | EP + 7 位 + kind | EP-pub-1234567 | |
| EP 申请 | app | EP + 8 位 + 可选 .校验位 | EP-app-10123456.7 | |
| CN 公开/授权 | pub | CN + 8–9 位 + kind(A/B/C/U/Y/S) | CN-pub-110123456 | |
| CN 申请 | app | CN + 4 位年 + 7–8 位 + 可选 .校验位 | CN-app-201810123456.7 | |
| JP 公开 | pub | JP + 4 位年 + 6 位 + kind | JP-pub-2020123456 | |
| JP 授权 | grant | JP + 7 位 + kind | JP-grant-6543210 | |
| KR 公开/授权 | pub | KR + 10/20 + 4 位年 + 5–7 位 | KR-pub-1020200012345 | |

## 歧义纪律

- US 裸 8 位（前两位 01–18）同时命中申请与授权模式：主解释为申请号，`alternatives` 列出授权号解释，`confidence=low`，必须提示人工核对著录项。
- 查询命中"同序号不同种类"（如 US-grant-10293847 与 US-pub-20180293847 同现于一条记录）时列入 `related_hits`，是否同一专利以著录项（申请号、优先权）为准，不得仅凭序号断言。

## 置信度

`high`=唯一命中且带 kind code；`medium`=唯一命中无 kind；`low`=歧义。置信度写入索引与结果，供下游风险判断使用。
