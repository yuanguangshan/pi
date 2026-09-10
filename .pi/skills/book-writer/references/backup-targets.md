备份目标与渠道配置

写书流程涉及三套持久化通道。每条通道的目标地址 / 凭证 / 限制记录如下:

## 1. ima 知识库(首选,Book project 持久化)

- 知识库 ID(kb_id): `C9ritGFPsdAXb_hjn92BqKqmYLnMEGU05JKdpxeNE-M=`
- 顶级文件夹: yuangs(`folder_7460859567692871`)
- 写书项目子目录: `yuangs/books/<书名>/`(folder_id 由知识库动态创建)
- 上传脚本: `python3 ~/workspace/skills/ima-knowledge/scripts/upload_file.py`
- 参数格式: `--file-path <path> --knowledge-base-id <kb_id> [--folder-id <folder_id>]`
- 文件后缀: `.py` / `.sh` 需先重命名为 `.txt`(知识库不支持)
- 限制: 单次上传 200MB,大量小文件 OK

### 为什么先 ima KB?
- ima KB 支持全文搜索,后续可用 `search(kb_id, "X")` 检索书稿内容
- 支持版本管理(同名上传会更新)
- 与笔记 / 微信公众号生态打通,长期管理友好

## 2. Knowly 服务器(必选,异机备份)

- 上传端点: `POST https://upload.want.biz/api/upload`
- 认证: HTTP Basic Auth `knowly:knowly2026`(环境变量 `KNOWLY_BASIC_AUTH`)
- 上传脚本: `KNOWLY_BASIC_AUTH=knowly:knowly2026 python3 ~/workspace/skills/上传到knowly/scripts/upload_to_knowly.py <file>`
- 上传 .md / .txt 后会自动触发: AI 处理 → 归档 → 索引 → 发布
- 限制: 单次 200MB,**必须为 -F 指定 MIME type**(Cloudflare 对未知二进制类型会 524)
- 历史保留: 同名文件 NAS 会保留历史,新上传走新路径

### 为什么必须 Knowly?
- 异机(独立 NAS),即使 ima.copilot 平台宕机也能取回书稿
- 支持公开分享 / 跨人协作
- 自动索引,可在 knowly 站内搜索

## 3. 微信通知(完成推送)

- 默认接收人: 广山哥(`--to` 参数可指定他人)
- 渠道: `wechat-send/scripts/send_to_wechat.py`,封装 `send_to_wechat.py`
- 调用规范(脚本会封装):
  - 内容写入 `/tmp/wechat_send_content.md`
  - 执行脚本即可发送
  - 防拦截必须带完整浏览器请求头(由脚本内部处理)
- 高频端点备选: `POST https://api.yuangs.cc/weixinpush`
  - 认证: `Authorization: Bearer 2d63e8c2552651b89181932688a4705c`
  - Body: `{"msgtype":"text","content":"..."}`
- 限制: 单条 4000 字符,超长会自动分段

### 什么时候必须通知?
- 单章写完并双备份后: **不需要**(频率太高,刷屏)
- 全书完成(Phase 7): **必须**

## 4. 三套通道的优先级与降级

| 通道 | 优先级 | 失败降级 |
|---|---|---|
| ima KB | 1(首选) | 标记 `--no-kb`,只走 Knowly |
| Knowly | 1(必选) | 标记 `--no-knowly`,只走 ima KB(必须有兜底) |
| 微信 | 通知层 | 失败时写入 `/tmp/wechat_send_failed.log`,后续 `notify_retry.py` 重试 |

> **核心原则**: 任何单条失败都不应阻塞写作流水线。`dual_backup.py` 实现里: 任意一边失败时,另一边仍正常继续,然后整体退出码反映部分失败。

## 5. 备份状态查询

```bash
# 列出某本书的所有备份(本地 + 已知的 KB / Knowly)
python3 scripts/dual_backup.py --list --book <书名>

# 检查某章是否双备份成功
python3 scripts/dual_backup.py --check --book <书名> --chapter N
```

输出格式:

```
=== 备份状态: 《书名》 第 N 章 ===
chapters/chNN_xxx.md
  [ima KB] ✅  yuangs/books/<书名>/chapters/chNN_xxx.md — <时间>
  [Knowly] ✅  /knowly_data/<书名>/chNN_xxx.md — <时间>
```

## 6. 不变量

写书过程中任何时刻:

```
INV-1: 工作目录的 chapters/ 文件数 == 已双备份的 chapter 数
INV-2: _COMPLETE_BOOK.md 存在 ⟹ 所有大纲章节已双备份
INV-3: ima KB 上能找到 yuangs/books/<书名>/ 下的所有 chNN 文件
INV-4: Knowly NAS 上存在对应 /knowly_data/<书名>/chNN 文件
```

`dual_backup.py --invariant-check` 会主动校验全部四条。
