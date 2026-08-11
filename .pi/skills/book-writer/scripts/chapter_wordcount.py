#!/usr/bin/env python3
"""
chapter_wordcount.py — 中文字数统计 + 区间惩罚评分

中文书写项目的字数统计按"中文字符 + 全角标点"计，英文/数字/空白不算。
目标每章 8000-10000 中文字符（含全角标点），理想值 9000（区间中点）。

区间惩罚（而非单一下限判定）:
    惩罚分 0-100，偏离目标区间/理想值越远，惩罚越高。
    区间内 [8000, 10000]: 惩罚 = |字数 - 9000| / 20 → 0~50
        评级: 理想(±200) / 良好(±500) / 贴边(贴近边界)
    区间外: 惩罚 = 50 + 缺口或超出 每 800 字 +10 → 50~100（封顶）
        评级: 不足(< 8000) / 超出(> 10000)
    "贴边"= 擦线达标（在区间内但贴近边界），质量风险高，
    主控应参考惩罚分决定是否充实（至 8500+）或精简（至 9500-）后定稿。

用法:
    python3 chapter_wordcount.py <md或txt文件>
    python3 chapter_wordcount.py chapters/      # 目录模式
    python3 chapter_wordcount.py chapters/ --json

退出码:
    0 = 所有文件达标(8000-10000)
    1 = 有文件不达标（区间外）
    2 = 参数错误
"""

import argparse
import json
import re
import sys
from pathlib import Path

# CJK Unified Ideographs + CJK 扩展 A（汉字，不含标点）
HANZI_PATTERN = re.compile(
    r"[\u4e00-\u9fff"          # CJK 基本
    r"\u3400-\u4dbf]"           # CJK 扩展 A
)

# 全角标点 / 全角符号（与 references/punctuation-rules.md 六项对齐）：
#   \u3000-\u303f  CJK 符号和标点（。、 《》 「」 等，原先误归 U+FF 区而漏计）
#   \uff00-\uffef  全角形式（（），：；！？ 及全角数字）
#   \u2014\u2026\u201c\u201d  破折号/省略号/双引号（六项里落在一般标点区，CJK 标点区不含）
FULLWIDTH_PATTERN = re.compile(r"[\u3000-\u303f\uff00-\uffef\u2014\u2026\u201c\u201d]")

# 字数目标区间（含全角标点）与理想值
TARGET_LOW = 8000
TARGET_HIGH = 10000
TARGET_IDEAL = 9000


def compute_penalty(total: int) -> dict:
    """区间惩罚评分：偏离目标区间/理想值越远，惩罚越高（0-100）。

    区间内 [8000, 10000]: 惩罚 = |total - 9000| / 20 → 0~50
        评级: 理想(±200) / 良好(±500) / 贴边(贴近边界, 擦线达标)
    区间外: 惩罚 = 50 + 缺口/超出 每 800 字 +10 → 50~100（封顶）
        评级: 不足(< 8000) / 超出(> 10000)
    """
    if total < TARGET_LOW:
        gap = TARGET_LOW - total
        penalty = min(100.0, 50.0 + gap * 10.0 / 800.0)
        return {"penalty": round(penalty, 1), "grade": "不足", "detail": f"低于下限 {gap} 字"}
    if total > TARGET_HIGH:
        gap = total - TARGET_HIGH
        penalty = min(100.0, 50.0 + gap * 10.0 / 800.0)
        return {"penalty": round(penalty, 1), "grade": "超出", "detail": f"超出上限 {gap} 字"}
    deviation = abs(total - TARGET_IDEAL)
    penalty = deviation / 20.0
    if deviation <= 200:
        grade = "理想"
    elif deviation <= 500:
        grade = "良好"
    else:
        grade = "贴边"
    return {
        "penalty": round(penalty, 1),
        "grade": grade,
        "detail": f"距理想值 {TARGET_IDEAL} 偏差 {deviation} 字",
    }


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

    hanzi = len(HANZI_PATTERN.findall(text_clean))
    fullwidth = len(FULLWIDTH_PATTERN.findall(text_clean))
    total = hanzi + fullwidth  # 原口径: 汉字 + 全角标点
    penalty_info = compute_penalty(total)
    return {
        "file": str(path),
        "hanzi_chars": hanzi,          # 汉字数（不含标点），读者实际感知量
        "fullwidth_chars": fullwidth,  # 全角标点/全角字符数
        "total_zh_chars": total,       # 含标点口径（达标判定用，与历史一致）
        "raw_chars": len(text),
        "clean_chars": len(text_clean),
        "target": f"{TARGET_LOW}-{TARGET_HIGH}(含标点, 理想 {TARGET_IDEAL})",
        "ok": TARGET_LOW <= total <= TARGET_HIGH,
        **penalty_info,
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
            print(f"[{status} {r['grade']}] {Path(r['file']).name}")
            print(f"     中文字符(不含标点): {r['hanzi_chars']:>6}  (读者感知量)")
            print(f"     含全角标点字符:   {r['total_zh_chars']:>6}  (目标 {r['target']})")
            print(f"     区间惩罚:          {r['penalty']:>5}/100  (评级 {r['grade']}; {r['detail']})")
            print(f"     原始字符:          {r['raw_chars']:>6}")
            print(f"     清理字符:          {r['clean_chars']:>6}")

    bad = [r for r in results if not r["ok"]]
    edge = [r for r in results if r["ok"] and r["grade"] == "贴边"]
    avg_penalty = sum(r["penalty"] for r in results) / len(results)
    print()
    if bad:
        print(f"❌ {len(bad)} 个文件不达标 (区间外: {TARGET_LOW}-{TARGET_HIGH} 中文字)")
        for r in bad:
            print(f"   ❌ {Path(r['file']).name}  惩罚 {r['penalty']}/100  ({r['detail']})")
    elif edge:
        print(f"✅ 所有 {len(results)} 个文件均达标，但 {len(edge)} 个评级为贴边(擦线达标):")
        for r in edge:
            print(f"   ⚠️ {Path(r['file']).name}  惩罚 {r['penalty']}/100  ({r['detail']})")
        print(f"   建议: 贴边章节充实至 {TARGET_IDEAL - 500}+ 或精简至 {TARGET_IDEAL + 500}- 后定稿")
    else:
        print(f"✅ 所有 {len(results)} 个文件均达标")
    print(f"平均区间惩罚: {avg_penalty:.1f}/100")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
