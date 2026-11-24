#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_fixture.py -- 合成示例稿件（合成示例，非真实案件）。

manuscript.md 内置四类真实缺陷，供三个脚本演示：
  1) 图编号断档/错号：第二个图题注误标为"图3"，正文却引用"图2"（悬空引用）
  2) 表1 题注放在表下方（违反"表题注在表上方"）
  3) 参考文献 [2] 缺文献类型标志、作者 4 人未截断；[3] 缺年份（ERROR）
  4) 参考文献 [1] 为合规条目（PASS 对照）
fixed.md 为按 renumber_plan 修正后的版本（xref_scan 应 0 ERROR）。
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work")

MANUSCRIPT = """# 合成稿件：示意图表与文献一致性检查

如图1所示，合成装置的示意结构包含三个腔体。

![装置示意图](fig1.png)

图1 合成装置结构示意图

如图2所示，温度曲线在 300 K 附近出现拐点。

![温度曲线](fig2.png)

图3 合成温度曲线（编号错误：应为图2）

合成数据汇总见表1。

| 组别 | 产率 |
| --- | --- |
| A | 92.4% |

表1 合成数据汇总（题注位置错误：应在表上方）

## 参考文献

[1] 张三, 李四, 王五, 等. 合成催化剂研究. 合成学报, 2020, 15(3): 123-130.

[2] Smith J, Doe A, Brown B, Green C. A synthetic study. Journal of Examples, 2021, 8(2): 45-52

[3] 赵六. 合成方法学. 北京: 合成出版社.
"""

FIXED = """# 合成稿件：示意图表与文献一致性检查

如图1所示，合成装置的示意结构包含三个腔体。

![装置示意图](fig1.png)

图1 合成装置结构示意图

如图2所示，温度曲线在 300 K 附近出现拐点。

![温度曲线](fig2.png)

图2 合成温度曲线

表1 合成数据汇总

| 组别 | 产率 |
| --- | --- |
| A | 92.4% |

合成数据汇总见表1。

## 参考文献

[1] 张三, 李四, 王五, 等. 合成催化剂研究[J]. 合成学报, 2020, 15(3): 123-130.

[2] Smith J, Doe A, Brown B, et al. A synthetic study. Journal of Examples [J], 2021, 8(2): 45-52.

[3] 赵六. 合成方法学 [M]. 北京: 合成出版社, 2019.
"""

def main():
    os.makedirs(WORK, exist_ok=True)
    for name, text in (("manuscript.md", MANUSCRIPT), ("fixed.md", FIXED)):
        with open(os.path.join(WORK, name), "w", encoding="utf-8") as f:
            f.write(text)
    print("synthetic fixtures ->", WORK)

if __name__ == "__main__":
    main()
