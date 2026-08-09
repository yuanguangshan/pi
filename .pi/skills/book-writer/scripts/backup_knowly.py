#!/usr/bin/env python3
"""
backup_knowly.py — 上传文件到 Knowly NAS（异机备份）

凭证不从代码读取，从以下位置按序获取（都不包含敏感信息）：
  1. 环境变量 KNOWLY_BASIC_AUTH / KNOWLY_UPLOAD_URL
  2. ~/.pi/agent/auth.json 的 "knowly" 条目（{"url": ..., "basic_auth": ...}）

用法:
    python3 backup_knowly.py chapters/ch01_标题.md
    python3 backup_knowly.py _COMPLETE_BOOK.md 序言.md chapters/*.md
    python3 backup_knowly.py _COMPLETE_BOOK.md --book-name 淀山湖

退出码:
    0 = 全部上传成功
    1 = 有失败
    2 = 未配置凭证 / 网络不可达（调用方可视为“跳过备份，不阻塞”）
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_UPLOAD_URL = "https://upload.want.biz/api/upload"


def load_config() -> dict:
    """返回 {url, basic_auth}；未配置则返回空 dict。"""
    cfg = {}
    auth = os.path.expanduser("~/.pi/agent/auth.json")
    if os.path.exists(auth):
        try:
            data = json.load(open(auth, encoding="utf-8"))
            k = data.get("knowly") or {}
            if k.get("url"):
                cfg["url"] = k["url"]
            if k.get("basic_auth"):
                cfg["basic_auth"] = k["basic_auth"]
        except Exception:
            pass
    cfg["url"] = os.environ.get("KNOWLY_UPLOAD_URL", cfg.get("url", DEFAULT_UPLOAD_URL))
    basic = os.environ.get("KNOWLY_BASIC_AUTH", cfg.get("basic_auth", ""))
    cfg["basic_auth"] = basic
    return cfg


def upload(path: Path, cfg: dict) -> dict:
    boundary = "----pi-bookwriter-boundary"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode())
    body.extend(b"Content-Type: text/markdown\r\n\r\n")
    body.extend(path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    auth = "Basic " + base64.b64encode(cfg["basic_auth"].encode()).decode()
    req = urllib.request.Request(
        cfg["url"],
        data=bytes(body),
        headers={
            "Authorization": auth,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return {"ok": True, "data": json.loads(raw)}
            except Exception:
                return {"ok": r.status == 200, "data": {"raw": raw}}
    except urllib.error.HTTPError as e:
        return {"ok": False, "data": {"http": e.code, "body": e.read().decode("utf-8", "replace")[:300]}}
    except Exception as e:
        return {"ok": False, "data": {"error": str(e)}}


def main():
    parser = argparse.ArgumentParser(description="上传文件到 Knowly NAS 备份")
    parser.add_argument("files", nargs="+", help="待上传文件（支持通配符展开）")
    parser.add_argument("--book-name", default="", help="书名（仅用于提示）")
    args = parser.parse_args()

    cfg = load_config()
    if not cfg["basic_auth"]:
        print("⚠️ 未配置 Knowly 凭证（~/.pi/agent/auth.json 的 knowly 条目或环境变量 KNOWLY_BASIC_AUTH），跳过备份")
        return 2

    files = [Path(f) for f in args.files if Path(f).exists()]
    if not files:
        print("⚠️ 没有可上传的文件")
        return 2

    print(f"=== Knowly 备份: {args.book_name or ''} ===")
    ok = 0
    for f in files:
        r = upload(f, cfg)
        if r["ok"]:
            ok += 1
            d = r["data"]
            print(f"✅ {f.name} -> {d.get('path', d.get('saved_as', ''))} ({f.stat().st_size} bytes)")
        else:
            print(f"❌ {f.name} 失败: {r['data']}")
    print(f"=== 结果: {ok}/{len(files)} 成功 ===")
    return 0 if ok == len(files) else 1


if __name__ == "__main__":
    sys.exit(main())
