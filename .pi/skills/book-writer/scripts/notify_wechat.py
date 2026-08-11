#!/usr/bin/env python3
"""
notify_wechat.py — 写书完成时通过微信推送通知

通道自动探测（pi / hermes 等环境通吃）：
  1. weclaw CLI（/usr/local/bin/weclaw send --to <user>@im.wechat，优先）
  2. weixinpush HTTP API（https://api.yuangs.cc/weixinpush，weclaw 不可用时兜底）

凭证/目标（都不包含敏感信息）：
  1. 环境变量 WECLAW_TO（默认 广山哥: o9cq80wpGQpRIUxH2LGdGFrksGak@im.wechat）
  2. weclaw CLI 路径: /usr/local/bin/weclaw
  3. 兜底 HTTP: 环境变量 WECHAT_PUSH_URL / WECHAT_PUSH_TOKEN，
     或 ~/.pi/agent/auth.json 的 "wechat-push" 条目（{"url": ..., "token": ...}）

用法:
    python3 notify_wechat.py --book-name 淀山湖 --chapters 4 --total-words 34012 \
        --complete-book-path book-projects/淀山湖/_COMPLETE_BOOK.md
    python3 notify_wechat.py --book-name 淀山湖 --dry-run   # 只打印不发送

退出码:
    0 = 推送成功
    2 = 未配置通道 / 网络不可达（调用方可视为“跳过通知，不阻塞”）
"""

import argparse
import json
import os
import subprocess
import sys

WECLAW_BIN = "/usr/local/bin/weclaw"
DEFAULT_TO = "o9cq80wpGQpRIUxH2LGdGFrksGak@im.wechat"  # 广山哥
DEFAULT_PUSH_URL = "https://api.yuangs.cc/weixinpush"


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


def send_via_weclaw(content: str, to: str) -> int:
    """weclaw CLI 发送（原生通道，优先）。"""
    try:
        r = subprocess.run(
            [WECLAW_BIN, "send", "--to", to, "--text", content],
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError:
        return 2
    except Exception:
        return 1
    if r.returncode == 0:
        return 0
    # ret=-2 等错误：打印诊断，不阻塞
    print(f"⚠️ weclaw 发送失败: {r.stdout[:200]} {r.stderr[:200]}")
    return 1


def http_config() -> tuple[str, str]:
    """HTTP 兜底通道的 (url, token)：env 优先，其次 auth.json 的 wechat-push 条目。"""
    url = os.environ.get("WECHAT_PUSH_URL", DEFAULT_PUSH_URL)
    token = os.environ.get("WECHAT_PUSH_TOKEN", "")
    if token:
        return url, token
    auth = os.path.expanduser("~/.pi/agent/auth.json")
    if os.path.exists(auth):
        try:
            data = json.load(open(auth, encoding="utf-8"))
            k = data.get("wechat-push") or {}
            url = k.get("url", url)
            token = k.get("token", "")
        except Exception:
            pass
    return url, token


def send_via_http(content: str) -> int:
    """兜底 HTTP 通道（weixinpush，若配置了 token）。"""
    import urllib.error
    import urllib.request

    url, token = http_config()
    if not token:
        return 2
    body = json.dumps({"msgtype": "text", "content": content}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
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
    parser.add_argument("--to", default=os.environ.get("WECLAW_TO", DEFAULT_TO), help="微信目标用户")
    parser.add_argument("--dry-run", action="store_true", help="只打印消息不发送")
    args = parser.parse_args()

    msg = build_message(args.book_name, args.chapters, args.total_words,
                        args.complete_book_path, args.extra)
    print("=== 待推送微信消息 ===")
    print(msg)
    print("=" * 40)

    if args.dry_run:
        return 0

    rc = send_via_weclaw(msg, args.to)
    if rc == 0:
        print(f"✅ 微信通知已发送 (weclaw → {args.to})")
        return 0
    if rc == 2:
        print(f"⚠️ weclaw CLI 不可用（{WECLAW_BIN} 不存在），尝试 HTTP 兜底…")
        rc = send_via_http(msg)
        if rc == 0:
            print("✅ 微信通知已发送 (HTTP)")
            return 0
        print("⚠️ HTTP 兜底也未配置/失败，跳过通知（不阻塞）")
        return 0
    print("⚠️ 微信通知失败（不阻塞）")
    return 0  # 通知失败不阻塞流水线


if __name__ == "__main__":
    sys.exit(main())
