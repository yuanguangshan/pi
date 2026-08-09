#!/usr/bin/env python3
"""
notify_wechat.py — 写书完成时通过微信推送通知

凭证不从代码读取，从以下位置按序获取（都不包含敏感信息）：
  1. 环境变量 WECHAT_PUSH_URL / WECHAT_PUSH_TOKEN
  2. ~/.pi/agent/auth.json 的 "wechat-push" 条目（{"url": ..., "token": ...}）

用法:
    python3 notify_wechat.py --book-name 淀山湖 --chapters 4 --total-words 34012 \
        --complete-book-path book-projects/淀山湖/_COMPLETE_BOOK.md
    python3 notify_wechat.py --book-name 淀山湖 --dry-run   # 只打印不发送

退出码:
    0 = 推送成功
    2 = 未配置凭证 / 网络不可达（调用方可视为“跳过通知，不阻塞”）
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_PUSH_URL = "https://api.yuangs.cc/weixinpush"


def load_config() -> dict:
    """返回 {url, token}；未配置 token 则返回空 dict。"""
    cfg = {}
    auth = os.path.expanduser("~/.pi/agent/auth.json")
    if os.path.exists(auth):
        try:
            data = json.load(open(auth, encoding="utf-8"))
            k = data.get("wechat-push") or {}
            if k.get("url"):
                cfg["url"] = k["url"]
            if k.get("token"):
                cfg["token"] = k["token"]
        except Exception:
            pass
    cfg["url"] = os.environ.get("WECHAT_PUSH_URL", cfg.get("url", DEFAULT_PUSH_URL))
    cfg["token"] = os.environ.get("WECHAT_PUSH_TOKEN", cfg.get("token", ""))
    return cfg


def build_message(book_name: str, chapters: int, total_words: str, complete_path: str, extras: list[str]) -> str:
    lines = [
        f"📚 《{book_name.strip('《》')}》写书完成",
        "",
        f"✅ 章节: {chapters} 章（已通过中文标点六项体检）",
        f"📝 总字数: {total_words} 字",
        f"📄 完整书稿: {complete_path}",
    ]
    if extras:
        lines.append("")
        lines.append("📌 备注:")
        for e in extras:
            lines.append(f"  - {e}")
    lines.append("")
    lines.append("— 雨轩于听雨轩 🌧️🏠")
    return "\n".join(lines)


def send(content: str, cfg: dict) -> int:
    body = json.dumps({"msgtype": "text", "content": content}).encode("utf-8")
    req = urllib.request.Request(
        cfg["url"],
        data=body,
        headers={
            "Authorization": f"Bearer {cfg['token']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return 0 if r.status == 200 else 1
    except urllib.error.URLError:
        return 2
    except Exception:
        return 1


def main():
    parser = argparse.ArgumentParser(description="写书完成 → 微信通知")
    parser.add_argument("--book-name", required=True, help="书名")
    parser.add_argument("--chapters", type=int, default=0, help="章节数")
    parser.add_argument("--total-words", default="", help="总字数")
    parser.add_argument("--complete-book-path", default="", help="完整书稿路径")
    parser.add_argument("--extra", action="append", default=[], help="附加备注行")
    parser.add_argument("--dry-run", action="store_true", help="只打印消息不发送")
    args = parser.parse_args()

    msg = build_message(args.book_name, args.chapters, args.total_words,
                        args.complete_book_path, args.extra)
    print("=== 待推送微信消息 ===")
    print(msg)
    print("=" * 40)

    if args.dry_run:
        return 0

    cfg = load_config()
    if not cfg["token"]:
        print("⚠️ 未配置微信凭证（~/.pi/agent/auth.json 的 wechat-push 条目或环境变量 WECHAT_PUSH_TOKEN），跳过通知")
        return 2

    rc = send(msg, cfg)
    if rc == 0:
        print("✅ 微信通知已发送")
    elif rc == 2:
        print("⚠️ 网络不可达，跳过通知（不阻塞）")
    else:
        print("⚠️ 微信通知失败（不阻塞）")
    return 0  # 通知失败不阻塞流水线


if __name__ == "__main__":
    sys.exit(main())
