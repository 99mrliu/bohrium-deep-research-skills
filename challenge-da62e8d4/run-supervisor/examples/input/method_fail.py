#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合成示例（synthetic），非正式案例结果：模拟“崩溃”的候选数值方法。
向 stderr 写入错误信息并以退出码 1 结束，用于验证监督器把失败记为证据且流程继续。"""
import sys

sys.stderr.write("method_fail: synthetic demo error — 模拟候选代码运行崩溃（exit 1）。\n")
sys.stderr.flush()
sys.exit(1)
