#!/usr/bin/env python3
"""code_audit.py — 零运行 AST 静态审计一个 Python 候选脚本的随机性与非确定性风险。

只使用标准库，不执行、不导入被审计文件。

用法:
    python3 code_audit.py <file.py>

退出码:
    0  审计完成（包括语法错误情形，此时输出 status=parse_error 的结构化 JSON）
    2  输入不是 .py 文件（输出 status=not_applicable 的结构化 JSON）

输出（stdout, JSON）字段:
    status       ok / parse_error / not_applicable
    file         被审计文件路径
    imports      import / from-import 清单（含行号）
    rng_calls    随机数调用点（random.* / np.random.* / torch.rand* 等，含行号）
    seed_calls   播种调用点（random.seed / np.random.seed / manual_seed 等，
                 含行号与首实参是否字面量）
    risks        非确定性风险点（time/datetime/os.urandom/set/hash/
                 threading/multiprocessing/subprocess/socket 等，含行号与说明）
    seeded       是否发现任何播种调用（布尔）
    warnings     文字告警列表（如"发现 RNG 调用但未发现播种"）
"""
import ast
import json
import os
import sys

# ---- RNG 识别配置 -----------------------------------------------------------
# 模块级 RNG 前缀（dot 结尾，用于前缀匹配）
_BASE_RNG_MODULE_PREFIXES = ("random.", "np.random.", "numpy.random.", "tf.random.")
# torch 的随机函数在顶层：torch.rand / randn / randint / randperm / rand_like ...
_TORCH_RAND_PREFIXES = ("torch.rand",)
# 精确匹配的 RNG 调用
_RNG_EXACT = {"np.rand", "np.randn", "numpy.rand", "numpy.randn"}

_SEED_EXACT = {
    "seed", "set_seed", "manual_seed",
    "random.seed", "np.random.seed", "numpy.random.seed",
    "torch.manual_seed", "torch.cuda.manual_seed", "torch.cuda.manual_seed_all",
    "tf.random.set_seed",
}
_SEED_SUFFIXES = (".seed", ".manual_seed", ".set_seed")

# ---- 风险规则 ---------------------------------------------------------------
# (匹配方式, 名字集合, 类别, 一句话说明)
_RISK_RULES = [
    ("exact", {"time.time", "time.monotonic", "time.perf_counter",
               "time.process_time", "time.localtime", "time.gmtime",
               "time.strftime", "time.ctime"}, "clock",
     "读取系统时钟：时间戳或耗时可能进入输出，甚至驱动分支逻辑"),
    ("exact", {"datetime.datetime.now", "datetime.datetime.utcnow",
               "datetime.now", "datetime.utcnow", "date.today",
               "datetime.date.today"}, "clock",
     "读取当前日期时间：可能进入输出或驱动逻辑"),
    ("prefix", ("os.urandom",), "system_entropy",
     "使用操作系统熵源：无法通过种子复现"),
    ("prefix", ("secrets.",), "system_entropy",
     "secrets 模块使用操作系统熵源：无法通过种子复现"),
    ("exact", {"set"}, "hash_order",
     "set(...) 构造：迭代顺序受元素哈希影响（str/bytes 的哈希受 PYTHONHASHSEED 影响）"),
    ("exact", {"hash"}, "hash_order",
     "hash() 对 str/bytes 的结果受 PYTHONHASHSEED 影响，跨进程可能不同"),
    ("exact", {"frozenset"}, "hash_order",
     "frozenset(...) 构造：迭代顺序受元素哈希影响"),
    ("prefix", ("threading.",), "concurrency",
     "多线程：调度交错可能引入非确定性"),
    ("prefix", ("multiprocessing.",), "concurrency",
     "多进程：子进程调度与归约顺序可能引入非确定性"),
    ("prefix", ("concurrent.futures.",), "concurrency",
     "并发执行器：任务完成顺序可能引入非确定性"),
    ("prefix", ("asyncio.",), "concurrency",
     "异步调度：任务交错顺序可能引入非确定性"),
    ("prefix", ("subprocess.",), "subprocess",
     "子进程调用：外部命令行为不在本审计与受控重放的控制范围内"),
    ("prefix", ("socket.",), "network",
     "网络访问：外部数据不可复现"),
    ("exact", {"os.environ.get", "os.getenv"}, "env_dependency",
     "读取环境变量：行为依赖外部环境，需纳入环境快照登记"),
]


def _dotted_name(node):
    """把 Name/Attribute 链还原成点分名字；还原不了返回 None。"""
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        parts.reverse()
        return ".".join(parts)
    return None


def _match(name, kind, names):
    if name is None:
        return False
    if kind == "exact":
        return name in names
    return any(name.startswith(p) for p in names)


