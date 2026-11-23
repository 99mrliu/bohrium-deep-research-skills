#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""normalize_input.py — 宽容型输入发现与语料归一化器。

职责（对应挑战官方运行时 /input 目录，也接受任意目录）：
1. 发现语料入口：优先 material.json（聚合索引），容忍三种形态：
   - 顶层列表：[ {source_id, role, path}, ... ]
   - 包装对象：{"materials": [...]}（亦接受 items/sources/files 键）
   - 映射对象：{source_id: {role, path} 或 "path"}
   material.json 缺失时回退到目录内 *-material.json 文件逐个装载。
2. 装载每个 material（primary-material.json / secondary-material.json），容忍
   包装层 {"material": {...}} 或直接 {"jats": {...}}。
3. 处理段落缺陷：
   - 缺失 paragraph id：确定性自动生成 "{source_id}.auto{n}" 并记 warning；
   - 重复 paragraph id：保留首次出现，重复 id 记入 duplicate_paragraph_ids，
     后续验证器对引用重复地址的证据一律报错（地址歧义即不可用）。
4. 交叉核对 corpus-manifest.json：role/doi/title 不一致记 warning。
5. 非 JSON 旁挂文件（如 secondary-publisher.xml）：不解析内容，仅记录其存在、
   字节数与 SHA-256，写入 skipped 清单（诚实声明“未解析”）。

输出 normalized_corpus.json（FORMAT normalized-corpus/1）。

CLI:
  python3 normalize_input.py --input /input --out /app/work/normalized_corpus.json
退出码：0 成功；2 结构性失败（无可装载 material）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import kgcommon as k


def _as_list_of_entries(raw):
    """把 material.json 的三种容忍形态统一为 entry 列表。"""
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, dict):
        for key in ("materials", "items", "sources", "files"):
            if isinstance(raw.get(key), list):
                return list(raw[key])
        # 映射形态：{source_id: meta}
        entries = []
        for sid in sorted(raw.keys()):
            meta = raw[sid]
            if isinstance(meta, str):
                meta = {"path": meta}
            if isinstance(meta, dict):
                meta = dict(meta)
                meta.setdefault("source_id", sid)
                entries.append(meta)
        if entries:
            return entries
    raise ValueError("material.json 形态不可识别（非列表/包装对象/映射）")


def discover_entries(input_dir, warnings):
    """发现 material 入口列表。"""
    input_dir = Path(input_dir)
    idx = input_dir / "material.json"
    if idx.exists():
        raw = k.read_json(idx)
        try:
            entries = _as_list_of_entries(raw)
        except ValueError as exc:
            warnings.append(f"material.json 解析宽容化失败：{exc}")
            entries = []
        if entries:
            return entries
        warnings.append("material.json 为空或不可用，回退到 *-material.json 逐文件发现")
    else:
        warnings.append("未发现 material.json，回退到 *-material.json 逐文件发现")
    entries = []
    for p in sorted(input_dir.glob("*-material.json")):
        entries.append({"path": p.name})
    return entries


def _unwrap_material(raw):
    """去掉一层可能的包装。"""
    if isinstance(raw, dict):
        for key in ("material", "document", "article"):
            if isinstance(raw.get(key), dict):
                return raw[key]
    return raw


def _extract_paragraphs(material, source_id, warnings, duplicate_ids):
    """从 jats 结构抽取有序段落列表；处理缺失/重复 id。"""
    jats = material.get("jats") if isinstance(material.get("jats"), dict) else material
    body = (jats or {}).get("body", {})
    raw_paras = []

    def collect(container, section):
        for item in container:
            if isinstance(item, str):
                raw_paras.append({"id": None, "section": section, "text": item})
            elif isinstance(item, dict):
                text = item.get("text")
                if text is None and isinstance(item.get("content"), str):
                    text = item["content"]
                if text is None:
                    continue
                raw_paras.append({
                    "id": item.get("id"),
                    "section": item.get("section", section),
                    "text": text,
                })

    if isinstance(body, dict):
        if isinstance(body.get("paragraphs"), list):
            collect(body["paragraphs"], body.get("title"))
        if isinstance(body.get("sections"), list):
            for sec in body["sections"]:
                if isinstance(sec, dict) and isinstance(sec.get("paragraphs"), list):
                    collect(sec["paragraphs"], sec.get("title") or sec.get("id"))
    if isinstance(jats, dict) and not raw_paras and isinstance(jats.get("paragraphs"), list):
        collect(jats["paragraphs"], None)

    seen = set()
    dup = []
    auto_n = 0
    paragraphs = []
    for item in raw_paras:
        pid = item["id"]
        if not pid:
            auto_n += 1
            pid = f"{source_id}.auto{auto_n}"
            warnings.append(f"{source_id}: 段落缺失 id，已自动编址为 {pid}")
        if pid in seen:
            dup.append(pid)
            warnings.append(f"{source_id}: 重复 paragraph id {pid}，保留首次出现，"
                            f"该地址此后视为歧义不可用")
            continue
        seen.add(pid)
        paragraphs.append({"id": pid, "section": item.get("section"), "text": item["text"]})
    if dup:
        duplicate_ids[source_id] = sorted(set(dup))
    return paragraphs


