"""合成示例（synthetic），非正式案例结果。

method_unseeded.py — 故意不播种的随机方法：使用 random 模块但不调用
random.seed()，每次运行打印不同的随机 metric，并写一个小结果文件
result_unseeded.txt（相对当前工作目录），便于 replay.py 做产物哈希对比。
受控重放下应判 unstable，且各次产物 sha256 不同。
"""
import random


def main():
    draws = [random.random() for _ in range(1000)]
    metric = sum(draws) / len(draws)
    print("method=unseeded")
    print("n_draws=1000")
    print("metric=%.6f" % metric)
    # 产物文件：replay.py 以 run_<i>/ 为 cwd 运行本脚本，故落在各次运行目录
    with open("result_unseeded.txt", "w", encoding="utf-8") as f:
        f.write("metric=%.6f\n" % metric)


if __name__ == "__main__":
    main()
