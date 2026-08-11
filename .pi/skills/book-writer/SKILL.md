---
name: book-writer
description: 自动写书流水线。当用户提到写书、写一本关于某主题的书、给大纲写书、分章撰写、长书创作，或使用 /book 命令时触发。两种入口：一句话定主题（AI 自决大纲）或给大纲文件（严格按用户结构写）。流程：搜资料→BRIEF→OUTLINE→分章撰写（每章 8000-10000 字）→中文标点六项体检→字数达标→整合完整书稿→决策留痕。不适用于单篇文章、报告或短问答。
---

# book-writer — 自动写书流水线（pi 版）

> 由 ima 知识库版 book-writer skill（v3.0）移植到 pi 环境。外部依赖（ima 知识库 / Knowly / 微信推送）在本环境不存在，已改为本地落盘 + 可选 git 备份；流水线其余部分与原始版一致。

## 一、入口分流

`/book <输入>` 先识别输入类型再分流：

| 输入 | 分支 | 做法 |
|---|---|---|
| 一句话主题（如"写一本关于 Unix 压缩算法的书"） | 分支 A · 自决大纲 | AI 自定书名、章节、字数分配，不询问用户 |
| 大纲文件路径（如 `outline.md`、`docs/大纲.md`） | 分支 B · 给定大纲 | 先 read 大纲，严格保留章节结构与顺序，不重写；每章仍现搜资料保深度 |

识别方法：输入以 `/`、`./`、`~/` 开头，或 `bash test -f "<输入>"` 通过 → 大纲文件；否则当主题。

## 二、项目目录

全部产物落在当前工作目录下：

```
book-projects/<书名>/
├── BRIEF.md           # 共享资料包（全自动构建）
├── OUTLINE.md         # 章节大纲（分支 A 自决 / 分支 B 来自用户文件）
├── _decision_log.md   # 全程 AI 决策留痕
├── materials/         # 原始资料（raw_01_*.md ...）
├── chapters/          # ch01_标题.md, ch02_标题.md ...
├── 序言.md            # 阶段 6 生成
└── _COMPLETE_BOOK.md  # 阶段 6 生成
```

## 三、七阶段流水线

