#!/usr/bin/env python3
"""
dual_backup.py — ima 知识库 + Knowly 双备份封装

章节或书稿写完后,执行此脚本实现两条独立通道的持久化。

用法:
    # 上传单文件(双备份)
    python3 dual_backup.py --file chapters/ch01_xxx.md \
        --label "第1章/xxx" --book-name "书名"

    # 仅走 ima KB
    python3 dual_backup.py --file chapters/ch01_xxx.md --no-knowly

    # 仅走 Knowly
    python3 dual_backup.py --file chapters/ch01_xxx.md --no-kb

    # 列出一本书的备份状态
    python3 dual_backup.py --list --book-name "书名"

    # 检查某章双备份状态
    python3 dual_backup.py --check --book-name "书名" --chapter 1

退出码:
    0 = 双备份全部成功
    1 = 任一通道失败
    2 = 文件不存在或参数错误
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# 默认配置(可被环境变量覆盖)
DEFAULT_KB_ID = "C9ritGFPsdAXb_hjn92BqKqmYLnMEGU05JKdpxeNE-M="
# yuangs 顶级文件夹(见 references/backup-targets.md);书名子目录需动态建,命令行暂不支持
DEFAULT_FOLDER_ID = "folder_7460859567692871"
IMAKB_SCRIPT = "~/.pi/agent/skills/ima-knowledge/scripts/upload_file.py"
KNOWLY_SCRIPT = "~/.pi/agent/skills/knowly-upload/scripts/upload_to_knowly.py"
# 本地 book-projects 根目录(历史项目位于 ~/ygs/pi/book-projects)
BOOK_PROJECTS_DIR = os.environ.get("BOOK_PROJECTS_DIR", "~/ygs/pi/book-projects")


def backup_to_ima_kb(file: Path, label: str, book_name: str, folder_id: str) -> dict:
    """上传到 ima 知识库 yuangs 文件夹(书名子目录需 MCP create_folder,此处落在 yuangs 顶层)。"""
    script = Path(IMAKB_SCRIPT).expanduser()
    if not script.exists():
        return {"ok": False, "channel": "ima_kb", "error": f"upload_file.py 不存在: {script}"}
    # .py / .sh 改 .txt
    actual_path = file
    if file.suffix in (".py", ".sh"):
        new_path = file.with_suffix(".txt")
        shutil.copy(file, new_path)
        actual_path = new_path
    cmd = [
        sys.executable,
        str(script),
        "--file-path", str(actual_path),
        "--knowledge-base-id", DEFAULT_KB_ID,
        "--folder-id", folder_id,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return {
            "ok": result.returncode == 0,
            "channel": "ima_kb",
            "label": label,
            "returncode": result.returncode,
            "stdout_tail": result.stdout[-500:] if result.stdout else "",
            "stderr_tail": result.stderr[-500:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "channel": "ima_kb", "error": "timeout(120s)"}
    except Exception as e:
        return {"ok": False, "channel": "ima_kb", "error": str(e)}


def backup_to_knowly(file: Path, label: str) -> dict:
    """上传到 Knowly 服务器。"""
    script = Path(KNOWLY_SCRIPT).expanduser()
    if not script.exists():
        return {"ok": False, "channel": "knowly", "error": f"upload_to_knowly.py 不存在: {script}"}
    env = os.environ.copy()
    env["KNOWLY_BASIC_AUTH"] = env.get("KNOWLY_BASIC_AUTH", "knowly:knowly2026")
    try:
        result = subprocess.run(
            [sys.executable, str(script), str(file)],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        return {
            "ok": result.returncode == 0,
            "channel": "knowly",
            "label": label,
            "returncode": result.returncode,
            "stdout_tail": result.stdout[-500:] if result.stdout else "",
            "stderr_tail": result.stderr[-500:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "channel": "knowly", "error": "timeout(120s)"}
    except Exception as e:
        return {"ok": False, "channel": "knowly", "error": str(e)}


def dual_backup(file: Path, label: str, book_name: str, no_kb: bool, no_knowly: bool, folder_id: str) -> int:
    print(f"=== 双备份启动: {label} ===")
    print(f"文件: {file} ({file.stat().st_size if file.exists() else 'MISSING'} bytes)")
    print(f"所属书: {book_name}")
    print()

    if not file.exists():
        print(f"❌ 文件不存在: {file}")
        return 2

    results = []
    if not no_kb:
        print(f"→ 上传到 ima 知识库(folder_id={folder_id})...")
        r = backup_to_ima_kb(file, label, book_name, folder_id)
        results.append(r)
        print(f"   {'✅' if r['ok'] else '❌'} {r['channel']}")
        if r['ok']:
            print(f"   {r['stdout_tail'].strip()[-200:]}")
        else:
            print(f"   stderr: {r.get('stderr_tail', '').strip()[-200:]}")
            print(f"   error:  {r.get('error', '')}")
        print()
    if not no_knowly:
        print("→ 上传到 Knowly 服务器...")
        r = backup_to_knowly(file, label)
        results.append(r)
        print(f"   {'✅' if r['ok'] else '❌'} {r['channel']}")
        if r['ok']:
            print(f"   {r['stdout_tail'].strip()[-200:]}")
        else:
            print(f"   stderr: {r.get('stderr_tail', '').strip()[-200:]}")
            print(f"   error:  {r.get('error', '')}")
        print()

    if not results:
        print("⚠️ 双备份通道都被 --no-* 关闭,无操作")
        return 2

    ok_count = sum(1 for r in results if r["ok"])
    total = len(results)
    print(f"=== 备份结果: {ok_count}/{total} 通道成功 ===")

    # 追加写入备份账本(可被 --check/--invariant-check 消费)
    try:
        book_dir = Path(BOOK_PROJECTS_DIR).expanduser() / book_name
        book_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "file": file.name,
            "label": label,
            "book": book_name,
            "channels": {r["channel"]: bool(r["ok"]) for r in results},
        }
        with open(book_dir / "_backup_log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"⚠️ 账本写入失败(不影响备份结果): {e}")

    return 0 if ok_count == total else 1


def invariant_check(book_dir: Path) -> int:
    """本地可验不变量:INV-1 结构面(命名/编号) + INV-2(整合稿⟹全章节就绪)。

    INV-3/INV-4(线上通道可寻性)由每次备份的 _backup_log.jsonl 回执保证,此处不扫描线上。
    """
    issues = []
    chs = sorted(book_dir.glob("chapters/ch*.md")) + sorted(book_dir.glob("chapters/ch*.txt"))
    print(f"=== 不变量校验: {book_dir.name} ===")
    print(f"  chapters/ 文件数: {len(chs)}")

    # INV-1 结构面:命名符合 chNN_ 约定 + 编号唯一
    nums = []
    for c in chs:
        m = re.match(r"ch0?(\d+)_", c.name)
        if not m:
            issues.append(f"INV-1: 章节文件命名不符合 chNN_ 约定: {c.name}")
        else:
            nums.append(int(m.group(1)))
    dup = sorted({n for n in nums if nums.count(n) > 1})
    if dup:
        issues.append(f"INV-1: 章节编号重复: {dup}")
    if not issues:
        print("  INV-1 ✅ 章节命名规范、编号唯一")

    # INV-2: _COMPLETE_BOOK.md 存在 ⟹ 大纲声明的章节全部就绪
    complete = book_dir / "_COMPLETE_BOOK.md"
    outline = book_dir / "OUTLINE.md"
    if complete.exists():
        outline_n = 0
        if outline.exists():
            text = outline.read_text(encoding="utf-8", errors="ignore")
            outline_n = len(set(re.findall(r"^## 第 (\d+) 章", text, re.M)))
        if outline_n and len(chs) < outline_n:
            issues.append(f"INV-2: 整合稿已存在,但大纲声明 {outline_n} 章、chapters/ 仅 {len(chs)} 个文件")
        elif outline_n:
            print(f"  INV-2 ✅ 整合稿存在,大纲 {outline_n} 章全部就绪")
        else:
            print("  INV-2 ⚠️ 整合稿存在但 OUTLINE.md 缺失/无章节标题,数量对齐无法校验")
    else:
        print("  INV-2 ➖ 无 _COMPLETE_BOOK.md(尚未整合,跳过)")

    if issues:
        for i in issues:
            print(f"  ❌ {i}")
        return 1
    print("=== 本地可验不变量全部通过 ===")
    return 0


def main():
    parser = argparse.ArgumentParser(description="章节/书稿双备份: ima KB + Knowly")
    parser.add_argument("--file", help="待上传的文件路径")
    parser.add_argument("--label", default="chapter", help="备份标签,用于显示")
    parser.add_argument("--book-name", help="所属书名,用于 ima KB 路径")
    parser.add_argument("--folder-id", default=DEFAULT_FOLDER_ID,
                        help="ima KB 目标文件夹 ID(默认 yuangs 顶级文件夹)")
    parser.add_argument("--no-kb", action="store_true", help="仅走 Knowly")
    parser.add_argument("--no-knowly", action="store_true", help="仅走 ima KB")
    parser.add_argument("--list", action="store_true", help="列出某书的本地章节与大小")
    parser.add_argument("--check", action="store_true", help="检查某书(或 --chapter 指定章)的本地文件与账本备份状态")
    parser.add_argument("--chapter", type=int, help="--check 时指定章节号")
    parser.add_argument("--invariant-check", action="store_true",
                        help="校验本地可验不变量:章节命名/编号唯一(INV-1 结构面)、整合稿⟹全章节就绪(INV-2)")
    args = parser.parse_args()

    if args.list or args.check:
        if not args.book_name:
            print("需要 --book-name")
            return 2
        book_dir = Path(BOOK_PROJECTS_DIR).expanduser() / args.book_name
        if not book_dir.exists():
            print(f"❌ 项目目录不存在: {book_dir}(可用 BOOK_PROJECTS_DIR 环境变量指定根目录)")
            return 2
        chs = sorted(book_dir.glob("chapters/ch*.md")) + sorted(book_dir.glob("chapters/ch*.txt"))
        if args.chapter:
            chs = [c for c in chs if re.match(rf"ch0?{args.chapter}_", c.name)]
        print(f"=== 《{args.book_name}》章节{'(仅第%d章)' % args.chapter if args.chapter else ''} ===")
        if not chs:
            print(f"  (chapters/ 下无章节文件: {book_dir / 'chapters'})")
            return 1 if args.check else 0
        # 读取备份账本(按文件名取最近一条)
        ledger: dict = {}
        log_path = book_dir / "_backup_log.jsonl"
        if log_path.exists():
            for line in log_path.read_text(encoding="utf-8").splitlines():
                try:
                    e = json.loads(line)
                    ledger[e.get("file", "")] = e  # 后写覆盖前写 = 最近一条
                except Exception:
                    continue
        for c in chs:
            size = c.stat().st_size
            e = ledger.get(c.name)
            if e:
                ch = e.get("channels", {})
                ima = "✅" if ch.get("ima_kb") else "❌"
                kn = "✅" if ch.get("knowly") else "❌"
                print(f"  {c.name}  ({size}B)")
                print(f"    [ima KB]{ima}  [Knowly]{kn}  — {e.get('ts', '?')}")
            else:
                print(f"  ⚠️ {c.name}  ({size}B) — 账本无记录(未备份或账本缺失)")
        print()
        print("⚠️ 线上实时状态需到 ima KB / Knowly 主动查询(本脚本依据本地账本 _backup_log.jsonl)")
        return 0

    if args.invariant_check:
        if not args.book_name:
            print("需要 --book-name")
            return 2
        book_dir = Path(BOOK_PROJECTS_DIR).expanduser() / args.book_name
        if not book_dir.exists():
            print(f"❌ 项目目录不存在: {book_dir}")
            return 2
        return invariant_check(book_dir)

    if not args.file:
        print("需要 --file")
        return 2

    file_path = Path(args.file)
    book = args.book_name or file_path.parent.parent.parent.name or "未命名书"
    return dual_backup(file_path, args.label, book, args.no_kb, args.no_knowly, args.folder_id)


if __name__ == "__main__":
    sys.exit(main())
