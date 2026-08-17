#!/usr/bin/env python3
"""
meta_check.py — 元叙述污染检测（"注脚式写作"检测）

检测正文中把大纲设计说明当正文展开的元叙述污染：
  - "XX 的注脚 / 注注注脚"（递归元注释）
  - "XX 的展开 / 深化 / 补足 / 收尾 / 定性"
  - "还有一个 XX / 在…里(展开|补全|确立|收束)了"
  - "大纲写作特色 / 读者带着…进入全书" 等设计说明语言

正文应是对内容要点的叙事翻译；出现上述模式即视为污染。

用法:
  python3 meta_check.py chapters/                 # 扫描目录
  python3 meta_check.py ch01.md ch02.md ...       # 或指定文件
  python3 meta_check.py chapters/ --out meta.md   # 报告落盘

退出码: 0 = 通过(无污染), 1 = 发现污染(供流水线决策门用)
"""

import argparse
import os
import re
import sys

# 元叙述污染模式
META_PATTERNS = [
    (r"的注脚", "注脚式"),
    (r"的注注", "注注式"),
    (r"的展开", "展开式"),
    (r"的深化", "深化式"),
    (r"的补足|的补充", "补足式"),
    (r"的收尾|的收束", "收尾式"),
    (r"的又一个|还有一个", "追加式"),
    (r"的定性", "定性式"),
    (r"(在|于)[「\"“]?[^」\"”]{2,20}[」\"”]?里(展开|补全|确立|收束)了", "回指式"),
    (r"读者带着[^。；]{2,30}(悬念|进入全书)", "钩子泄漏"),
    (r"大纲(写作特色|叙事设计|核心命题)", "大纲引用"),
    (r"(开篇钩子|悬念设置|叙事设计)([:：])", "设计说明"),
]

def check(text: str) -> list[tuple[str, int]]:
    """返回 [(模式名, 命中次数)]"""
    hits = {}
    for pat, label in META_PATTERNS:
        n = len(re.findall(pat, text))
        if n:
            hits[label] = hits.get(label, 0) + n
    return sorted(hits.items(), key=lambda x: -x[1])

def main():
    parser = argparse.ArgumentParser(description="元叙述污染检测")
    parser.add_argument("paths", nargs="+", help="chapters/ 目录或 md 文件列表")
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

    total_hits = 0
    bad_files = 0
    lines = []
    for f in files:
        try:
            text = open(f, encoding="utf-8").read()
        except OSError as e:
            print(f"⚠️ 无法读取 {f}: {e}")
            continue
        # 跳过代码块
        text = re.sub(r"```[\s\S]*?```", "", text)
        hits = check(text)
        name = os.path.basename(f)
        if not hits:
            lines.append(f"✅ {name}")
            continue
        n = sum(c for _, c in hits)
        total_hits += n
        bad_files += 1
        detail = "、".join(f"{k}×{c}" for k, c in hits)
        lines.append(f"⚠️ {name}: {detail}")

    report = "\n".join(lines)
    if total_hits:
        report += f"\n\n共 {bad_files}/{len(files)} 个文件检出元叙述污染，总命中 {total_hits} 次。"
        report += "\n处理: 这些段落是'对写作设计的解释'而非叙事正文，必须重写为正常叙事（把内容要点翻译成故事，删除'注脚/展开/深化'类元语言）。"
        print(report)
        if args.out:
            open(args.out, "w", encoding="utf-8").write(report + "\n")
        return 1
    print(report if lines else "✅ 无污染")
    print("✅ 未检出元叙述污染（全部为正常叙事）")
    if args.out:
        open(args.out, "w", encoding="utf-8").write(report + "\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
