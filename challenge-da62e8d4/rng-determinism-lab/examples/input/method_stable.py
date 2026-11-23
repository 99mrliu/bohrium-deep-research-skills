"""合成示例（synthetic），非正式案例结果。

method_stable.py — 纯确定计算：无任何随机性、无时钟、无外部输入，
每次运行应打印完全相同的数值（受控重放下应判 identical / numerically_stable）。
"""


def main():
    # 固定系数的小计算：zeta(2) 的部分和
    total = 0.0
    for k in range(1, 101):
        total += 1.0 / (k * k)
    metric = total / 100.0
    print("method=stable")
    print("n_terms=100")
    print("sum_zeta2_partial=%.10f" % total)
    print("metric=%.6f" % metric)


if __name__ == "__main__":
    main()
