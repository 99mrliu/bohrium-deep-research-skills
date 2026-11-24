# 在线核查与降级语义（online_verification）

> 本政策规定 verify_corpus.py `--online`（V8）的行为边界。**离线是常态**：
> 评测环境不保证外网连通，本 skill 的一切默认结论都建立在本地一致性核验之上。

## 1. V8 的行为约定

- 仅对**本地语法合法**的 DOI（V2 通过）发起 Crossref 查询：
  `https://api.crossref.org/works/<doi>`，urllib 请求，timeout 5 秒，
  带可识别的 User-Agent。
- 命中且元数据一致 → checks_passed 记 `V8(verified_online)`，
  verification_scope 升级为 `online`。
- 命中但 title（规范化相似度 < 0.90）或 year 与本地记录冲突 → state 升级为
  suspicious，理由记 `V8: Crossref 命中但元数据冲突`。
- 网络失败、超时、HTTP 错误、响应不可解析 → 该记录 online_check=`unavailable`，
  理由中如实记录异常类型；**绝不因联网失败崩溃，也绝不把失败粉饰为成功**。

## 2. 降级语义（纪律条款）

1. **离线时结论限定为"本地一致性核验"**：report 中 online_check=`disabled`
   或 `unavailable` 时，verified 状态只意味着"通过 V1–V7 本地规则"，
   不是"已被外部数据库证实"。result.json.uncertainty 必须写明这一点。
2. **"快照中查不到"不等于伪造证据**：Crossref 未覆盖全部文献类型（预印本、
   中文期刊、会议论文收录不全），查询 404 或网络失败都不能作为伪造判据。
   伪造嫌疑只能来自本地可复核信号（V2 语法非法、V3 年份越界等），且一律
   只标 suspicious、不标 fake。
3. **联网结果只是增量证据**：在线核查可以提升置信（verified_online）或追加
   嫌疑（元数据冲突），但不推翻本地规则的判定；两者冲突时在 uncertainty 中
   并列呈现，交由人工裁决。
4. **失败要留痕**：online_errors 数组逐条记录 `<记录id>: <异常>`；
   report 级 online_check 取 `ok / partial / unavailable / disabled` 之一，
   任何一条失败都不得静默吞掉。

## 3. 实用指引

- 默认离线运行（不带 `--online`），保证 900 秒预算内确定性完成；
  仅在环境确认可联网且语料含大量可疑 DOI 时启用 `--online`。
- Crossref 请求为逐条串行，语料大时注意耗时（每条约 1–5 秒）；
  超预算风险出现时优先放弃在线核查，保本地核验与交付物完整。
- 评测快照环境下网络通常不可用：此时 `--online` 的预期结果就是
  online_check=`unavailable` 且 exit 码不受影响——这是特性，不是故障。
