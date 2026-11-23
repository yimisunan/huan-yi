#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深渊天平引擎 · 知识库世界书 → Operit 世界书格式转换脚本
用法: python3 convert_to_operit.py
产物: 同目录 operit_worldbook_深渊天平.json（Operit 原生条目数组，import_entries 可直接导入）
映射说明:
  lorebook(ST v1)  →  Operit 原生
  name             →  name
  content          →  content
  keywords[]       →  keywords
  useRegex         →  is_regex
  caseSensitive    →  case_sensitive
  constantActive   →  always_active
  enabled          →  enabled
  priority         →  priority
  scanDepth        →  scan_depth
  position(any)    →  inject_position=append（原 after_system_prompt 语义）
  role             →  inject_target=system
  injectDepth      →  insertion_depth=0（append 模式不参与）
"""
import json
import os
import sys
import hashlib

BASE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(BASE)
OUTPATH = os.path.join(BASE, "operit_worldbook_深渊天平.json")

FILES = [
    ("世界观类", os.path.join(WORKSPACE, "txt文件/知识库/世界观类.json")),
    ("叙事判断", os.path.join(WORKSPACE, "txt文件/知识库/叙事判断.json")),
    ("角色类", os.path.join(WORKSPACE, "txt文件/知识库/角色类.json")),
    ("系统标签类", os.path.join(WORKSPACE, "txt文件/知识库/系统标签类.json")),
]


def to_operit(e):
    if not e.get("name") or not e.get("content"):
        raise ValueError(f"条目缺少 name 或 content: {e.get('name', '<无name>')!r}")
    return {
        "name": e["name"],
        "content": e["content"],
        "keywords": e.get("keywords", []),
        "is_regex": bool(e.get("useRegex", False)),
        "case_sensitive": bool(e.get("caseSensitive", False)),
        "always_active": bool(e.get("constantActive", False)),
        "enabled": bool(e.get("enabled", True)),
        "priority": int(e.get("priority", 50)),
        "scan_depth": int(e.get("scanDepth", 0)),
        "inject_target": "system",
        "inject_position": "append",
        "insertion_depth": 0,
    }


# ---------- 终端美化（非终端环境自动退化为纯文本） ----------
_USE_COLOR = sys.stdout.isatty()


def c(code, s):
    return f"\033[{code}m{s}\033[0m" if _USE_COLOR else s


GREEN, RED, YELLOW, CYAN, DIM, BOLD, MAG = (
    lambda s: c("32", s), lambda s: c("31", s), lambda s: c("33", s),
    lambda s: c("36", s), lambda s: c("2", s), lambda s: c("1", s),
    lambda s: c("35", s),
)
LINE = "=" * 60
THIN = "─" * 60


def fmt_size(n):
    return f"{n:,} B"


def status_icon(ok):
    return GREEN("✔") if ok else RED("✘")


def md5_of(path):
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()[:8]
    except OSError:
        return None


def main():
    print(BOLD(f"\n{LINE}"))
    print(BOLD(f"  深渊天平 → Operit 世界书导出"))
    print(DIM(f"  源目录: {WORKSPACE}"))
    print(BOLD(f"{LINE}\n"))

    out = []
    ok_libs, fail_libs = [], []
    for src, path in FILES:
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except FileNotFoundError:
            fail_libs.append(src)
            print(f" {RED('✘')} {BOLD(src)}  {RED('源文件不存在')}  {DIM(path)}")
            continue
        except json.JSONDecodeError as e:
            fail_libs.append(src)
            print(f" {RED('✘')} {BOLD(src)}  {RED('JSON 解析失败')}")
            print(f"    {DIM('位置:')} 第 {e.lineno} 行 第 {e.colno} 列 | {e.msg}")
            continue
        entries = d.get("data", {}).get("entries", []) or d.get("entries", [])
        if not entries:
            fail_libs.append(src)
            print(f" {YELLOW('!')} {BOLD(src)}  {YELLOW('0 条条目，已跳过')}  {DIM('请检查源文件')}")
            continue
        converted = [to_operit(e) for e in entries]
        names = [e["name"] for e in converted]
        ok_libs.append(src)
        print(f" {GREEN('✔')} {BOLD(src)}  {CYAN(f'{len(converted):>2} 条')}  {DIM('(' + ', '.join(names) + ')')}")
        out.extend(converted)

    print(f"\n{THIN}")
    total = len(out)
    if fail_libs:
        print(f" {RED('✘')} 汇总: 合并 {BOLD(str(total))} 条 · "
              f"{GREEN(f'{len(ok_libs)}')}/{len(FILES)} 库成功 · "
              f"{RED(f'失败: ' + ', '.join(fail_libs))}")
    else:
        print(f" {GREEN('✔')} 汇总: 合并 {BOLD(str(total))} 条 · "
              f"{GREEN(f'{len(ok_libs)}/{len(FILES)} 库成功')}")

    # 重名校验
    names = [e["name"] for e in out]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        print(f" {RED('✘')} 重名校验: 存在 {len(dupes)} 个重名 {RED(str(dupes))}")
        raise SystemExit(1)
    print(f" {GREEN('✔')} 重名校验: {CYAN(str(len(names)))} 条无重名")

    if fail_libs:
        print(f"\n {RED('✘')} 转换中止: 存在失败库，未写入产物")
        print(f"{LINE}\n")
        raise SystemExit(1)

    # 写入产物
    try:
        with open(OUTPATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f" {RED('✘')} 产物写入失败: {OUTPATH}\n   {e}")
        raise SystemExit(1)
    size = os.path.getsize(OUTPATH)
    digest = md5_of(OUTPATH)
    prev = md5_of(OUTPATH + ".prev")

    print(f"\n{THIN}")
    print(f" {GREEN('✔')} 产物已写入: {CYAN(OUTPATH)}")
    print(f"   大小: {BOLD(fmt_size(size))} | 条目: {BOLD(str(total))}")

    # 与上次产物对比（.prev 为上次运行前的快照）
    if prev is None:
        print(f" {DIM('ℹ')} MD5: {BOLD(digest)}  {DIM('（新产物，无历史对比）')}")
    elif prev == digest:
        print(f" {YELLOW('!')} MD5: {BOLD(digest)}  {YELLOW('与上次产物一致，无实质变化')}")
    else:
        print(f" {GREEN('↑')} MD5: {BOLD(digest)}  {GREEN('与上次不同')}  {DIM(f'（上次 {prev}）')}")

    # 保留本次快照供下次对比
    try:
        with open(OUTPATH, "rb") as f_src, open(OUTPATH + ".prev", "wb") as f_dst:
            f_dst.write(f_src.read())
    except OSError:
        pass

    print(f"\n{THIN}")
    print(f" {MAG('下一步')}: 在 Operit 世界书工具调用 {CYAN('import_entries')}，")
    print(f"          path 指向: {CYAN(OUTPATH)}")
    print(f"{LINE}\n")


if __name__ == "__main__":
    main()