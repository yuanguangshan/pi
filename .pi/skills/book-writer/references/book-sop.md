写书工程化 SOP 详细规范

本文件是 SKILL.md 主干之外的详细补充,被以下场景加载:
- subagent 并行撰写多章节时
- 处理章节定稿 / 修订 / 重写时
- 全书整合时序言 / 章节顺序 / 章节标题调整时

> **v2 全自动模式提醒 (2026-08-09 修订)**: 所有"让用户确认"环节在全自动模式下都改为 AI 自决,只在决策日志中留痕。详见 `SKILL.md` Phase 1/2/3 的"AI 决策门"小节。

## 1. 任务模型

### 1.1 单章节任务输入(给 subagent 的 brief)

```yaml
task: 撰写《<书名>》第 N 章 "<章节标题>"
context:
  - 必读: book-projects/<书名>/BRIEF.md
  - 必读: book-projects/<书名>/OUTLINE.md(查第 N 章定位)
  - 必读: book-projects/<书名>/materials/下相关素材文件
deliverable:
  - 文件: book-projects/<书名>/chapters/chNN_<章节标题>.md
  - 字数: 8000-10000 中文字符(不含英文/数字)
  - 结构: 严格遵循 OUTLINE.md 中第 N 章的子节列表
constraints:
  - 标点: 全角中文(全读 references/punctuation-rules.md)
  - 术语: 严格使用 BRIEF.md 中"概念词典"的规定
  - 引文: 引用素材段必须标注来源文件名 + 行号
  - **全自动模式**: 不向主控询问风格/方向,自行决策;主控只关心"产出文件存在 + 标点 + 字数"
check_after_write:
  - python3 scripts/punctuation_check.py <输出文件>
  - python3 scripts/chapter_wordcount.py <输出文件>
```

### 1.2 主控在子代理收齐后必须做的(全自动模式)

1. 跑一次 `punctuation_check.py` 对所有章节一起做
2. 跑一次 `chapter_wordcount.py --all` 确认每章达标
3. 列出每章的子节标题,与 `OUTLINE.md` 比对:是否所有子节都覆盖
4. **不询问用户是否调整**;若有未达标章节,自动 file_edit 补做(最多 2 轮)
5. 所有检查结果写 `_decision_log.md` 留痕

### 1.3 决策日志约定 (`_decision_log.md`)

每个 AI 自决都要写日志,标准格式:

```markdown
## [<时间戳>] <阶段> - <决策类型>

- 输入: <做了什么 / 评估什么>
- 决策规则: <引用 SKILL.md 哪个决策门>
- 结果: <通过 / 未通过 / 自动修补 / 例外>
- 动作: <下一步>

---
```

例如:

```markdown
## [2026-08-09 14:23:00] Phase 2 - 大纲可证伪性决策

- 输入: 9 章大纲,核心论点逐一自检
- 决策规则: SKILL.md §2.1(可证伪性自检)
- 结果: 7/9 直接通过,2/9 不可证伪已自动改写
- 动作: 进入 Phase 3

---
```

## 2. 修订流程

### 2.1 修订 vs 重写

| 场景 | 动作 | 命名 |
|---|---|---|
| 局部段落修改 | file_edit | 保留 `chNN.md` |
| 全文重写 | 新文件 | `chNN_v2.md`,旧文件保留作 archive |
| 子节顺序调整 | file_edit | 保留 `chNN.md` |
| 章节标题修改 | file_edit + OUTLINE.md 同步更新 | 保留 `chNN.md`,但需更新 OUTLINE.md |

**绝对禁止**: 备份成功的 `chNN.md` 文件被原地覆写为不兼容的版本。如果必须重写,走 `_v2` 路线。

### 2.2 修订后重新双备份

任何 file_edit 后都需要重跑双备份,因为旧版本在 ima KB / Knowly 上的副本会被覆盖:
- ima KB: `dual_backup.py` 上传同名文件会覆盖
- Knowly: `upload_to_knowly.py` 同名文件会生成新版本(NAS 保留历史)

### 2.3 全自动模式下的修订决策(替代原"询问用户方向")

**v2 默认**: 修订方向由 AI 自决,基于以下启发式:

| 触发场景 | AI 决策 |
|---|---|
| 章节字数 < 6000 | 自动补写(扩到 8000-10000) |
| 章节字数 > 12000 | 自动精简(砍冗余段落,优先保留 BRIEF 关键事实) |
| 标点六项未过 | 自动 file_edit 修补(用 `references/punctuation-rules.md` 修复策略) |
| 子节缺失 | 自动补齐缺失子节 |
| 章节顺序错乱 | 自动按 OUTLINE.md 顺序重排 |
| 概念术语与 BRIEF 不一致 | 自动按 BRIEF 概念词典统一 |

