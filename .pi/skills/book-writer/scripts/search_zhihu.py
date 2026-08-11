#!/usr/bin/env python3
"""
search_zhihu.py — 知乎搜索（高质量社区内容，供写书资料搜集优先调用）

通过知乎开放平台搜索知乎站内内容。通道自动探测，Mac/Linux 通吃：
  1. zhihu-cli（macOS 官方 CLI，凭证存 Keychain；Linux 无官方二进制时不可用）
  2. HTTP API 直连（https://developer.zhihu.com/api/v1/content/zhihu_search，
     Bearer 鉴权；CLI 不可用或调用失败时的自动降级通道）

凭证（按优先级）:
  1. 环境变量 ZHIHU_ACCESS_SECRET
  2. ~/.pi/agent/auth.json 的 zhihu.access_secret 条目
  3. zhihu-cli 已存入 macOS Keychain（auth set 配置过）

用法:
    python3 search_zhihu.py "Transformer 架构 历史"
    python3 search_zhihu.py "搜索：AI Agent 案例" --count 10 --out materials/raw_xx_zhihu.md

退出码:
    0 = 成功
    1 = 搜索失败 / 未配置凭证
    2 = 参数错误
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

CLI_DEFAULT = Path.home() / "Library/Application Support/zhihu-cli/current/zhihu-cli"
HTTP_API = "https://developer.zhihu.com/api/v1/content/zhihu_search"


def user_agent() -> str:
    """平台自适应 User-Agent（macOS / Linux）。"""
    if platform.system() == "Darwin":
        return "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    return "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"


def find_cli() -> Path:
    """定位 zhihu-cli：环境变量 ZHIHU_CLI 优先，否则默认安装路径 / PATH。"""
    env = os.environ.get("ZHIHU_CLI")
    if env:
        p = Path(env)
        if p.exists():
            return p
    if CLI_DEFAULT.exists():
        return CLI_DEFAULT
    import shutil
    p = shutil.which("zhihu-cli")
    if p:
        return Path(p)
    return CLI_DEFAULT


def read_secret() -> str:
    """按优先级读取 Access Secret：env > auth.json（Keychain 由 CLI 侧持有）。"""
    if os.environ.get("ZHIHU_ACCESS_SECRET"):
        return os.environ["ZHIHU_ACCESS_SECRET"]
    auth = os.path.expanduser("~/.pi/agent/auth.json")
    if os.path.exists(auth):
        try:
            data = json.load(open(auth, encoding="utf-8"))
            zh = data.get("zhihu") or {}
            if zh.get("access_secret"):
                return zh["access_secret"]
        except Exception:
            pass
    return ""


def cli_credentials(cli: Path) -> bool:
    """检测 CLI keychain 凭证（兼容 zhihu-cli 0.2.x 的 auth status 输出格式）。

    用 --verify 实际验证一次，verification=valid 才是真可用；
    早期版本用 "keychain":"configured/available" 表示已配置，兼容两种取值。
    """
    try:
        r = subprocess.run(
            [str(cli), "auth", "status", "--verify"],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(r.stdout)
        return (
            data.get("verification") == "valid"
            or data.get("keychain") in ("available", "configured")
            or data.get("configured") is True
        )
    except Exception:
        return False


def search_http(secret: str, query: str, count: int) -> dict:
    """HTTP API 直连搜索（Linux 无 CLI / CLI 失败时的降级通道）。"""
    params = urllib.parse.urlencode({"Query": query, "Count": min(count, 10)})
    url = f"{HTTP_API}?{params}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {secret}",
        "X-Request-Timestamp": str(int(time.time())),
        "Content-Type": "application/json",
        "User-Agent": user_agent(),
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("Code") != 0:
        raise RuntimeError(data.get("Message", f"搜索失败（Code={data.get('Code')}）"))
    return data


def search_cli(cli: Path, query: str, count: int) -> dict:
    cmd = [str(cli), "search", "zhihu", "--query", query, "--count", str(count)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip() or "zhihu-cli 调用失败")
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"zhihu-cli 输出非 JSON: {r.stdout[:200]}")
    if data.get("Code") != 0:
        raise RuntimeError(data.get("Message", "搜索失败"))
    return data


def render_markdown(query: str, items: list, via: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# 知乎搜索: {query}", "", f"> 抓取时间: {now} | 来源: 知乎站内搜索（{via}）", f"> 结果: {len(items)} 条", ""]
    for i, it in enumerate(items, 1):
        title = it.get("Title", "(无标题)")
        author = it.get("AuthorName", "")
        url = it.get("Url", "")
        ctype = it.get("ContentType", "")
        votes = it.get("VoteUpCount", 0)
        comments = it.get("CommentCount", 0)
        badge = it.get("AuthorBadgeText", "")
        text = (it.get("ContentText", "") or "").strip()
        if len(text) > 600:
            text = text[:600] + "…"
        lines.append(f"## {i}. {title}")
        meta = f"- 作者: {author}" + (f"（{badge}）" if badge else "")
        meta += f" | 类型: {ctype} | 赞同: {votes} | 评论: {comments}"
        lines.append(meta)
        lines.append(f"- 链接: {url}")
        lines.append("")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="知乎搜索（写书资料搜集优先通道）")
    parser.add_argument("query", help="搜索问题")
    parser.add_argument("--count", type=int, default=10, help="返回条数（1-10，默认 10）")
    parser.add_argument("--out", help="把结果写入文件（推荐存 materials/）")
    args = parser.parse_args()

    secret = read_secret()
    cli = find_cli()

    if cli.exists() and (secret or cli_credentials(cli)):
        via = "zhihu-cli"
        try:
            data = search_cli(cli, args.query, args.count)
        except Exception as e:
            if not secret:
                print(f"⚠️ zhihu-cli 失败且无 HTTP 凭证，放弃: {e}")
                return 1
            print(f"⚠️ zhihu-cli 失败（{e}），降级 HTTP API…")
            data = search_http(secret, args.query, args.count)
            via = "HTTP API"
    elif secret:
        data = search_http(secret, args.query, args.count)
        via = "HTTP API"
    else:
        print("❌ 未配置知乎凭证。设置环境变量 ZHIHU_ACCESS_SECRET 或 ~/.pi/agent/auth.json 的 zhihu.access_secret。")
        return 1

    items = data.get("Data", {}).get("Items", [])
    if not items:
        print("⚠️ 搜索无结果")
        return 1

    md = render_markdown(args.query, items, via)
    print(md)
    if args.out:
        out_path = os.path.abspath(args.out)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        Path(out_path).write_text(md, encoding="utf-8")
        print(f"\n已写入: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