| 阶段 | 动作 | 产出物 | 决策门 |
|---|---|---|---|
| 1 资料搜集 | 联网检索（curl）+ 模型知识，落盘 materials/ | materials/*.md | 覆盖度自评 ≥ 80% |
| 2 大纲规划 | 分支 A 自决 / 分支 B 读用户文件 | OUTLINE.md | 子论点可证伪性自检通过 |
| 3 分章撰写 | 每章 8000-10000 字（区间惩罚制，理想 9000），边写边自查 | chapters/chXX_标题.md | 标点六项全过 + 字数达标 |
| 4 标点体检 | 跑 scripts/punctuation_check.py 修到全过 | — | 六项全部通过 |
| 5 落盘持久化 | 本地落盘即保存；可选 git 备份 | 文件落盘 | 无 |
| 6 序言 + 整合 | 写序言，跑 scripts/integrate_book.py 合并 | 序言.md + _COMPLETE_BOOK.md | 总标点体检通过 |
| 7 汇报 | 终端汇总产物、章节数、总字数 | 汇总信息 | — |

执行原则：

- 阶段不跳级；决策门未过自动回退补做，不询问用户。
- 所有 AI 决策写入 `_decision_log.md`。
- 默认不打扰用户；仅硬阻塞（资料源全不可达、标点 3 轮无法修复、fatal 异常）才停下询问。
- **时间预期**：半小时成书是热主题 + 模型极速输出的理想值；冷门主题资料搜集可能触发多轮补搜，单本耗时远超此值，属正常，不以速度为达标标准。

## 四、Phase 1 资料搜集 → BRIEF.md

### 4.1 多路并行检索

本环境无内置 search 工具，用 bash + curl 联网检索。以下通道均为本机实测可用（无 key 限制）；Bing/Baidu/Google Books/SearXNG 公共实例实测被挡或配额耗尽，不可用。

**知乎搜索（高质量社区内容，第一优先）**：知乎社区内容质量高——真实经验、具体案例、多元观点，最适合作为书籍资料基底。通道自动探测（Mac/Linux 通吃）：优先 zhihu-cli（macOS Keychain）；CLI 不可用（如 Linux 无官方二进制）自动降级 HTTP API 直连（凭证：env `ZHIHU_ACCESS_SECRET` / `~/.pi/agent/auth.json` 的 zhihu.access_secret / Keychain）：

```bash
# 知乎站内搜索（优先通道；--out 落盘 materials/ 供后续引用）
python3 .pi/skills/book-writer/scripts/search_zhihu.py "<搜索问题>" --count 10 --out materials/raw_xx_zhihu.md
# 每个子主题至少一轮知乎搜索；知乎结果与通用搜索交叉印证，社区观点与官方资料并陈
# 知乎通道失败（未配置凭证/网络）时：终端会输出 ⚠️ 降级警告，必须把"知乎通道降级"记入 _decision_log.md，不得静默跳过
```

```bash
# ── 通用网页搜索 ──────────────────────────────
# 1) DuckDuckGo HTML（主通道，无需 API key；<URL编码主题> 用 python3 编码）
curl -sL -m 10 -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36" \
  "https://html.duckduckgo.com/html/?q=<URL编码主题>"
# 2) DuckDuckGo Lite（备选，更轻量）
curl -sL -m 10 -A "Mozilla/5.0" "https://lite.duckduckgo.com/lite/?q=<URL编码主题>"
# 3) DDG Instant Answer API（返回 JSON，适合百科类即时回答，但常见查询为空）
curl -sL -m 8 "https://api.duckduckgo.com/?q=<URL编码主题>&format=json"

# ── 模型内置联网搜索（服务端执行，最省事，推荐） ───────
# 用 deepseek-v4-flash 的 Responses API，web_search 工具由服务端执行，
# 返回基于真实搜索结果生成的答案。当前可用的两个端点（均已实测）：
#   A) opencode-go 当前端点（key 自动探测：env OPENCODE_GO_API_KEY / ~/.hermes/.env / DEEPSEEK_API_KEY / ~/.pi/agent/auth.json）
#      https://opencode.ai/zen/go/v1/responses
#   B) DeepSeek 官方（env DEEPSEEK_API_KEY）
#      https://api.deepseek.com/responses
# 请求模板（key 换成对应端点的；可用 python3 脚本调用并把结果存 materials/）：
curl -sL -m 120 "https://opencode.ai/zen/go/v1/responses" \
  -H "Authorization: Bearer <opencode-go-key>" -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v4-flash","input":"搜索：<中文问题>，请给出要点和来源","tools":[{"type":"web_search_2025_08_26"}],"max_output_tokens":2000}'
# 响应中 type=web_search_call 的 item 即服务端搜索执行记录；
# 最终 message 的 output_text 是搜索加持后的答案。

# ── 权威百科（拉全文，最可靠） ──────────────────
# 4) Wikipedia API（返回 JSON，可拉纯文本全文）
curl -sL -m 15 "https://zh.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&format=json&titles=<URL编码词条>"
# 5) Wikipedia REST 摘要（更轻量）
curl -sL -m 8 "https://zh.wikipedia.org/api/rest_v1/page/summary/<URL编码词条>"
# 6) Wikipedia 搜索（不确定词条名时先用它找标题）
curl -sL -m 10 "https://zh.wikipedia.org/w/api.php?action=query&list=search&srsearch=<URL编码主题>&format=json&srlimit=10"

# ── 技术主题（代码/讨论/问答） ──────────────────
# 7) GitHub Search API（10 次/分，无需 key）
curl -sL -m 10 -H "Accept: application/vnd.github+json" \
  "https://api.github.com/search/repositories?q=<URL编码主题>&per_page=5"
# 8) Hacker News Algolia（技术社区讨论）
curl -sL -m 10 "https://hn.algolia.com/api/v1/search?query=<URL编码主题>&hitsPerPage=5"
# 9) Stack Exchange API（Stack Overflow 等技术问答）
curl -sL -m 10 "https://api.stackexchange.com/2.3/search/advanced?site=stackoverflow&q=<URL编码主题>&pagesize=5"

# ── 学术论文 ──────────────────────────────────
# 10) Crossref API（论文元数据，无 key）
curl -sL -m 10 "https://api.crossref.org/works?query=<URL编码主题>&rows=5"
```

URL 编码可用：`python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "主题词"`。
DDG 结果页里 `class="result__a" href="//duckduckgo.com/l/?uddg=<URL编码目标>"` 即为真实链接，解析后用已知 URL 直接抓正文。

**人物与故事专项检索（每本书必做，题材不限）**：无论主题是人、事、物还是抽象概念，额外检索一路"人物/口述/访谈/故事/细节"素材，落盘 `materials/raw_xx_人物故事.md`：

```bash
python3 .pi/skills/book-writer/scripts/search_model.py "搜索：<主题> 人物 口述 访谈 故事 细节 从业者" --out materials/raw_xx_人物故事.md
# 知乎同样优先：社区里的从业者自述、亲历者经历、具体案例，是人物故事素材的富矿
python3 .pi/skills/book-writer/scripts/search_zhihu.py "<主题> 从业者 经历 案例" --count 10 --out materials/raw_xx_人物故事.md
# 纯技术/纯理论主题改为检索从业者/历史人物/具体案例
```

规则：真实人物（姓名、职业、细节）只能来自素材并标注来源；素材中没有的人物信息，不得作为事实虚构写入。

网络不可用时，直接用模型知识撰写资料，并在 `_decision_log.md` 标注"资料来自模型知识，未经联网核实"。

对每个命中，把提炼后的素材段落盘：

```
materials/raw_01_<主题A>.md
materials/raw_02_<主题B>.md
```

### 4.2 共享资料包 BRIEF.md

为每个项目写 BRIEF.md（各章风格统一的"宪法"），必含：

```markdown
# [书名] 共享资料包 BRIEF

## 核心定位
- 主题:
- 目标读者:
- 核心论点 / 一句话价值主张:

## 风格基线
- 人称: 第几人称?
- 语气: 理性克制 / 激情 / 散文?
- 标点规则: 中文全角（必读 references/punctuation-rules.md）
- 章节结构: 每章[小节数]小节,每小节[字数]字,共[章数]章
- 每章目标字数: 8000-10000（含全角标点；汉字感知量约 7200-9000）

## 概念词典
- 术语1: 定义
- 术语2: 定义

## 关键事实清单（必引）
- 事实1: [来源]
- 事实2: [来源]

## 深度挖掘候选（至少 3 个）

> 以下为素材中出现的"人物/地点/物 + 主题交叉点"，须在写作中触发二级搜索展开（见 4.4），不可仅作背景资料罗列。

1. [人物/地点/物] + [与该书主题的交叉点] — 预期挖掘方向：[该交叉点指向的核心问题]
2. [人物/地点/物] + [与该书主题的交叉点] — 预期挖掘方向：[该交叉点指向的核心问题]
3. [人物/地点/物] + [与该书主题的交叉点] — 预期挖掘方向：[该交叉点指向的核心问题]

## 资料索引
- 素材1: materials/raw_01_主题A.md
```

### 4.3 AI 决策门：覆盖度自评

覆盖度 = 已覆盖核心论点维度数 / BRIEF 声明维度数：

| 覆盖度 | 决策 | 动作 |
|---|---|---|
| ≥ 80% | 通过 | 写日志，进 Phase 2 |
| 50%-80% | 自动补救 | 第二轮定向检索缺失维度（最多 2 轮） |
| < 50% | 硬阻塞 | 写日志，询问用户 |

### 4.4 深度挖掘触发器（通用版）

> 与题材解绑，适用任何长书写作项目（历史/传记、科技史、城市文化、艺术文学、商业产业等）。规则关注"叙事深度"，不挑主题。

**触发条件**（BRIEF 深度挖掘候选或写作中遇到的素材，出现以下任一模式即触发）：

- **A. 关键人物 + 具体地点/机构 + 明确时间节点**：同一句话或同一段落中同时出现可辨识的关键人物（政商学艺界）、具体地点/机构名称、明确年份或时期。例："张謇、南通、1899年大生纱厂创办"、"陈寅恪、清华国学院、1925年"、"杜尚、纽约现代艺术博物馆、1913年军械库展览"。
- **B. 多重标签人物**：人物在公开资料中具有 ≥2 种显著身份，且其中至少一种与该书主题直接相关。例："张謇：状元 + 实业家 + 教育家"、"图灵：数学家 + 密码学家 + 人工智能先驱"、"林徽因：建筑师 + 诗人 + 古建筑保护者"。
- **C. 主题物/场所与当代意义的断裂**：素材中提到某物、某地或某机构的历史原功能（或原含义）与其当代面貌或认知形成反差，且该反差对理解主题有价值。例："填埋场 → 今天的城市公园"、"算盘 → 量子计算"、"巴黎下水道 → 旅游景点"。

**二级搜索强制动作**（触发后必须立即执行——调用 search_model.py 或 search_zhihu.py，至少完成 2 轮）：

```bash
# 第 1 轮：挖掘该人物/地点/物与该书主题的功能性关联（"它为什么重要"）
python3 .pi/skills/book-writer/scripts/search_model.py \
  "搜索：[人物名/地点/物] [主题关键词] [贡献/影响/行业关联]" \
  --out materials/raw_xx_深度挖掘_关联.md

# 第 2 轮：追问该人物/地点/物对主题核心命题的具体支撑（"它能回答什么问题"）
python3 .pi/skills/book-writer/scripts/search_model.py \
  "搜索：[人物名/地点/物] [主题核心命题关键词] 案例 细节" \
  --out materials/raw_xx_深度挖掘_细节.md
```

**撰写约束**（硬性要求，二级搜索返回后对最终书稿中该段落的处理）：

- 触发点不能仅以"一笔带过"的身份出现，必须呈现其在主题叙事中的具体作用——它回答了什么问题、提供了什么视角、揭示了什么结构。
- 段落字数不少于 150 字（不含直接引语），确保从"提及"升级为"展开"。
- 必须包含至少一个直接引语或具体可验证的细节（数字、日期、当事人原话、当时媒体报道）。若二级搜索未找到，应在文末标注"未检索到直接引语，细节据公开事实重构"。

**例外豁免**：若二级搜索确认该触发点在该书主题下无深层叙事价值，则允许降级为"背景信息"一句话处理，并在 `_decision_log.md` 中注明豁免理由。

## 五、Phase 2 大纲规划 → OUTLINE.md

### 分支 A（一句话主题）：AI 自决大纲

按模板写 OUTLINE.md：

```markdown
# 《[书名]》大纲

总章数: [N]
预计总字数: [N × 9000]

## 第 1 章 [标题]
- 核心论点: ...
- 子节:
  - 1.1 [子节标题] — [字数] 字
  - ...
- 引用素材: materials/raw_xx.md

## 第 2 章 ...
```

### 分支 B（大纲文件）：尊重用户结构

1. read 用户大纲文件。
2. 复制为 `OUTLINE.md`，**严格保留章节、标题、顺序**；只做必要规范化（如补编号），不重写、不增删章节。
3. 若用户大纲缺字数分配，AI 补上每章目标字数。

### AI 决策门：子论点可证伪性自检

对每章核心论点自检：是事实判断/可观察现象 → 通过；玄学/纯情绪 → 改写为可证伪陈述（最多 3 轮）。结果写 `_decision_log.md`。

## 六、Phase 3 分章撰写

### 6.1 单章六步

```
1. 读 BRIEF.md + OUTLINE.md 该章定位
2. 现搜该章子主题资料（curl 一轮，命中落盘 materials/chXX_*.md）
2.5 深度挖掘触发器（强制）：当素材命中以下任一信号时，必须立即调用 search_model.py 或 search_zhihu.py 执行二级定向搜索，不得跳过直接进入撰写；BRIEF"深度挖掘候选"列出的交叉点同样视为命中。搜索命令与撰写约束见 4.4。

    | 信号类型 | 判定规则 | 示例（跨题材） |
    |---|---|---|
    | A. 关键人物 + 具体地点/机构 + 明确时间节点 | 同一句话或同一段落中同时出现可辨识的关键人物（政商学艺界）、具体地点/机构名称、明确年份或时期 | "张謇、南通、1899年大生纱厂创办" / "陈寅恪、清华国学院、1925年" / "杜尚、纽约现代艺术博物馆、1913年军械库展览" |
    | B. 多重标签人物 | 人物在公开资料中具有 ≥2 种显著身份，且其中至少一种与该书主题直接相关 | "张謇：状元 + 实业家 + 教育家" / "图灵：数学家 + 密码学家 + 人工智能先驱" / "林徽因：建筑师 + 诗人 + 古建筑保护者" |
    | C. 主题物/场所与当代意义的断裂 | 素材中提到某物、某地或某机构的历史原功能（或原含义）与其当代面貌或认知形成反差，且该反差对理解主题有价值 | "填埋场 → 今天的城市公园" / "算盘 → 量子计算" / "巴黎下水道 → 旅游景点" |
3. 读该章相关素材 + 全局素材
4. 撰写（目标 8000-10000 字，区间惩罚制理想值 9000；严格用 BRIEF 的风格/术语/标点）。**每章必须包含至少一个"人文锚点"**（题材无关的通用要求）：
   - 具体的人（有名有姓或可辨识的具体个体）优先；无人可写时退而求具体物件、具体场景或具体案例
   - 细节三要素：至少一个可触摸的物件、一个具体的动作、一段直接引语
   - 真实性纪律：真实人物信息必须来自 materials/ 素材并标注来源；素材不足时允许文学化重构，但须在章节内或文末声明"文学化处理，细节为艺术重构"
5. 立即跑: python3 .pi/skills/book-writer/scripts/punctuation_check.py chapters/chXX_标题.md
6. 修补到六项全过 → 进 Phase 4/5
```

每章现搜资料是硬性步骤，防止"内容单薄、全靠 BRIEF 推论"。

### 6.2 章节质量门（全自动）

| 检查项 | 通过条件 | 失败动作 |
|---|---|---|
| 标点六项 | 全过 | 修补，3 轮未过标"⚠️"接受 |
| 字数 | 8000-10000（**含全角标点**；汉字数约 7200-9000 为正常感知量） | 区间惩罚制（见 chapter_wordcount.py）：不足/超出 → 补写/精简；贴边（贴近 8000/10000 边界，惩罚 ≥40）→ 充实至 8500+ 或精简至 9500- 后定稿 |
| 子节覆盖 | 与 OUTLINE.md 对齐 | 补齐 |
| 人文锚点 | 每章 ≥1 个具体的人/物件/场景/案例 + 真实性标注 | 缺失则补写；素材不足按"文学化处理"声明规则接受 |
| 深度挖掘触发点 | 触发点须展开：段落 ≥150 字（不含直接引语）+ 含直接引语或可验证细节 | 未展开则补跑 4.4 二级搜索；豁免须在 _decision_log.md 注明理由 |

## 七、Phase 4 标点体检

每章写完必跑：

```bash
python3 .pi/skills/book-writer/scripts/punctuation_check.py chapters/chXX_标题.md
```

六项规则详见 `references/punctuation-rules.md`。AI 自动修补到全过。

## 八、Phase 5 落盘持久化

- 写完一章即落盘 `chapters/`（本地即持久化，任何时刻进度已保存）。
- 章节定稿后不再原地修改；重写走 `chXX_标题_v2.md`。
- 可选 git 备份：仅当用户明确要求时，只 `git add book-projects/<书名>/` 并 commit（遵循仓库提交规则）。
- 可选 Knowly 异机备份（**自动探测，通才执行，不通不阻塞**）：

```bash
python3 ~/.pi/agent/scripts/knowly_upload.py \
  chapters/ch01_标题.md chapters/ch02_标题.md ...
python3 ~/.pi/agent/scripts/knowly_upload.py _COMPLETE_BOOK.md 序言.md
```

  凭证从 `~/.pi/agent/auth.json` 的 `knowly` 条目（`{"url":..., "basic_auth":...}`）或环境变量 `KNOWLY_BASIC_AUTH` / `KNOWLY_UPLOAD_URL` 读取，不入库。未配置或上传失败只记录、不打断写作。

## 九、Phase 6 序言 + 整合

1. 写 `序言.md`（2000-4000 字：为谁写、核心问题、结构导览、与同类书差异、致谢），走相同标点体检。
2. 整合：

```bash
python3 .pi/skills/book-writer/scripts/integrate_book.py \
  --book-dir book-projects/<书名> \
  --preface 序言.md \
  --outline OUTLINE.md \
  --output _COMPLETE_BOOK.md
```

3. 对 `_COMPLETE_BOOK.md` 再跑一次总标点体检。

## 十、Phase 7 汇报

终端汇报：产物路径、章节数、总字数（`chapter_wordcount.py chapters/`）。

可选微信通知（**自动探测，通才执行，不通不阻塞**）：

```bash
# 总字数统计（汉字数，不含标点；“grep 中文字符”匹配双口径输出中的汉字行）
TOTAL=$(python3 .pi/skills/book-writer/scripts/chapter_wordcount.py chapters/ | grep 中文字符 | sed 's/[^0-9]//g' | awk '{s+=$1} END {print s}')
python3 .pi/skills/book-writer/scripts/notify_wechat.py \
  --book-name <书名> --chapters 4 --total-words "$TOTAL" \
  --complete-book-path book-projects/<书名>/_COMPLETE_BOOK.md
```

  凭证从 `~/.pi/agent/auth.json` 的 `wechat-push` 条目（`{"url":..., "token":...}`）或环境变量 `WECHAT_PUSH_URL` / `WECHAT_PUSH_TOKEN` 读取，不入库。未配置或通知失败不阻塞。

## 十一、异常分支（何时打扰用户）

默认不打扰。以下硬阻塞才停下询问：

1. 资料源全部不可达（curl 全失败且模型知识不足）
2. 标点体检 3 轮未过且无自动修复路径
3. fatal exception（脚本崩溃 / 输出异常）
4. 可证伪性自检 3 轮未过

## 十二、写作硬性规则

1. 中文用全角标点：`“”`、`。`、`、`、`《》`、`（）`、`——`
2. 代码块内豁免英文标点
3. 句末用 `。？！……`，不用英文 `.`
4. 不混排（一句话内不混用中英文标点）
5. 人文锚点与真实性纪律（题材无关）：每章至少一个具体的人/物件/场景/案例锚点；真实信息标注来源；素材不足的文学化重构必须显式声明，禁止把虚构人物当事实呈现
6. 深度挖掘触发点（见 4.4）：触发点不得一笔带过，须展开其在主题叙事中的作用（≥150 字，不含直接引语；含直接引语或可验证细节）；二级搜索确认无深层价值可豁免为背景一句话，但须在 `_decision_log.md` 注明理由

## 不适用边界

- 单篇文章 / 报告 / 短问答（直接答即可）
- 翻译、校对已有书稿

## 目录结构

```
book-writer/
├── SKILL.md
├── references/
│   ├── punctuation-rules.md   # 中文标点六项规则
│   └── book-sop.md            # 分章撰写 SOP / 并行策略 / 决策日志格式
└── scripts/
    ├── punctuation_check.py   # 标点六项体检（纯 stdlib）
    ├── chapter_wordcount.py   # 中文字数统计
    ├── integrate_book.py      # 序言 + 章节整合为完整书稿
    ├── search_model.py        # 模型内置联网搜索（deepseek-v4-flash Responses API）
    ├── knowly_upload.py      # Knowly NAS 异机备份（独立工具，见 ~/.pi/agent/scripts/）
    └── notify_wechat.py       # 微信完成通知（可选，通才执行）
```

## 启动一句话

"帮我写本书，主题是 X" 或 `/book X` 或 `/book path/to/outline.md` → 全自动执行以上流水线。
