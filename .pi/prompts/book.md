---
description: 自动写书：一句话定主题或给大纲文件，全自动搜资料、分章撰写、标点体检、整合成书
argument-hint: "<主题一句话 | 大纲文件路径>"
---
# /book 自动写书

输入：$ARGUMENTS

按以下流程执行：

1. 先读取技能文件 `.pi/skills/book-writer/SKILL.md`，后续所有阶段以该技能为准（含标点规则、字数目标、决策日志要求）。
2. 解析输入：
   - 若输入为空 → 询问用户给主题或大纲文件路径。
   - 若输入是一个存在的文件路径（用 `bash test -f "<输入>"` 判断）→ 先 read 该大纲文件，进入"分支 B · 给定大纲"。
   - 否则 → 把输入当主题描述，进入"分支 A · 自决大纲"。
3. 创建项目目录 `book-projects/<书名>/`，按技能七阶段流水线执行：搜资料 → BRIEF.md → OUTLINE.md → 分章撰写（每章 8000-10000 字）→ 标点体检 → 整合 `_COMPLETE_BOOK.md`。
4. 全程在 `_decision_log.md` 记录 AI 决策；每章写完立即跑 `scripts/punctuation_check.py`。
5. 完成后终端汇报：项目目录、章节数、总字数、`_COMPLETE_BOOK.md` 路径。
