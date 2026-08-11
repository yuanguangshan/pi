#!/usr/bin/env python3
"""
punctuation_check.py — 中文写作标点六项体检

六项全角标点体检 = ① 双引号 “” 配对 ② 句号 。（非 .） ③ 顿号 、（非 ,）
                 ④ 书名号 《》（非 <>） ⑤ 括号 （）（非 ()） ⑥ 破折号 ——（非 --）

体检脚本跳过代码块 ``` ... ``` 内部，只检查正文中标点。

用法:
    python3 punctuation_check.py <md或txt文件>
    python3 punctuation_check.py chapters/      # 目录模式，检查所有 md

退出码:
    0 = 六项全过
    1 = 存在未通过项
    2 = 参数错误
"""

import re
import sys
from pathlib import Path

# 跳过代码块: ```....``` 区域
CODE_FENCE = re.compile(r"```[\s\S]*?```", re.MULTILINE)

# Unicode 常量
LDQUO = "\u201c"  # “
RDQUO = "\u201d"  # ”
FULL_STOP = "\u3002"  # 。
IDEO_COMMA = "\u3001"  # 、 顿号
LANGLE_BK = "\u300A"  # 《
RANGLE_BK = "\u300B"  # 》
LPAREN_FULL = "\uFF08"  # （
RPAREN_FULL = "\uFF09"  # ）

# 违规字符
ASCII_DQUO = '"'
ASCII_STOP = "."
ASCII_COMMA = ","  # 仅在中文并列场景才视为违规，这里给警告级信号
ASCII_LT = "<"
ASCII_GT = ">"
ASCII_LPAREN = "("
ASCII_RPAREN = ")"
ASCII_DOUBLE_HYPHEN = "--"


def remove_code_blocks(text: str) -> str:
    """移除所有围栏代码块，只对正文体检。"""
    return CODE_FENCE.sub("", text)


def check_chinese_double_quotes(text: str) -> dict:
    """项 1: 中文正文不应出现 ASCII 双引号 "，全角双引号 “” 必须左右配对。"""
    ascii_count = text.count(ASCII_DQUO)
    left = text.count(LDQUO)
    right = text.count(RDQUO)
    violations = []
    if ascii_count > 0:
        violations.append({
            "line": 0,
            "text": f"发现 ASCII 双引号 {ascii_count} 处(应为 0)，应改为中文双引号",
        })
    if left != right:
        violations.append({
            "line": 0,
            "text": f"中文双引号不平衡(左 {left} / 右 {right})",
        })
    return {
        "name": '双引号 ""',
        "left": left,
        "right": right,
        "ascii_count": ascii_count,
        "violations": violations,
        "passed": ascii_count == 0 and left == right,
    }


def check_period(text: str) -> dict:
    """项 2: 中文正文不应使用 ASCII 句点。
    规则: 前一个字符是中文时，后面的 ASCII '.' 一律视为违规，
    不限于后随中文/空白/行尾（“中文.See”这种 . 后跟英文的混排也必检）。
    数字/英文如 3.12、v1.2 因前一字符非中文而天然豁免。
    """
    chinese_re = re.compile(r"([\u4e00-\u9fa5])\.")
    violations = []
    for m in chinese_re.finditer(text):
        idx = m.start() + 1  # . 的位置（中文后的第一个字符）
        line_no = text[:idx].count("\n") + 1
        line_start = text.rfind("\n", 0, idx) + 1
        line_end = text.find("\n", idx)
        if line_end == -1:
            line_end = len(text)
        line_text = text[line_start:line_end]
        violations.append({"line": line_no, "text": line_text.strip()[:80]})
    return {
        "name": "句号 ASCII '.'",
        "violations": violations[:10],  # 最多报 10 条
        "passed": len(violations) == 0,
    }


def check_comma(text: str) -> dict:
    """项 3: 中文并列场景的 ASCII ',' 视为违规（报警，不自动改）。"""
    chinese_re = re.compile(r"[\u4e00-\u9fa5],(?=[\u4e00-\u9fa5])")
    violations = []
    for m in chinese_re.finditer(text):
        idx = m.start() + 1  # , 的位置
        line_no = text[:idx].count("\n") + 1
        line_start = text.rfind("\n", 0, idx) + 1
        line_end = text.find("\n", idx)
        if line_end == -1:
            line_end = len(text)
        line_text = text[line_start:line_end]
        violations.append({"line": line_no, "text": line_text.strip()[:80]})
    return {
        "name": "顿号 ASCII ','",
        "violations": violations[:10],
        "passed": len(violations) == 0,
    }


