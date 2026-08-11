#!/usr/bin/env python3
"""
integrate_book.py — 全书整合: 序言 + 全部章节合并为 _COMPLETE_BOOK.md

用法:
    python3 integrate_book.py \
        --book-dir book-projects/<书名> \
        --preface 序言.md \
        --outline OUTLINE.md \
        --output _COMPLETE_BOOK.md

    # 仅做完成度检查,不整合
    python3 integrate_book.py --check \
        --book-dir book-projects/<书名> \
        --outline OUTLINE.md

退出码: 0 = 全部成功,1 = 有缺失章节,2 = 参数/路径错误
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path


def parse_outline(outline_path: Path) -> list[dict]:
    """解析 OUTLINE.md,提取章节顺序 + 标题。
    格式约定:
      ## 第 N 章 [标题]
      ## 第 N 章: [标题]
      ## 第 N 章：[标题]   （全角冒号）
    """
    text = outline_path.read_text(encoding="utf-8")
    chapters = []
    for line in text.splitlines():
        m = re.match(r"^#{1,3}\s*第\s*(\d+)\s*章\s*[:：\s]\s*(.+?)\s*$", line)
        if m:
            chapters.append({
                "num": int(m.group(1)),
                "title": m.group(2).strip(),
                "filename": f"ch{int(m.group(1)):02d}_{m.group(2).strip()}.md",
            })
    return chapters


def check_completion(book_dir: Path, chapters: list[dict]) -> dict:
    chapters_dir = book_dir / "chapters"
    missing = []
    present = []
    for ch in chapters:
        candidates = list(chapters_dir.glob(f"ch{int(ch['num']):02d}*.md")) + \
                     list(chapters_dir.glob(f"ch{ch['num']}*.md"))
        candidates = [c for c in candidates if not c.name.startswith("_")]
        if candidates:
            present.append({"ch": ch, "path": candidates[0]})
        else:
            missing.append(ch)
    return {"present": present, "missing": missing}


def integrate(book_dir: Path, preface_path: Path, outline_path: Path, output_path: Path) -> int:
    chapters = parse_outline(outline_path)
    if not chapters:
        print(f"❌ 从 {outline_path} 未解析到任何章节")
        return 2
    print(f"✓ 从大纲解析到 {len(chapters)} 章: {[c['title'] for c in chapters]}")
    print()

    status = check_completion(book_dir, chapters)
    if status["missing"]:
        print(f"❌ 缺失 {len(status['missing'])} 章:")
        for ch in status["missing"]:
            print(f"  - 第{ch['num']}章 {ch['title']}  ({ch['filename']})")
        return 1

    print(f"✓ 所有 {len(chapters)} 章本地文件齐全")
    print(f"✓ 开始整合到 {output_path}")
    print()

    # 构建输出
    title = book_dir.name
    today = datetime.now().strftime("%Y-%m-%d")
    lines = []
    lines.append(f"# 《{title}》")
    lines.append("")
    lines.append(f"> 作者: 用户  ")
    lines.append(f"> 完成时间: {today}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 序言
    if preface_path.exists():
        preface_text = preface_path.read_text(encoding="utf-8").strip()
        lines.append("## 序言")
        lines.append("")
        lines.append(preface_text)
        lines.append("")
        lines.append("---")
        lines.append("")
    else:
        print(f"⚠️ 序言文件不存在: {preface_path}(会跳过)")

    # 目录
    lines.append("## 目录")
    lines.append("")
    if preface_path.exists():
        lines.append("- 序言")
    for ch in chapters:
        lines.append(f"- 第{ch['num']}章 {ch['title']}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 正文
    for item in status["present"]:
        ch = item["ch"]
        path = item["path"]
        lines.append(f"## 第{ch['num']}章 {ch['title']}")
        lines.append("")
        body = path.read_text(encoding="utf-8").strip()
        lines.append(body)
        lines.append("")
        lines.append("---")
        lines.append("")
        print(f"  ✓ 第{ch['num']}章: {path.name}")

    full = "\n".join(lines)
    output_path.write_text(full, encoding="utf-8")
    print()
    print(f"=== 整合完成: {output_path} ===")
    print(f"总字符数: {len(full)}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="整合序言 + 所有章节为完整书稿")
    parser.add_argument("--book-dir", required=True, help="书的项目目录")
    parser.add_argument("--preface", default="序言.md", help="序言文件路径")
    parser.add_argument("--outline", default="OUTLINE.md", help="大纲文件路径")
    parser.add_argument("--output", default="_COMPLETE_BOOK.md", help="输出文件名")
    parser.add_argument("--check", action="store_true", help="仅做完成度检查")
    args = parser.parse_args()

    book_dir = Path(args.book_dir)
    if not book_dir.exists():
        print(f"❌ 书目录不存在: {book_dir}")
        return 2

    outline = book_dir / args.outline
    preface = book_dir / args.preface
    output = book_dir / args.output

    if args.check:
        chapters = parse_outline(outline)
        status = check_completion(book_dir, chapters)
        print(f"=== 《{book_dir.name}》完成度检查 ===")
        print(f"大纲章节: {len(chapters)}")
        print(f"本地齐全: {len(status['present'])}")
        print(f"本地缺失: {len(status['missing'])}")
        for ch in status["missing"]:
            print(f"  ❌ 第{ch['num']}章 {ch['title']}")
        return 0 if not status["missing"] else 1

    return integrate(book_dir, preface, outline, output)


if __name__ == "__main__":
    sys.exit(main())
