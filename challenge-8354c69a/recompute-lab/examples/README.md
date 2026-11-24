# 最小示例（合成示例，非正式案例结果）

演示双通道复算与 claims 审计。输入为**合成数据**（一条位移-载荷曲线），
claims.json 故意包含一个正确数值与一个错误数值。

## 运行

```bash
cd examples
python3 make_synthetic_input.py --outdir ./demo
# 直接审计（也会自动生成 claims.json 指向 demo 数据）
python3 ../scripts/run_lab.py --input ./demo/input --work ./demo/work \
    --output ./demo/output --claims ./demo/input/claims.json
echo "exit=$?"   # 预期 exit=1：存在 TOLERANCE_MISS，deliverable=false
cat demo/work/claims_audit.json
```

## 预期（captured 于 expected/）

- 全部账本 AGREE（合成数据无病态）；
- claims 审计：C1(mean, 正确值) → CONFIRMED；C2(max, 故意写错) → TOLERANCE_MISS；
- run_lab 以 exit 非零/result.json status=partial 演示「带错不得交付」规则。

`expected/` 为一次真实本地运行的输出副本。
