#!/usr/bin/env python3
"""
chapter_wordcount.py — 中文字数统计

中文书写项目的字数统计按"中文字符 + 全角标点"计，英文/数字/空白不算。
目标每章 8000-10000 中文字符。

用法:
    python3 chapter_wordcount.py <md或txt文件>
    python3 chapter_wordcount.py chapters/      # 目录模式
    python3 chapter_wordcount.py chapters/ --json

退出码:
    0 = 所有文件达标(8000-10000)
    1 = 有文件不达标
    2 = 参数错误
"""

import argparse
import json
import re
import sys
from pathlib import Path

# CJK Unified Ideographs + CJK 扩展 A + 全角 ASCII / 全角标点
ZH_PATTERN = re.compile(
    r"[\u4e00-\u9fff"          # CJK 基本
    r"\u3400-\u4dbf"           # CJK 扩展 A
    r"\uff00-\uffef]"          # 全角 ASCII / 全角标点(含 。、《》、（）、，！？「」、)
)


def count_zh(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    # 移除代码块
    text_no_code = re.sub(r"```[\s\S]*?```", "", text)
    # 移除 markdown 标记(简化: 标题 #, 列表 -, 引用 >)
    text_clean = re.sub(r"^#+\s*", "", text_no_code, flags=re.MULTILINE)
    text_clean = re.sub(r"^[\s]*[-*+]\s*", "", text_clean, flags=re.MULTILINE)
    text_clean = re.sub(r"^>\s*", "", text_clean, flags=re.MULTILINE)
    # 移除 YAML 前置元数据
    if text_clean.startswith("---"):
        end = text_clean.find("\n---", 4)
        if end != -1:
            text_clean = text_clean[end + 4:]

    total = len(ZH_PATTERN.findall(text_clean))
    return {
        "file": str(path),
        "total_zh_chars": total,
        "raw_chars": len(text),
        "clean_chars": len(text_clean),
        "target": "8000-10000",
        "ok": 8000 <= total <= 11000,  # 留 10% 上限缓冲
    }


def main():
    parser = argparse.ArgumentParser(description="中文字数统计(目标 8000-10000)")
    parser.add_argument("target", help="文件或目录")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"❌ 不存在: {target}")
        return 2

    if target.is_dir():
        files = sorted(target.glob("*.md"))
    else:
        files = [target]

    if not files:
        print(f"⚠️ 没有 md 文件")
        return 0

    results = [count_zh(f) for f in files]
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0 if not [r for r in results if not r["ok"]] else 1
    else:
        print(f"=== 中文字数报告 ===")
        for r in results:
            status = "✅" if r["ok"] else "❌"
            print(f"[{status}] {Path(r['file']).name}")
            print(f"     中文字符: {r['total_zh_chars']:>6}  (目标 {r['target']})")
            print(f"     原始字符: {r['raw_chars']:>6}")
            print(f"     清理字符: {r['clean_chars']:>6}")

    bad = [r for r in results if not r["ok"]]
    print()
    if bad:
        print(f"❌ {len(bad)} 个文件未达标 (8000-10000 中文字)")
    else:
        print(f"✅ 所有 {len(results)} 个文件均达标")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
