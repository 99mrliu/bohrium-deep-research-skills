# 独立 Oracle 的精确定义与限制

## 共同判定规则

运行器先验证明 spec 哈希，再计算 Oracle。候选 JSON 中的浮点值按十进制读入；支持 JSON number、numeric string或只含 `value` 键的单键对象。布尔、NaN、Infinity、缺失或错误类型均失败。所有容差在运行前冻结。

数值比较采用逐元素：

```
error = abs(actual - expected)
bound = abs_tolerance + rel_tolerance * max(abs(actual), abs(expected))
pass iff error <= bound
```

容差衡量候选约定输出与 Oracle 定义的差异，不是论文复现容差的自动替代。论文目标另外比较，绝不当 expected。每个试验都记录独立 expected、候选实际输出、误差和界限。

## `quadratic_roots`

### 支持域

输入 `parameters.a/b/c` 为有限十进制数，`a != 0`，`precision` 为 16–250。仅支持判别式非负的实根；其他情况是不支持的 spec，而非猜测复根格式。候选输出必须为：

```json
{"roots": [2.0, 3.0]}
```

两个根排序后比较，重根保留两个位置。额外的 `method` 等键不参与判定。

### 独立 expected

在 `decimal.localcontext` 的 spec 精度下计算 `D = b² - 4ac`。`D > 0` 时不直接用两个灾难性相消的普通公式，而采用：

```
q = -(b + sign(b)*sqrt(D))/2
r1 = q/a
r2 = c/q
```

`D == 0` 使用 `-b/(2a)` 两次；仅 `q == 0` 的边角使用普通两根公式。expected 是这套独立稳定 Decimal 解析结果，不导入或调用候选函数。

### 必做检查

1. 排序根的绝对/相对误差：`tolerances.abs`、`tolerances.rel`。
2. 每个候选根的绝对残差：`|a r²+b r+c| <= residual_abs`。
3. 缩放残差：`residual / (|a|r²+|b||r|+|c|+1) <= residual_scaled`。
4. Vieta 恒等式：两根和与 ` -b/a `、积与 `c/a` 的误差，使用根 abs/rel 容差形成的共享界。
5. `scaling_factors` 中每个非零因子实际再执行候选，将 `(a,b,c)` 同乘该因子；独立重算 expected、残差和 Vieta。根不变是变形关系，仍逐试验执行，不复用候选输出。

全部根、残差和恒等式通过，且所有进程/解析/缩放试验成功，候选才通过。该通过只支持这组输入与变形，不证明所有二次方程都正确。

## `brute_force_minimizer_1d`

### 支持域

`parameters`：

- `coefficients`：1–30 个有限十进制数，低次到高次，表示 `p(x)=sum(coefficients[i]*x^i)`；不用 `eval`，不接受候选自定义函数。
- `lower < upper`：闭区间。
- `initial_grid_points`：2–100001。
- `refinement_rounds`：0 –14。
- `local_grid_points`：3–1001。
- `precision`：16–250。

候选输出至少为 `{"x": 1.25}`，可选 `value`。运行器始终独立用 Horner 法重算 `p(x)`，不信任候选报告的 value，同时记录二者差异。x 越界失败。

### 独立 expected 与判定

先均匀扫描整个闭区间，再围绕当前最佳采样点按事前固定半径进行对称局部细化，细化永不读取候选输出。轨迹、点数、求值次数和最佳点全部记录。expected 明确定义为**指定确定性搜索访问到的最佳采样点/值**，不是通用解析最小值。

使用 `objective_abs`、`objective_rel` 限制候选函数值超出最佳采样值的幅度。可选 `x_abs`、`x_rel` 另加位置检查；未配置时不以 x 接近为由掩盖错误目标值。候选值明显更优时标记 `oracle_inconclusive`，说明 Oracle 网格遗漏更优点，不能反诬候选错误。

### 限制

固定网格及局部细化可能遗漏极窄谷底，不能保证任意多项式的连续全局最优，也不证明唯一性。不得把它用于多变量、非多项式或不连续黑箱函数。此类型做独立目标值/定义域检查，不自动提供二次方程的缩放变形；需要其他变形时扩展独立实现，不能伪造本类型已覆盖。

## 论文不等于数学真值

`paper_vs_oracle` 用同一事前容差比较论文目标和数学结果，但独立保存 `paper_target` 与 `oracle_mathematical_result`。若论文排版、近似或定义不同导致 `mismatched`，单列差异并检查单位、四舍五入、目标定义及实验条件；不允许移动 expected。`paper_target: null` 诚实输出 `not_provided`。
