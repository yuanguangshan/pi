#!/usr/bin/env python3
"""
fetch_zhihu_full.py — 知乎链接 → 全文抓取（写书资料搜集用）

输入知乎链接（或含链接的文件），通过本机 knowly 的完整链路抓取全文：
提交 knasync（Chrome 扩展抓取）→ 轮询 knowly history → 拉全文 → 清洗 → 落盘。

解决写书资料搜集的痛点：zhihu-cli 搜索只返回摘要+链接，本脚本拿到链接后
把全文抓回来，作为 materials/ 素材。

依赖（全部本机）:
  - knowly 守护进程（http://127.0.0.1:8090，含 knasync 提交与 history/full API）
  - Chrome 知乎扩展在线（否则提交成功但无结果，超时后脚本提示）

凭证:
  - 从 ~/.knowly/config.json 读取 knasync endpoint/auth_key 与 web.auth（Basic auth）
  - 可用环境变量覆盖: ZHIHU_KNASYNC_ENDPOINT / ZHIHU_KNASYNC_KEY / KNOWLY_BASE_URL / KNOWLY_BASIC_AUTH

用法:
    python3 fetch_zhihu_full.py "https://www.zhihu.com/question/123/answer/456"
    python3 fetch_zhihu_full.py "https://www.zhihu.com/question/123/answer/456" --out materials/raw_03_知乎全文.md
    python3 fetch_zhihu_full.py materials/raw_01_zhihu.md --out-dir materials/   # 从文件提取所有链接
    python3 fetch_zhihu_full.py <链接> --timeout 240 --clean                   # 清洗 frontmatter/img 残留

退出码:
    0 = 全部成功
    1 = 部分失败或超时
    2 = 参数错误 / 凭证不可用
"""

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

KNOWNLY_DEFAULT = "http://127.0.0.1:8090"
CONFIG_PATH = Path.home() / ".knowly/config.json"

URL_RE = re.compile(r"https?://[^\s\"'<>）)】\]]+")
ZHIHU_RE = re.compile(r"https?://[\w.-]*zhihu\.com[^\s\"'<>）)】\]]*")
FRONTMATTER_RE = re.compile(r"(?s)^---\n.*?\n---\n")
IMG_REMNANT_RE = re.compile(r"(?m)^\" data-[^\n]*?(?:origin_image|zh-lightbox|data-actualsrc)[^\n]*")
IMG_TAG_RE = re.compile(r"(?i)<img[^>]*>")
IMG_ACTUALSRC_RE = re.compile(r'data-actualsrc="([^"]+)"')
IMG_SRC_RE = re.compile(r'(?i)src="([^"]+)"')


def load_config() -> dict:
    """从 ~/.knowly/config.json 读取 knasync 与 web.auth 配置。"""
    cfg = {"base_url": os.environ.get("KNOWLY_BASE_URL", KNOWNLY_DEFAULT)}
    if not CONFIG_PATH.exists():
        return cfg
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        k = data.get("knasync") or {}
        if k.get("endpoint"):
            cfg["knasync_endpoint"] = k["endpoint"]
        if k.get("auth_key"):
            cfg["knasync_auth_key"] = k["auth_key"]
        if data.get("web", {}).get("auth"):
            cfg["basic_auth"] = data["web"]["auth"]
    except Exception:
        pass
    cfg["knasync_endpoint"] = os.environ.get("ZHIHU_KNASYNC_ENDPOINT", cfg.get("knasync_endpoint", ""))
    cfg["knasync_auth_key"] = os.environ.get("ZHIHU_KNASYNC_KEY", cfg.get("knasync_auth_key", ""))
    cfg["basic_auth"] = os.environ.get("KNOWLY_BASIC_AUTH", cfg.get("basic_auth", ""))
    return cfg