def _load_manifest(input_dir, warnings):
    path = Path(input_dir) / "corpus-manifest.json"
    if not path.exists():
        warnings.append("未发现 corpus-manifest.json，role 信息仅来自 material 自身")
        return {}
    raw = k.read_json(path)
    out = {}
    for entry in raw.get("sources", []) if isinstance(raw, dict) else []:
        if isinstance(entry, dict) and entry.get("source_id"):
            out[entry["source_id"]] = entry
    return out


def normalize(input_dir):
    """执行归一化，返回 normalized corpus 对象。"""
    input_dir = Path(input_dir)
    warnings = []
    skipped = []
    duplicate_ids = {}

    entries = discover_entries(input_dir, warnings)
    manifest = _load_manifest(input_dir, warnings)

    sources = []
    loaded_paths = set()
    for pos, entry in enumerate(entries):
        if isinstance(entry, str):
            entry = {"path": entry}
        if not isinstance(entry, dict):
            warnings.append(f"忽略无法识别的 material 入口（位置 {pos}）")
            continue
        embedded = entry.get("material") or entry.get("content")
        path = entry.get("path")
        if embedded is None and path:
            full = input_dir / path
            if not full.exists():
                warnings.append(f"material 路径不存在，已跳过：{path}")
                continue
            raw = k.read_json(full)
            loaded_paths.add(str(full.resolve()))
        elif embedded is not None:
            raw = embedded
            path = path or f"<embedded:{pos}>"
        else:
            warnings.append(f"material 入口既无 path 也无内嵌内容（位置 {pos}），已跳过")
            continue
        material = _unwrap_material(raw)
        if not isinstance(material, dict):
            warnings.append(f"material 内容不是对象（{path}），已跳过")
            continue

        source_id = entry.get("source_id") or material.get("source_id")
        if not source_id:
            stem = Path(str(path)).stem if path else f"material{pos}"
            source_id = stem.replace("-material", "").upper()
            warnings.append(f"material 缺少 source_id，按文件名推定为 {source_id}")
        role = entry.get("role") or material.get("role")
        if not role:
            role = "primary" if "primary" in str(path) else "secondary"
            warnings.append(f"{source_id}: 未声明 role，按文件名推定为 {role}")

        jats = material.get("jats", material)
        meta = (jats or {}).get("article-meta", {}) if isinstance(jats, dict) else {}
        doi = meta.get("doi") or material.get("doi")
        title = meta.get("title") or material.get("title")
        authors = meta.get("authors") or material.get("authors") or []

        man = manifest.get(source_id)
        if man:
            if man.get("role") and man["role"] != role:
                warnings.append(f"{source_id}: manifest role={man['role']} 与 material role={role} 不一致")
            if man.get("doi") and doi and man["doi"] != doi:
                warnings.append(f"{source_id}: manifest DOI 与 material DOI 不一致")
            if man.get("title") and title and man["title"] != title:
                warnings.append(f"{source_id}: manifest title 与 material title 不一致")
            role = man.get("role", role)

        paragraphs = _extract_paragraphs(material, source_id, warnings, duplicate_ids)
        sources.append({
            "source_id": source_id,
            "role": role,
            "doi": doi,
            "title": title,
            "authors": list(authors),
            "path": str(path),
            "paragraph_count": len(paragraphs),
            "paragraphs": paragraphs,
        })

    if not sources:
        raise SystemExit("错误：未装载到任何 material，无法构建语料。")

    # 非 JSON 旁挂文件：只登记，不解析。
    for p in sorted(Path(input_dir).iterdir()):
        if p.is_file() and p.suffix.lower() not in (".json", ".md") \
                and str(p.resolve()) not in loaded_paths:
            skipped.append({
                "path": p.name,
                "bytes": p.stat().st_size,
                "sha256": k.sha256_file(p),
                "reason": "非 JSON 旁挂文件，未解析；仅登记存在性与摘要以供溯源审计",
            })

    sources.sort(key=lambda s: (s.get("role") != "primary", s["source_id"]))
    corpus = {
        "format": k.FORMAT_NORMALIZED_CORPUS,
        "input_dir": str(input_dir),
        "sources": sources,
        "duplicate_paragraph_ids": duplicate_ids,
        "skipped": skipped,
        "warnings": warnings,
    }
    return corpus


def main(argv=None):
    ap = argparse.ArgumentParser(description="宽容型语料发现与归一化器")
    ap.add_argument("--input", required=True, help="输入目录（官方运行时 /input）")
    ap.add_argument("--out", required=True, help="输出 normalized_corpus.json 路径")
    args = ap.parse_args(argv)

    corpus = normalize(args.input)
    k.write_json(args.out, corpus)
    n_warn = len(corpus["warnings"])
    print(f"[normalize_input] sources={len(corpus['sources'])} "
          f"paragraphs={sum(s['paragraph_count'] for s in corpus['sources'])} "
          f"warnings={n_warn} skipped={len(corpus['skipped'])}")
    for w in corpus["warnings"]:
        print(f"  warning: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