仅当上述 6 类全部跑完仍不达标,或遇到硬阻塞(资料缺失 / 网络断),才通知用户。

## 3. 全书整合顺序规则

整合 `_COMPLETE_BOOK.md` 时,顺序必须严格:

1. 书名标题块
2. 作者 + 完成时间
3. 序言全文
4. 目录(从 OUTLINE.md 自动生成,用 1.1 / 1.2 / ... 编号,跳过序言用"序言"无编号)
5. 第 1 章 → 第 N 章(按 OUTLINE.md 中的顺序,**严格保留原作者的章序**)
6. (可选)后记 / 致谢 / 参考资料

整合时**不做任何章节内容的修改**,即使发现瑕疵也仅在交付后单独提修订建议。

## 4. 大规模并行策略(>5 章)

### 4.1 subagent fan-out 拓扑

```
主控
  ├── Phase 1 并行检索(search web/kb/note)
  ├── AI 自决写 BRIEF.md + 自评覆盖度
  ├── AI 自决写 OUTLINE.md + 可证伪性自检
  ├── Phase 2 fan-out (并行 subagent × N 章) [全自动模式默认开启]
  │    ├── subagent_01 → ch01.md
  │    ├── subagent_02 → ch02.md
  │    └── ...
  ├── Phase 3 收齐后总标点体检(AI 自决)
  ├── Phase 4 逐章 dual_backup.py(全自动)
  ├── Phase 5 AI 自决写序言
  ├── Phase 6 integrate_book.py + 总标点体检(AI 自决)
  └── Phase 7 微信通知
```

> v1 旧版在 Phase 1/2 之后会"等用户确认",v2 全自动模式直接跳过用户确认,改为 AI 自决 + 决策日志。

### 4.2 subagent 并发数控制

- 总章节 ≤ 5 章: 全部并行
- 5 < 总章节 ≤ 10 章: 拆 2 批
- > 10 章: 拆 3 批,每批后主控做一次 mid-check

### 4.3 subagent 失败兜底(全自动模式)

- subagent 返回文件未通过标点体检 → 主控**不通知用户**,自己 file_edit 修补;3 轮未过则标"⚠️ 标点瑕疵"接受
- subagent 字数 < 6000 → 主控**不通知用户**,要求 subagent 补写到目标下限(再 spawn 一次只补)
- subagent 子节覆盖不全 → 主控**不通知用户**,要求补完缺失子节

### 4.4 全自动并行 vs 半自动并行(对照)

| 维度 | v1 半自动 | v2 全自动 |
|---|---|---|
| BRIEF.md 完成后 | 等用户确认 | AI 自决覆盖度评估 |
| OUTLINE.md 完成后 | 等用户逐章确认 | AI 自决可证伪性自检 |
| 章节标题 / 子节 | 用户可调整 | AI 自决 |
| 标点未过 | file_edit 修补 → 通知用户 | file_edit 修补 → 3 轮未过才标"⚠️" |
| 决策可见性 | 仅终端输出 | 终端 + `_decision_log.md` 永久留痕 |
| 何时打扰用户 | 任何修订 / 不可达 | 仅 5 类硬阻塞 |

## 5. 与其他技能的协同

| 场景 | 推荐技能 | 备注 |
|---|---|---|
| 公众号同步发布某章 | `blog_publisher` | 单章发布需先到整合稿所在文件夹 |
| 章节音频化 | `ima-podcast` | 单章成稿后转音频 |
| PDF 导出书稿 | `ima-pdf` | _COMPLETE_BOOK.md → PDF |
| 推 Kindle | `sendtokindle` | EPUB / DOCX 转换 |

## 6. 全自动模式的"何时回退到半自动"开关

虽然 v2 默认全自动,但仍保留半自动入口(供用户主动选择):

| 触发语 | 模式 |
|---|---|
| "帮我写本书,主题是 X" | 全自动(默认) |
| "帮我写本书,每章给我看下" | 半自动(Phase 1/2 确认) |
| "写 X,但每章后等我" | 半自动(每章确认) |
| "全自动写 X,但 X 章后通知我" | 混合(每 N 章通知一次) |

> AI 接到用户指令时,先识别关键词匹配模式;无明确指示时默认全自动。
