# 📚 book-writer skill — 知识库备份包（总索引 · v2 全自动版）

> **版本**：v2.0 全自动优先版（2026-08-09 修订）
> **前序版本**：v1.x 半自动版（要求用户在 Phase 1/2 确认）
> **修订原因**：苑老师偏好"全自动"，任何"用户确认"环节都视为打断
> **位置**：ima 知识库 → yuangs / skills / book-writer / (folder_id: `folder_7492093740086370`)
> **沙箱原路径**：`~/.pi/agent/skills/book-writer/`
> **包总大小**：约 50 KB（10 个文件）

---

## 这是什么

**book-writer** 是把"写一本书"工程化、可重复、可追溯的中文长文创作流水线。
**v2 默认全自动**：给完"帮我写本关于 X 的书"后，AI 自决所有方向性决策（BRIEF 覆盖度 / 大纲可证伪性 / 章节标题），只把决策写 `_decision_log.md` 留痕，仅在 5 类硬阻塞时打扰用户。

**七阶段流水线**：

```
搜资料 → BRIEF（AI 自决覆盖度）→ OUTLINE（AI 自决可证伪性）→ 分章撰写（默认并行）
        → 标点体检（AI 自决修补）→ 双备份 → 微信通知
```

---

## v1 → v2 核心变化

| 维度 | v1 半自动 | **v2 全自动** |
|---|---|---|
| Phase 1 BRIEF.md 完成后 | 等用户确认 | **AI 自决覆盖度评估（≥80% 通过）** |
| Phase 2 OUTLINE.md 完成后 | 等用户逐章确认 | **AI 自决可证伪性自检** |
| 章节标题 / 子节 | 用户可调整 | **AI 自决** |
| 标点未过 | file_edit 修补 → 通知用户 | **file_edit 修补 → 3 轮未过才标"⚠️"** |
| 字数 / 子节未达标 | 询问用户 | **AI 自决补写 / 精简** |
| 决策可见性 | 仅终端输出 | **终端 + `_decision_log.md` 永久留痕** |
| 何时打扰用户 | 任何修订 / 不可达 | **仅 5 类硬阻塞** |

> 模式切换由用户主动触发："帮我写书" = 全自动；"帮我写书，每章给我看下" = 半自动。

---

## 包内文件清单（10 个文件）

按 `weread-topic-research` 同款命名规范（平铺在 book-writer 文件夹下，靠前缀区分目录）：

| # | 文件名 | 类型 | 原路径 | 作用 |
|---|--------|------|--------|------|
| 1 | `SKILL.md` | Markdown | `SKILL.md` | **主入口** — 触发条件、全自动七阶段、AI 决策门、5 类硬阻塞 |
| 2 | `references_book-sop.md` | Markdown | `references/book-sop.md` | SOP 详细规范（任务模型、subagent 并行、全自动 vs 半自动对照） |
| 3 | `references_punctuation-rules.md` | Markdown | `references/punctuation-rules.md` | 中文标点六项体检规则（全角 vs ASCII 对照表） |
| 4 | `references_backup-targets.md` | Markdown | `references/backup-targets.md` | 三套备份通道配置（ima KB / Knowly / 微信） |
| 5 | `scripts_chapter_wordcount.py.txt` | TXT | `scripts/chapter_wordcount.py` | 中文字数统计（目标 8000-10000） |
| 6 | `scripts_dual_backup.py.txt` | TXT | `scripts/dual_backup.py` | ima KB + Knowly 双备份封装 |
| 7 | `scripts_integrate_book.py.txt` | TXT | `scripts/integrate_book.py` | 序言+完整书稿整合 |
| 8 | `scripts_notify_wechat.py.txt` | TXT | `scripts/notify_wechat.py` | 微信完成通知封装 |
| 9 | `scripts_punctuation_check.py.txt` | TXT | `scripts/punctuation_check.py` | 中文标点六项体检脚本（核心质量守门员） |
| 10 | `BOOK_WRITER_SKILL_PACKAGE.md` | Markdown | 索引 | 本文件（总入口） |

> **注**：`.py` 文件后缀必须改为 `.py.txt`（ima 知识库不支持 `.py` 后缀直接上传），恢复时改回 `.py` 即可。

---

## 沙箱重置后恢复路径

如果沙箱被重置，`~/.pi/agent/skills/book-writer/` 整个目录丢失，可按以下步骤从知识库恢复：

```bash
# 1. 在 yuangs/skills/book-writer/ 下找到这 10 个文件，用 fetch(media_id) 拉取每个文件原文
# 2. 在沙箱中重建目录结构
mkdir -p ~/.pi/agent/skills/book-writer/{references,scripts}

# 3. 写入文件并恢复命名
# SKILL.md / BOOK_WRITER_SKILL_PACKAGE.md 直接写入
# references_xxx.md  → references/xxx.md（去掉 references_ 前缀）
# scripts_xxx.py.txt → scripts/xxx.py（去掉 scripts_ 前缀，.py.txt 改回 .py）

# 4. 重新注册 skill（必须由 AI 在 shell tool 中执行，subprocess 无法调用）
ima_skill_create -d ~/.pi/agent/skills/book-writer
```

> `ima_skill_create` 是 shell tool 注入的内置命令，**不在 PATH 中**，无法被 Python subprocess / bash 子进程调用，只能在 shell tool 中执行。

---

## 全自动模式关键设计点

1. **AI 决策门替代用户确认门**
   - Phase 1: BRIEF 覆盖度自评（≥80% 通过，50-80% 自动补救，<50% 通知用户）
   - Phase 2: 大纲子论点可证伪性自检（不通过则自动改写，最多 3 轮）
   - Phase 3: 章节标点 + 字数 + 子节覆盖（不达标 AI 自决修补，3 轮未过才标"⚠️"）
2. **全程决策留痕**：所有 AI 自决写 `_decision_log.md`（`book-projects/<书名>/_decision_log.md`），用户事后可翻阅
3. **5 类硬阻塞才打扰用户**：
   - 资料源全部不可达
   - 标点体检 3 轮未过且无自动修复路径
   - 网络彻底断（ima KB + Knowly 双失败）
   - fatal exception（Python 崩溃 / OOM / 配额耗尽）
   - 可证伪性自检 3 轮未过
4. **默认并行**：≥2 章即默认开 subagent 并行（v1 是"可选"）
5. **保留半自动入口**：用户主动说"每章给我看下"才回半自动

---

## 触发场景

**v2 全自动触发**（默认）：
- "帮我写本书，主题是 X"
- "把 Y 的资料整合成一本"
- "写一本关于 X 的书"
- "book chapter: X"

**半自动触发**（用户主动切换）：
- "帮我写本书，每章给我看下"
- "写 X，但每章后等我"
- "全自动写 X，但 X 章后通知我"

**不适用**：
- 单篇文章（用 `article-analysis`）
- 结构化报告（用 `ima-report`）
- 公众号长文 / 千字散文 / 不分章节的小文
- 翻译 / 校对已有书稿

---

## 写书坐标

- **所属知识库**：广山哥（`C9ritGFPsdAXb_hjn92BqKqmYLnMEGU05JKdpxeNE-M=`）
- **子文件夹层级**：yuangs / skills / book-writer
- **兄弟 skills**：weread-deep-read, weread-topic-research, blog_publisher, podcast_publisher, ima-pdf, sendtokindle（书稿完成后的下游可联动技能）

---

雨轩于听雨轩 🌧️🏠
