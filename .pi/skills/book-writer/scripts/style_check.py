#!/usr/bin/env python3
"""
style_check.py — 反 AI 句式与语气检查（润色节点）

扫描章节，检测并统计两类"AI 格式化基因"：
  1. 套路句式黑名单（转折/升华/宿命论高频句式）出现次数
  2. 段尾硬拔高密度：以"哲理升华句"收尾的段落占段落总数比例

输出每章统计 + 超标警告。AI 依据报告改写：同类句式每章限用，
段尾允许事实收尾或留白，不要求每段都升华。

用法:
  python3 style_check.py chapters/                 # 扫描目录
  python3 style_check.py ch01.md ch02.md ...       # 或指定文件
  python3 style_check.py chapters/ --out style.md  # 报告落盘

退出码: 0 = 通过, 1 = 超标（供流水线决策门用）
"""

import argparse
import os
import re
import sys

# 黑名单句式（正则）。每章出现次数限制见 LIMITS。
PATTERNS = [
    (r"不是[^。；]{2,24}而是", "转折套路「不是…而是…」"),
    (r"这不仅是[^。；]{2,24}更是", "升华套路「这不仅是…更是…」"),
    (r"这(大概|恰恰|正是|才)是[^。；]{2,30}", "断言套路「这大概是/恰恰是…」"),
    (r"直接葬送", "宿命论「直接葬送」"),
    (r"(一声|敲响)[^。；]{0,6}丧钟|丧钟", "宿命论「丧钟」"),
    (r"最[^。；]{0,12}(误判|昂贵|残酷|惨痛|昂贵)的", "宿命论「最…的」"),
    (r"铁律", "断言「铁律」"),
    (r"永恒(的|地)?[^。；]{0,10}", "断言「永恒」"),
    (r"毋庸置疑|毫无疑问", "断言「毋庸置疑/毫无疑问」"),
    (r"某种程度上|在某种意义上", "填充「某种程度上」"),
    (r"可以说[，,]", "填充「可以说」"),
]

# 每章各句式的允许次数上限
DEFAULT_LIMIT = 3

# 段尾升华句式（段落末句匹配其一视为"硬拔高"）
ELEVATION_RE = re.compile(
    r"(这不仅是[^。]{0,30}|这是[^。]{0,20}(较量|战争|缩影|铁律|代价|宿命|悲剧)|"
    r"这大概就是[^。]{0,30}|也许这就是[^。]{0,30}|商业史上最[^。]{0,30}|"
    r"历史会记住[^。]{0,30}|注定[^。]{0,20}(载入|写入|成为))"
)

def split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

def analyze(text: str, fname: str) -> dict:
    paras = split_paragraphs(text)
    counts = {}
    for pat, label in PATTERNS:
        n = len(re.findall(pat, text))
        if n:
            counts[label] = n
    # 段尾升华：段落末句（最后一句）命中升华句式
    elev = 0
    for p in paras:
        sents = [s for s in re.split(r"(?<=[。！？；…])", p) if s.strip()]
        if not sents:
            continue
        last = sents[-1]
        if ELEVATION_RE.search(last):
            elev += 1
    total_sents = sum(len([s for s in re.split(r"(?<=[。！？；…])", p) if s.strip()]) for p in paras)
    return {
        "file": fname,
        "paras": len(paras),
        "counts": counts,
        "elevation": elev,
        "elevation_ratio": elev / len(paras) if paras else 0,
        "total_sents": total_sents,
    }

def render(results: list[dict], limit: int = DEFAULT_LIMIT) -> tuple[str, bool]:
    over_limit = []
    lines = []
    for r in results:
        flags = []
        for label, n in sorted(r["counts"].items()):
            if n > limit:
                flags.append(f"{label}×{n}(超限)")
        ratio = r["elevation_ratio"]
        if ratio > 0.25:
            flags.append(f"段尾升华{ratio:.0%}段落(超25%)")
        if not r["counts"] and ratio <= 0.25:
            lines.append(f"✅ {r['file']}: 无黑名单句式，段尾升华 {ratio:.0%}（{r['elevation']}/{r['paras']} 段）")
            continue
        detail = "、".join(f"{k}×{v}" for k, v in sorted(r["counts"].items()))
        lines.append(f"⚠️ {r['file']}: {detail}；段尾升华 {ratio:.0%}（{r['elevation']}/{r['paras']} 段）")
        if flags:
            over_limit.append(f"{r['file']}: {'、'.join(flags)}")
    report = "\n".join(lines)
    if over_limit:
        report += "\n\n超限项（需改写）:\n  " + "\n  ".join(over_limit)
        report += "\n\n改写规则: 同类句式每章最多" + str(limit) + "次；段尾升华占比 ≤25%；允许事实收尾与留白；戏剧性只在关键历史节点爆发。"
        return report, True
    return report, False

def main():
    parser = argparse.ArgumentParser(description="反 AI 句式与语气检查")
    parser.add_argument("paths", nargs="+", help="chapters/ 目录或 md 文件列表")
    parser.add_argument("--out", default="", help="报告落盘路径")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="单句式每章次数上限")
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

    results = []
    for f in files:
        try:
            txt = open(f, encoding="utf-8").read()
        except OSError as e:
            print(f"⚠️ 无法读取 {f}: {e}")
            continue
        results.append(analyze(txt, os.path.basename(f)))

    report, over = render(results, args.limit)
    print(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report + "\n")
        print(f"已写入: {args.out}")
    return 1 if over else 0

if __name__ == "__main__":
    sys.exit(main())