def http_json(url: str, cfg: dict, method="GET", body=None, headers=None, timeout=30):
    req_headers = {"Authorization": "Basic " + base64.b64encode(cfg["basic_auth"].encode()).decode()}
    if headers:
        req_headers.update(headers)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def submit_knasync(cfg: dict, url: str) -> str:
    """提交链接到 knasync，返回响应文本。"""
    endpoint = cfg["knasync_endpoint"].rstrip("/") + "/submit"
    body = json.dumps({"url": url}).encode("utf-8")
    req = urllib.request.Request(
        endpoint, data=body,
        headers={
            "Content-Type": "application/json",
            "X-Auth-Key": cfg["knasync_auth_key"],
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8").strip()


def knowly_history(cfg: dict, limit: int) -> list:
    return http_json(cfg["base_url"].rstrip("/") + f"/api/history?limit={limit}", cfg)


def knowly_full(cfg: dict, entry_id: str) -> str:
    try:
        d = http_json(cfg["base_url"].rstrip("/") + f"/api/history/{entry_id}/full", cfg, timeout=30)
        return d.get("content", "")
    except Exception:
        return ""


def knowly_latest_ts(cfg: dict) -> int:
    try:
        entries = knowly_history(cfg, 1)
        if entries:
            ts = time.mktime(time.strptime(entries[0]["timestamp"], "%Y-%m-%d %H:%M:%S"))
            return int(ts)
    except Exception:
        pass
    return 0


def clean_url(raw: str) -> str:
    """去掉 query/fragment，用于 URL 匹配。"""
    u = re.split(r"[?#]", raw)[0]
    return u.rstrip("/")


def extract_urls(text: str) -> list:
    return list(dict.fromkeys(ZHIHU_RE.findall(text)))


def fetch_one(cfg: dict, raw_url: str, timeout: int) -> str:
    """提交并等待全文，返回清洗后的 markdown。失败返回空串。"""
    clean = clean_url(raw_url)
    before = knowly_latest_ts(cfg)
    try:
        resp = submit_knasync(cfg, raw_url)
    except Exception as e:
        print(f"  ❌ 提交失败: {e}", file=sys.stderr)
        return ""
    print(f"  提交: {resp}")

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(8)
        try:
            entries = knowly_history(cfg, 30)
        except Exception as e:
            print(f"  ⚠️ history 查询失败: {e}", file=sys.stderr)
            continue
        for e in entries:
            ts = time.mktime(time.strptime(e["timestamp"], "%Y-%m-%d %H:%M:%S"))
            if int(ts) <= before:
                continue
            content = knowly_full(cfg, e["id"])
            if content and clean in content:
                return content
    return ""


def clean_content(content: str) -> str:
    """清洗 frontmatter 与图片残留；保留标题/作者/来源行（素材需标注来源）。"""
    content = FRONTMATTER_RE.sub("", content)

    def replace_img(m):
        s = m.group(0)
        m2 = IMG_ACTUALSRC_RE.search(s) or IMG_SRC_RE.search(s)
        return f"[图片 {m2.group(1)}]" if m2 else "[图片]"

    content = IMG_REMNANT_RE.sub(replace_img, content)
    content = IMG_TAG_RE.sub(replace_img, content)
    return content.strip()


def render_markdown(raw_url: str, content: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# 知乎全文（via knowly 抓取）", "",
             f"> 原始链接: {clean_url(raw_url)}", f"> 抓取时间: {now}", ""]
    lines.append(content)
    lines.append("")
    lines.append(f"---")
    lines.append(f"> 来源: {raw_url}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="知乎链接 → 全文抓取（写书资料搜集）")
    parser.add_argument("input", help="知乎链接 或 含链接的 md/文本文件")
    parser.add_argument("--out", help="输出文件路径（单个链接时）")
    parser.add_argument("--out-dir", help="输出目录（多个链接/文件时，按序号命名）")
    parser.add_argument("--timeout", type=int, default=180, help="单个链接最长等待秒数（默认 180）")
    parser.add_argument("--no-clean", action="store_true", help="不清洗 frontmatter 与图片残留（默认清洗）")
    args = parser.parse_args()

    cfg = load_config()
    if not cfg.get("knasync_endpoint") or not cfg.get("knasync_auth_key") or not cfg.get("basic_auth"):
        print("❌ 凭证不可用：需要 ~/.knowly/config.json（knasync + web.auth）或对应环境变量", file=sys.stderr)
        return 2

    # 提取链接
    inp = args.input
    if "://" in inp and "zhihu.com" in inp:
        urls = extract_urls(inp)
    else:
        p = Path(inp)
        if not p.exists():
            print(f"❌ 文件不存在: {p}", file=sys.stderr)
            return 2
        urls = extract_urls(p.read_text(encoding="utf-8"))
    if not urls:
        print("❌ 未找到知乎链接", file=sys.stderr)
        return 2

    print(f"共 {len(urls)} 个知乎链接，开始抓取全文（单个超时 {args.timeout}s）...")
    ok = 0
    for i, url in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] {clean_url(url)}")
        content = fetch_one(cfg, url, args.timeout)
        if not content:
            print(f"  ⚠️ 超时/未抓到（确认 Chrome 扩展在线；该页面可能无正文）")
            continue
        content = content.strip() if args.no_clean else clean_content(content)
        md = render_markdown(url, content)

        if args.out and len(urls) == 1:
            out_path = Path(args.out)
        elif args.out_dir:
            name = re.sub(r"[^\w\u4e00-\u9fff]+", "_", clean_url(url).split("/")[-1] or f"zhihu_{i}")
            out_path = Path(args.out_dir) / f"raw_{i:02d}_知乎全文_{name}.md"
        else:
            name = re.sub(r"[^\w\u4e00-\u9fff]+", "_", clean_url(url).split("/")[-1] or f"zhihu_{i}")
            out_path = Path.cwd() / f"zhihu_full_{i}_{name}.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        print(f"  ✅ 已保存: {out_path}（{len(content)} 字）")
        ok += 1

    print(f"完成：成功 {ok}/{len(urls)}")
    return 0 if ok == len(urls) else 1


if __name__ == "__main__":
    sys.exit(main())
