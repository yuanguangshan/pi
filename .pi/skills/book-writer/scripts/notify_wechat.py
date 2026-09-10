#!/usr/bin/env python3
"""
notify_wechat.py — 写书完成时通过微信渠道通知广山哥

封装 wechat-send 脚本。默认接收人:广山哥。

用法:
    python3 notify_wechat.py \
        --book-name "《书名》" \
        --chapters N \
        --total-words "XX,XXX" \
        --complete-book-path "_COMPLETE_BOOK.md"

退出码:
    0 = 推送成功
    1 = 推送失败(已写失败日志,后续可手工重试)
    2 = 参数错误
"""

import argparse
import subprocess
import sys
from pathlib import Path

WECHAT_SEND_SCRIPT = "~/.pi/agent/skills/wechat-send/scripts/send.py"


def build_message(book_name: str, chapters: int, total_words: str, complete_path: str, extras: list[str]) -> str:
    lines = [
        f"📚 {book_name} 写书完成",
        "",
        f"✅ 章节: {chapters} 章(已通过中文标点六项体检)",
        f"📝 总字数: {total_words} 字",
        f"💾 双备份通道:",
        f"   - ima 知识库:yuangs/books/{book_name.strip('《》')}/",
        f"   - Knowly 服务器:/knowly_data/{book_name.strip('《》')}/",
        f"📄 完整书稿:{complete_path}",
    ]
    if extras:
        lines.append("")
        lines.append("📌 备注:")
        for e in extras:
            lines.append(f"  - {e}")
    lines.append("")
    lines.append("— 雨轩于听雨轩 🌧️🏠")
    return "\n".join(lines)


def send(message: str) -> int:
    """调用 wechat-send/scripts/send.py,消息内容作为命令行参数传递。"""
    send_script = Path(WECHAT_SEND_SCRIPT).expanduser()
    if not send_script.exists():
        print(f"⚠️ wechat-send 脚本不存在: {send_script}")
        return 1
    try:
        result = subprocess.run(
            [sys.executable, str(send_script), message],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.returncode
    except subprocess.TimeoutExpired:
        return 1


def main():
    parser = argparse.ArgumentParser(description="写书完成 → 微信通知")
    parser.add_argument("--book-name", required=True, help="书名(可含《》)")
    parser.add_argument("--chapters", type=int, default=0, help="章节数")
    parser.add_argument("--total-words", default="", help="总字数")
    parser.add_argument("--complete-book-path", default="", help="完整书稿文件名")
    parser.add_argument("--extra", action="append", default=[], help="附加备注行")
    parser.add_argument("--dry-run", action="store_true", help="只打印消息不发送")
    args = parser.parse_args()

    msg = build_message(args.book_name, args.chapters, args.total_words, args.complete_book_path, args.extra)
    print("=== 待推送微信消息 ===")
    print(msg)
    print("=" * 40)

    if args.dry_run:
        return 0

    rc = send(msg)
    if rc == 0:
        print("✅ 微信通知已发送")
    else:
        print(f"⚠️ 微信通知失败(退出码 {rc})")
    return rc


if __name__ == "__main__":
    sys.exit(main())
