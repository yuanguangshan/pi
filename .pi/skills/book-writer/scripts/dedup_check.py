#!/usr/bin/env python3
"""
dedup_check.py — 跨章节信息复读检测（去重与信息消歧节点）

扫描 chapters/ 下所有章节，找出跨章节重复出现的"信息指纹"：
  1. 完全重复句：去除标点/空白后完全相同的句子
  2. 高相似句：difflib 相似度 >= 阈值（金句变体、换词重说）
  3. 包含重复：一句包含另一句的较长片段（同一案例被扩展/缩写复述）

输出 markdown 报告到终端，供 AI 按规则压缩：保留最详尽一次，
其余位置压缩为一句简短交叉引用（如"如前文第 N 章所述"）。

用法:
  python3 dedup_check.py chapters/                 # 扫描目录
  python3 dedup_check.py ch01.md ch02.md ...       # 或指定文件
  python3 dedup_check.py chapters/ --min-len 10    # 最小指纹长度（默认 12）
  python3 dedup_check.py chapters/ --out dup.md    # 报告落盘

退出码: 0 = 无严重复读, 1 = 发现复读（供流水线决策门用）
"""

import argparse
import difflib
import os
import re
import sys
from collections import defaultdict

MIN_LEN = 12          # 指纹最短字数（太短全是"他说""这家公司"）
SIM_THRESHOLD = 0.88  # 高相似度阈值
PUNCT = "。！？；…——"

def split_sentences(text: str) -> list[str]:
    """按中文句末标点切句，保留句末标点。"""
    parts = re.split(r"([。！？；…])", text)
    sents = []
    for i in range(0, len(parts) - 1, 2):
        s = (parts[i] + parts[i + 1]).strip()
        if s:
            sents.append(s)
    if parts[-1].strip():
        sents.append(parts[-1].strip())
    return sents

def fingerprint(s: str) -> str:
    """去标点/空白，得到比较指纹。"""
    return re.sub(r"[\s\u3000，。！？；：、“”‘’（）《》〈〉—…·]+", "", s)

def norm(s: str) -> str:
    """报告用的简短显示（去首尾空白）。"""
    return s.strip()[:80] + ("…" if len(s.strip()) > 80 else "")

def scan(files: list[str], min_len: int = MIN_LEN) -> list[dict]:
    """返回复读条目: {fingerprint, text, chapters:[{file, line}]}"""
    chapters = []  # [{file, sents: [{fp, text}]}]
    for f in files:
        try:
            txt = open(f, encoding="utf-8").read()
        except OSError as e:
            print(f"⚠️ 无法读取 {f}: {e}")
            continue
        sents = [
            {"fp": fingerprint(s), "text": s}
            for s in split_sentences(txt)
            if len(fingerprint(s)) >= min_len
        ]
        chapters.append({"file": os.path.basename(f), "sents": sents})

    # 指纹 -> 出现位置
    fp_locs = defaultdict(list)
    for ci, ch in enumerate(chapters):
        for si, s in enumerate(ch["sents"]):
            fp_locs[s["fp"]].append((ci, si, s["text"]))

    # 1) 完全重复（>=2 处）
    exact = []
    for fp, locs in fp_locs.items():
        if len(locs) >= 2:
            exact.append({"type": "完全重复", "text": locs[0][2], "locs": locs})

    # 2) 高相似句（跨章、非同一句的变体）——只比较首尾，避免 O(n^2) 爆炸
    similar = []
    flat = []
    for ci, ch in enumerate(chapters):
        for si, s in enumerate(ch["sents"]):
            flat.append((ci, si, s))
    for i in range(len(flat)):
        for j in range(i + 1, len(flat)):
            ci, si, a = flat[i]
            cj, sj, b = flat[j]
            if ci == cj:
                continue
            if a["fp"] == b["fp"]:
                continue  # 已在 exact
            if abs(len(a["fp"]) - len(b["fp"])) > max(len(a["fp"]), len(b["fp"])) * 0.4:
                continue
            r = difflib.SequenceMatcher(None, a["fp"], b["fp"]).ratio()
            if r >= SIM_THRESHOLD:
                similar.append({
                    "type": f"高相似(相似度{r:.0%})",
                    "text": a["text"] if len(a["text"]) >= len(b["text"]) else b["text"],
                    "locs": [(ci, si, a["text"]), (cj, sj, b["text"])],
                })

    # 3) 包含重复：长句包含另一句的完整指纹（跨章、长度差 >= 8 字）
    contain = []
    for i in range(len(flat)):
        for j in range(len(flat)):
            ci, si, a = flat[i]
            cj, sj, b = flat[j]
            if ci == cj or i == j:
                continue
            la, lb = len(a["fp"]), len(b["fp"])
            if la <= lb:
                continue
            if la - lb < 8:
                continue
            if b["fp"] in a["fp"]:
                contain.append({
                    "type": "包含复述",
                    "text": a["text"],
                    "locs": [(ci, si, a["text"]), (cj, sj, b["text"])],
                })

    # 合并输出（去重：同文本多类型取其一）
    seen = set()
    out = []
    for item in exact + similar + contain:
        key = (item["text"].strip()[:40], tuple(sorted((l[0], l[1]) for l in item["locs"])))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out

def render(items: list[dict], files: list[str], min_len: int = MIN_LEN, sim: float = SIM_THRESHOLD) -> str:
    if not items:
        return "✅ 未发现跨章节复读（阈值: 指纹≥%d字, 相似度≥%.0f%%）" % (min_len, sim)
    lines = [f"⚠️ 发现 {len(items)} 处跨章节复读（指纹≥{min_len}字，相似度≥{sim:.0%}）：", ""]
    for k, item in enumerate(items, 1):
        names = [os.path.basename(f) for f in files]
        locs = item["locs"]
        where = " | ".join(f"{names[ci]}#{si+1}行" for ci, si, _ in locs)
        lines.append(f"{k}. [{item['type']}] {where}")
        lines.append(f"   片段: “{norm(item['text'])}”")
        lines.append("")
    lines.append("处理规则: 同一金句/案例/数据点全书只详写一次；其余位置压缩为一句交叉引用（如“如前文第 N 章所述”），删除重复的解释性段落。")
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="跨章节信息复读检测")
    parser.add_argument("paths", nargs="+", help="chapters/ 目录或 md 文件列表")
    parser.add_argument("--min-len", type=int, default=MIN_LEN, help="指纹最短字数")
    parser.add_argument("--out", default="", help="报告落盘路径")
    args = parser.parse_args()

    files = []
    for p in args.paths:
        if os.path.isdir(p):
            files.extend(sorted(os.path.join(p, f) for f in os.listdir(p) if f.endswith(".md")))
        else:
            files.append(p)
    if not files:
        print("❌ 没有可扫描的 md 文件")
        return 2

    items = scan(files, args.min_len)
    report = render(items, files, args.min_len)
    print(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report + "\n")
        print(f"已写入: {args.out}")
    return 1 if items else 0

if __name__ == "__main__":
    sys.exit(main())
