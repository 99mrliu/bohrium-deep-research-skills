# examples — 合成示例（非正式案例结果）

> 本目录所有内容均为**合成示例，非正式案例结果**，仅用于演示与回归测试 baseline-parity 的三个脚本。

## 结构

- `case/` — 合成输入材料：
  - `config_ours.yaml`：本文方法配置（epochs=200）；
  - `config_base.yaml`：自复现基线 ResNet-50 配置（epochs=50，故意与本文不一致，用于演示 parity 违规）；
  - `results.log`：两个 run 各一条最终指标（均单次运行，用于演示“缺重复次数”缺口）；
  - `refs.md`：VGG-16 [1] 的原报值引用（标注“非同等条件”）；
  - `draft.md`：对照实验草稿，含一句无支撑论断“我们的方法显著优于所有基线”。
- `run_example.sh`：一键依次运行 `baseline_mine.py` → `parity_check.py` → `claim_check.py`。
- `expected/`：运行产物（baselines/parity/claims_report 的 json+md）。

## 运行

```bash
bash examples/run_example.sh
```

## 预期结果

1. `baseline_mine`：识别两个基线——`ResNet-50`（自复现，关联指标 accuracy=91.10）与 `VGG-16`（原报，引用 [1]，指标 accuracy 71.3）；
2. `parity_check`：报出 `epochs` 预算不一致（ours=200 vs resnet50=50），以及统计协议三缺口（缺重复次数、缺均值±标准差、缺显著性检验）；
3. `claim_check`：抓出 draft.md 第 5 行“显著优于所有基线”为无支撑论断并给出降级建议；脚本退出码为 1（`run_example.sh` 捕获该码并正常结束）。