class _Audit(ast.NodeVisitor):
    def __init__(self, source):
        self.source = source
        self.imports = []
        self.rng_calls = []
        self.seed_calls = []
        self.risks = []
        # 别名追踪：numpy/torch 的 as 别名；RNG 模块别名
        self._numpy_aliases = {"numpy", "np"}
        self._torch_aliases = {"torch"}
        self._rng_module_aliases = {"random"}  # 本身就是 RNG 模块的名字
        self._rng_local_funcs = set()          # from random import random 这类
        self._seed_local_funcs = set()         # from random import seed 这类

    # -- imports -------------------------------------------------------------
    def visit_Import(self, node):
        for a in node.names:
            top = a.name.split(".")[0]
            effective = a.asname or a.name
            if a.name == "random":
                self._rng_module_aliases.add(a.asname or "random")
            elif a.name == "numpy.random":
                self._rng_module_aliases.add(a.asname or "numpy.random")
            elif a.name == "numpy":
                self._numpy_aliases.add(a.asname or "numpy")
            elif a.name == "torch":
                self._torch_aliases.add(a.asname or "torch")
            elif a.name in ("tensorflow", "tensorflow.random"):
                self._rng_module_aliases.add(effective + ".random"
                                             if a.name == "tensorflow" else effective)
            self.imports.append({
                "line": node.lineno, "kind": "import",
                "module": a.name, "alias": a.asname,
            })
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        mod = node.module or ""
        names = [a.name for a in node.names]
        self.imports.append({
            "line": node.lineno, "kind": "from",
            "module": mod, "names": names,
            "aliases": {a.name: a.asname for a in node.names if a.asname},
        })
        if mod in ("random", "numpy.random"):
            for a in node.names:
                local = a.asname or a.name
                if a.name == "seed":
                    self._seed_local_funcs.add(local)
                elif a.name != "*":
                    self._rng_local_funcs.add(local)
        self.generic_visit(node)

    # -- calls ---------------------------------------------------------------
    def visit_Call(self, node):
        name = _dotted_name(node.func)
        if name is not None:
            self._check_call(node, name)
        self.generic_visit(node)

    def _rng_prefixes(self):
        prefixes = list(_BASE_RNG_MODULE_PREFIXES)
        for alias in self._rng_module_aliases:
            prefixes.append(alias + ".")
        for na in self._numpy_aliases:
            prefixes.append(na + ".random.")
        for ta in self._torch_aliases:
            prefixes.append(ta + ".rand")
        return tuple(prefixes)

    def _check_call(self, node, name):
        # RNG 调用
        is_rng = (
            name.startswith(self._rng_prefixes())
            or name in _RNG_EXACT
            or name in self._rng_local_funcs
        )
        # 播种调用（优先于 RNG 判定，seed 本身不算 RNG 消费点）
        is_seed = (
            name in _SEED_EXACT
            or any(name.endswith(s) for s in _SEED_SUFFIXES)
            or name in self._seed_local_funcs
        )
        if is_seed:
            arg_literal = False
            arg_repr = None
            if node.args:
                first = node.args[0]
                arg_literal = isinstance(first, ast.Constant)
                try:
                    arg_repr = ast.literal_eval(first).__repr__()
                except (ValueError, SyntaxError, TypeError, MemoryError):
                    arg_repr = ast.dump(first)[:80]
            self.seed_calls.append({
                "line": node.lineno, "call": name,
                "arg_literal": arg_literal, "arg_repr": arg_repr,
            })
            return
        if is_rng:
            self.rng_calls.append({"line": node.lineno, "call": name})
        # 风险规则
        for kind, names, category, msg in _RISK_RULES:
            if _match(name, kind, names):
                self.risks.append({
                    "line": node.lineno, "category": category,
                    "call": name, "note": msg,
                })
                break


def audit(path):
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as e:
        return {
            "status": "parse_error",
            "file": path,
            "error": {
                "message": e.msg,
                "line": e.lineno,
                "offset": e.offset,
            },
            "note": "源文件无法被 ast 解析（语法错误），静态审计不可用；"
                    "受控重放与环境快照不受影响。",
        }
    visitor = _Audit(source)
    visitor.visit(tree)
    seeded = len(visitor.seed_calls) > 0
    warnings = []
    if visitor.rng_calls and not seeded:
        warnings.append(
            "发现 %d 处随机数调用但没有任何播种（seed）调用："
            "同机重跑结果可能不稳定，属未播种 RNG。" % len(visitor.rng_calls))
    non_literal = [s for s in visitor.seed_calls if not s["arg_literal"]]
    if non_literal:
        warnings.append(
            "发现 %d 处播种调用的实参不是字面量（行 %s）："
            "种子来自变量/外部环境，需在参数表中登记其实际取值。"
            % (len(non_literal),
               ", ".join(str(s["line"]) for s in non_literal)))
    if visitor.risks:
        cats = sorted({r["category"] for r in visitor.risks})
        warnings.append("发现非确定性风险类别: %s。" % ", ".join(cats))
    return {
        "status": "ok",
        "file": path,
        "imports": visitor.imports,
        "rng_calls": visitor.rng_calls,
        "seed_calls": visitor.seed_calls,
        "risks": visitor.risks,
        "seeded": seeded,
        "warnings": warnings,
    }


def main(argv):
    if len(argv) != 2:
        print("用法: python3 code_audit.py <file.py>", file=sys.stderr)
        return 2
    path = argv[1]
    if not (path.endswith(".py") and os.path.isfile(path)):
        json.dump({
            "status": "not_applicable",
            "file": path,
            "reason": "输入不是存在的 .py 文件，AST 静态审计不适用；"
                      "受控重放（replay.py）与环境快照（env_snapshot.py）仍可做。",
        }, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 2
    result = audit(path)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
