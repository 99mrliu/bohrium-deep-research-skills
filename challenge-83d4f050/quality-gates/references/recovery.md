# Recovery, determinism and failure injection

## 从 checkpoint 恢复

始终给 `--resume` 传入与原运行相同的 case/work/output。没有 manifest、case_id 不同或文件 hash 不一致都不能假装可恢复。

1. 启动先把 result 降为 partial，防止恢复中的故障被读成旧 complete。
2. 根据 completed_stages 找到最后成功阶段。
3. 若 exported 已完成但 PNG/PDF 缺失，回退到 exported；renderer 的 SVG checkpoint 和源 specification 保留。
4. 重跑 exported/audited，而不是手写一个假“success”checkpoint。result supporting files 会重建，因此缺字段可在 audited 修复。
5. 将原因和 resume_from 写入 recoveries/recovery.json。恢复到 audited 后仍需 native visual attestation。

## 两种合同故障

```bash
python3 scripts/runner.py run ... --inject-failure missing-png
# 预期 3，result/manifest=failed，PNG 确实缺失。
python3 scripts/runner.py run ... --resume
# 预期 0，真实重导 PNG，回到 audited/partial。

python3 scripts/runner.py run ... --inject-failure missing-result-field
# 预期 3，candidate result 确实缺 sources。
python3 scripts/runner.py run ... --resume
# 预期 0，result 重建，所有动态字段重新验收。
```

故障注入仅用于 synthetic validation，正式科学运行不能使用。`--resume` 不携带 injection，不能无限重复制造同一个故障后宣称成功。

## 科学失败

把 scientific_review verdict 设为 fail，observed 即返回 4。合同/文件问题返回 3。两类失败不可混成同一个“所有非零即通过”的测试；验证器分别断言。

## 确定性

验证器在同一 case 与 output 根下，删除并重建 clean work，再完整执行 fresh run。对 output 下所有普通文件（包括 result、manifest、audit、SVG、PNG、PDF、sources 等）计算 SHA-256 并比较整个路径→hash map。

采用确定性数据序列化，不包含 wall clock、临时 staging 名、run UUID 或机器相关绝对 work path。若改变输入、renderer 或 PyMuPDF 版本，输出 hash 可以合理地改变；这不是随机不确定性的证明，应在局限中注明依赖版本。resume 历史与从未失败的 fresh run 可以不同，因为恢复历史本身是交付证据；确定性比较针对两次相同 fresh 成功运行。

## 恢复失败

resume 本身遇到合同错误返回 3，科学错误返回 4，其他用法/内部错误返回 2。输出 error/recovery_command，保留 manifest 供诊断；不得把“继续运行”解释为“已达到 delivered”。
