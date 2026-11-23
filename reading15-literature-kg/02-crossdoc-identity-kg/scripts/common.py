# -*- coding: utf-8 -*-
"""共享工具：UTF-8 JSON 读写与目录保障（仅 Python3 标准库）。"""
import json
import os


def load_json(path, default=None):
    """读取 UTF-8 JSON；文件不存在或解析失败时返回 default（容错）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, NotADirectoryError):
        return default
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        if default is not None:
            return default
        raise ValueError("JSON 解析失败 %s: %s" % (path, exc))


def dump_json(obj, path):
    """以确保存在的目录写出 UTF-8 JSON（不转义非 ASCII 字符）。"""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_text(text, path):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
