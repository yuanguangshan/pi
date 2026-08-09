#!/usr/bin/env python3
"""
search_model.py — 用 deepseek-v4-flash 的 Responses API 做服务端联网搜索

模型内置 web_search 工具，由服务端执行搜索并生成答案。两个可用端点：
  A) opencode-go（当前 pi 使用的端点）: https://opencode.ai/zen/go/v1/responses
  B) DeepSeek 官方:                      https://api.deepseek.com/responses

用法:
    python3 search_model.py "搜索：龙华寺 素斋"
    python3 search_model.py "搜索：xz 压缩算法 历史" --out materials/raw_04_xz.md
    python3 search_model.py "搜索：..." --endpoint deepseek   # 用 DEEPSEEK_API_KEY
    python3 search_model.py "搜索：..." --key <sk-xxx>        # 显式给 key

退出码: 0 = 成功, 1 = 失败
"""

import argparse
import json
import os
import sys
import urllib.request

ENDPOINTS = {
    "opencode": "https://opencode.ai/zen/go/v1/responses",
    "deepseek": "https://api.deepseek.com/responses",
}


def read_key() -> str:
    """依次尝试：auth.json(opencode-go) > env DEEPSEEK_API_KEY。"""
    auth = os.path.expanduser("~/.pi/agent/auth.json")
    if os.path.exists(auth):
        try:
            data = json.load(open(auth, encoding="utf-8"))
            if "opencode-go" in data and data["opencode-go"].get("key"):
                return data["opencode-go"]["key"]
        except Exception:
            pass
    if os.environ.get("DEEPSEEK_API_KEY"):
        return os.environ["DEEPSEEK_API_KEY"]
    return ""


def search(query: str, key: str, endpoint: str, max_tokens: int) -> dict:
    body = {
        "model": "deepseek-v4-flash",
        "input": query,
        "tools": [{"type": "web_search_2025_08_26"}],
        "max_output_tokens": max_tokens,
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract(data: dict) -> tuple[list[str], str]:
    """提取搜索查询词 + 最终答案文本（只取 phase=final_answer 的消息，跳过中途 commentary）。"""
    queries, answer = [], ""
    messages = []
    for item in data.get("output", []):
        t = item.get("type")
        if t == "web_search_call":
            for q in item.get("action", {}).get("queries", []):
                queries.append(q)
        elif t == "message":
            messages.append(item)
    # 优先 final_answer，否则取最后一条消息
    final = [m for m in messages if m.get("phase") == "final_answer"]
    if not final:
        final = messages[-1:] if messages else []
    for m in final:
        for c in m.get("content", []):
            if c.get("type") == "output_text":
                answer += c.get("text", "")
    return queries, answer


def main():
    parser = argparse.ArgumentParser(description="deepseek-v4-flash 服务端联网搜索")
    parser.add_argument("query", help="搜索问题")
    parser.add_argument("--out", help="把答案写入文件（推荐存 materials/）")
    parser.add_argument("--endpoint", choices=list(ENDPOINTS), default="opencode",
                        help="端点: opencode(默认, 当前pi的端点) / deepseek(官方)")
    parser.add_argument("--key", help="API key（默认从 auth.json / 环境变量读取）")
    parser.add_argument("--max-tokens", type=int, default=4000)
    args = parser.parse_args()

    key = args.key or read_key()
    if not key:
        print("❌ 未找到 API key（auth.json opencode-go 条目或 DEEPSEEK_API_KEY）")
        return 1

    print(f"查询: {args.query}")
    print(f"端点: {ENDPOINTS[args.endpoint]}")
    try:
        data = search(args.query, key, ENDPOINTS[args.endpoint], args.max_tokens)
    except Exception as e:
        print(f"❌ 搜索失败: {e}")
        return 1

    if data.get("error"):
        print(f"❌ API 错误: {data['error']}")
        return 1

    status = data.get("status")
    if status == "incomplete":
        reason = (data.get("incomplete_details") or {}).get("reason", "")
        print(f"⚠️ 响应被截断(incomplete: {reason})，答案可能不完整")

    queries, answer = extract(data)
    print(f"搜索执行: {'; '.join(queries) if queries else '未触发搜索'}")
    print("=== 搜索结果 ===")
    print(answer if answer else "（无文本输出）")

    if args.out:
        out_path = os.path.abspath(args.out)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        content = f"# 模型联网搜索: {args.query}\n\n> 搜索词: {'; '.join(queries)}\n> 时间: {data.get('created_at', '')}\n\n{answer}\n"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"\n已写入: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
