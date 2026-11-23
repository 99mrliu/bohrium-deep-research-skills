#!/usr/bin/env python3
"""env_snapshot.py — 环境快照与可重建说明。不联网，只用标准库。

用法:
    python3 env_snapshot.py [--out DIR] [--imports pkg1,pkg2,...]

输出:
    <out>/env.json    python 版本与可执行路径、platform、机器架构、
                      关键环境变量、--imports 指定包的精确版本（缺包记 not_installed）
    <out>/rebuild.md  可重建说明（python 版本、pip install pkg==ver 清单、
                      建议的环境变量设置）

退出码: 0 成功；2 参数错误。
"""
import argparse
import importlib.metadata
import json
import os
import platform
import sys

# 与数值计算确定性最相关的环境变量
KEY_ENV_VARS = [
    "PYTHONHASHSEED",
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "BLIS_NUM_THREADS",
    "CUDA_VISIBLE_DEVICES",
    "NVIDIA_VISIBLE_DEVICES",
    "TF_DETERMINISTIC_OPS",
    "CUBLAS_WORKSPACE_CONFIG",
]


def main(argv):
    parser = argparse.ArgumentParser(description="环境快照与可重建说明（不联网）")
    parser.add_argument("--out", default=".", help="输出目录，默认当前目录")
    parser.add_argument("--imports", default="",
                        help="逗号分隔的包名列表，用 importlib.metadata 记录精确版本")
    args = parser.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)

    packages = {}
    requested = [p.strip() for p in args.imports.split(",") if p.strip()]
    for name in requested:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not_installed"

    env = {
        "python": {
            "version": sys.version,
            "version_info": list(sys.version_info),
            "executable": sys.executable,
            "implementation": platform.python_implementation(),
        },
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "environment_variables": {k: os.environ.get(k) for k in KEY_ENV_VARS},
        "packages": packages,
        "note": "快照只记录，不修改任何环境；未联网。",
    }
    env_path = os.path.join(args.out, "env.json")
    with open(env_path, "w", encoding="utf-8") as f:
        json.dump(env, f, ensure_ascii=False, indent=2)

    lines = []
    lines.append("# 环境可重建说明（rebuild）")
    lines.append("")
    lines.append("## Python")
    lines.append("")
    lines.append("- 版本: `%s`" % sys.version.split()[0])
    lines.append("- 实现: %s" % platform.python_implementation())
    lines.append("- 可执行路径（本机）: `%s`" % sys.executable)
    lines.append("- 平台: `%s` / 架构: `%s`" % (platform.platform(), platform.machine()))
    lines.append("")
    lines.append("## 第三方包精确版本")
    lines.append("")
    if requested:
        lines.append("```bash")
        for name in requested:
            ver = packages[name]
            if ver == "not_installed":
                lines.append("# %s: not_installed（本机未安装，按需安装，"
                             "版本请以来源论文/仓库为准）" % name)
            else:
                lines.append("pip install %s==%s" % (name, ver))
        lines.append("```")
    else:
        lines.append("（未通过 --imports 指定任何包。）")
    lines.append("")
    lines.append("## 建议的环境变量设置（重放与复现前）")
    lines.append("")
    lines.append("```bash")
    lines.append("export PYTHONHASHSEED=0        # 固定 str/bytes 哈希，消除哈希序差异")
    lines.append("export OMP_NUM_THREADS=1       # 固定 BLAS 线程数，消除浮点归约顺序差异")
    lines.append("export OPENBLAS_NUM_THREADS=1")
    lines.append("export MKL_NUM_THREADS=1")
    lines.append("export CUDA_VISIBLE_DEVICES=   # 如需纯 CPU 复现，屏蔽 GPU")
    lines.append("```")
    lines.append("")
    lines.append("## 当前实际取值快照")
    lines.append("")
    for k in KEY_ENV_VARS:
        lines.append("- `%s` = `%s`" % (k, os.environ.get(k)))
    lines.append("")
    lines.append("> 本文件由 env_snapshot.py 自动生成；只记录事实，不构成复现成功结论。")
    lines.append("")
    with open(os.path.join(args.out, "rebuild.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("env.json: %s" % env_path)
    print("rebuild.md: %s" % os.path.join(args.out, "rebuild.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