def check_book_title(text: str) -> dict:
    """项 4: 书名号《》— ASCII '<...>' 不应出现书名上下文。
    启发: 包含中文的 <> 视为书名号违规。
    """
    pattern = re.compile(r"<([^<>]{2,40})>")
    violations = []
    for m in pattern.finditer(text):
        inner = m.group(1)
        if re.search(r"[\u4e00-\u9fa5]", inner):
            idx = m.start()
            line_no = text[:idx].count("\n") + 1
            violations.append({
                "line": line_no,
                "text": f"<{inner}> 应改为 《{inner}》",
            })
    return {
        "name": "书名号 ASCII '<>'",
        "violations": violations[:10],
        "passed": len(violations) == 0,
    }


def check_parens(text: str) -> dict:
    """项 5: 中文括号应是全角 （） 而非 ASCII ()。
    启发: 中文字符后紧跟的 ASCII '(' 或中文前紧邻的 ')' 视为违规。
    """
    left_violations = list(re.finditer(r"[\u4e00-\u9fa5]\(", text))
    right_violations = list(re.finditer(r"\)[\u4e00-\u9fa5]", text))
    violations = []
    for m in left_violations[:5]:
        idx = m.start() + 1
        line_no = text[:idx].count("\n") + 1
        violations.append({"line": line_no, "text": f"中文后接 '(' 应改为 （"})
    for m in right_violations[:5]:
        idx = m.start()
        line_no = text[:idx].count("\n") + 1
        violations.append({"line": line_no, "text": f"中文前 ')' 应改为 ）"})
    return {
        "name": "括号 ASCII '()'",
        "violations": violations[:10],
        "passed": len(violations) == 0,
    }


def check_em_dash(text: str) -> dict:
    """项 6: 破折号应使用 ——（两个 em dash），不是 --（两个 hyphen）。"""
    pattern = re.compile(r"(?<!-)-{2}(?!-)")  # 不是更长横线的一部分
    violations = []
    for m in pattern.finditer(text):
        idx = m.start()
        line_no = text[:idx].count("\n") + 1
        line_start = text.rfind("\n", 0, idx) + 1
        line_end = text.find("\n", idx)
        if line_end == -1:
            line_end = len(text)
        line_text = text[line_start:line_end]
        violations.append({"line": line_no, "text": line_text.strip()[:80]})
    return {
        "name": "破折号 ASCII '--'",
        "violations": violations[:10],
        "passed": len(violations) == 0,
    }


CHECKS = [
    check_chinese_double_quotes,
    check_period,
    check_comma,
    check_book_title,
    check_parens,
    check_em_dash,
]


def run_on_file(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    clean_text = remove_code_blocks(text)

    print(f"=== 中文标点体检报告 ===")
    print(f"文件: {path}")
    print(f"原始字符数: {len(text)}  正文字符数(去除代码块后): {len(clean_text)}")
    print()

    passed_count = 0
    for i, check in enumerate(CHECKS, 1):
        result = check(clean_text)
        status = "✅" if result["passed"] else "❌"
        if result["passed"]:
            passed_count += 1
        detail = ""
        if "left" in result:
            detail = f"(左{result['left']} 右{result['right']})"
        elif "violations" in result:
            detail = f"(违规 {len(result['violations'])} 处)"
        print(f"[{i}/6] {result['name']}: {status} {detail}")
        if not result["passed"] and result["violations"]:
            for v in result["violations"][:5]:
                print(f"     L{v['line']}: {v['text']}")
    print()
    print(f"六项总分: {passed_count}/6")
    print(f"总判定: {'✅ 通过' if passed_count == 6 else '❌ 未通过(需修复)'}")
    return 0 if passed_count == 6 else 1


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)

    target = Path(sys.argv[1])
    if target.is_dir():
        files = sorted(target.rglob("*.md"))
        if not files:
            files = sorted(target.rglob("*.txt"))
        rc = 0
        for f in files:
            sub_rc = run_on_file(f)
            rc = max(rc, sub_rc)
            print()
        sys.exit(rc)
    else:
        sys.exit(run_on_file(target))


if __name__ == "__main__":
    main()
