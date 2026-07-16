---
name: toutiao-auto-publisher
description: 今日头条自动发布工具 — 检查登录、扫码登录、发布图文文章到头条号，支持正文配图、封面图、声明勾选、草稿模式。触发词："发头条"、"头条发布"、"发布到头条"。
version: 1.5.1
author: 摸鱼哥（咸鱼观天下）
homepage: https://github.com/xiaohao80
---

# 今日头条自动发布 Skill

基于 Playwright 的今日头条（头条号）自动发布工具。持久化登录、图文文章发布、正文配图、封面设置、声明勾选一体化。

## 功能

- **check** — 检查登录状态
- **login** — 扫码登录（首次使用）
- **publish** — 发布图文文章（支持正文配图、封面、草稿模式）

## 前置条件

1. 已有头条号（mp.toutiao.com）
2. Python 3.8+ 已安装
3. Playwright 已安装（`pip install playwright && playwright install chromium`）
4. 首次使用需扫码登录，登录态保存在 `~/.toutiao-browser-data/`，有效期约30天

## 安装依赖

```bash
pip install playwright playwright-stealth
playwright install chromium
```

> ⚠️ `playwright-stealth` 是**必须依赖**，不加的话头条反爬检测会返回7050保存失败

## 使用方法

### 1. 首次登录

```bash
python {SKILL_DIR}/toutiao_publisher.py login
```

会弹出浏览器，在 mp.toutiao.com 页面扫码登录。登录态自动保存。

### 2. 检查登录状态

```bash
python {SKILL_DIR}/toutiao_publisher.py check
```

### 3. 发布图文文章

```bash
python {SKILL_DIR}/toutiao_publisher.py publish \
  --title "文章标题" \
  --content-file "article.md" \
  --cover "cover.png" \
  --images "img1.png" "img2.png"
```

### 4. 存草稿（不直接发布）

```bash
python {SKILL_DIR}/toutiao_publisher.py publish \
  --title "文章标题" \
  --content-file "article.md" \
  --cover "cover.png" \
  --draft
```

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--title` | 是 | 文章标题 |
| `--content` | 否 | 文章正文（直接传入，与 --content-file 二选一） |
| `--content-file` | 否 | 文章正文文件路径（支持 Markdown 格式） |
| `--cover` | 否 | 封面图路径（建议 16:9 比例）。v1.5.1：封面失败不阻断流程，头条自动用正文第一张配图当封面 |
| `--images` | 否 | 正文配图路径（可多张，空格分隔） |
| `--draft` | 否 | 存草稿（不直接发布） |
| `--debug-dir` | 否 | 调试截图目录（默认当前目录） |

`{SKILL_DIR}` 为本 skill 所在目录，通常为 `~/.workbuddy/skills/toutiao-auto-publisher/`。

## 发布流程

```
打开发布页 → 填标题 → 上传图片到头条图床拿CDN URL → 填正文（图片按[配图N]占位符穿插插入）→ 设置封面（失败则头条自动用正文配图）→ 勾选声明 → 发布/存草稿
```

每一步都会自动截图（`debug_toutiao_*.png`），方便排查问题。

## 正文格式支持

支持简单 Markdown 格式：
- `# 标题1` / `## 标题2` / `### 标题3`
- `> 引用文字`
- `- 列表项`
- `---` 分隔线
- `**加粗**`
- `[配图1]` / `[配图1：描述]` 配图占位符（**真正穿插插入正文**，v1.5.0 方案）

## 技术要点

1. **持久化登录**：使用 `launch_persistent_context` + `~/.toutiao-browser-data`，Cookie有效期约30天
2. **playwright-stealth 反检测（必须！）**：头条有严格的反爬检测，不加 stealth 的 Playwright 会被识别为自动化工具，API返回 `7050 保存失败`。用 `playwright-stealth` 的 `Stealth().apply_stealth_async(context)` 彻底隐藏自动化特征
3. **标题输入框是 `<textarea>`**：头条标题不是 contenteditable div，而是 `textarea[placeholder*="标题"]`，必须用键盘输入（`keyboard.type`）触发 React onChange
4. **正文用键盘输入**：ProseMirror 编辑器，用 `keyboard.type(delay=30)` 逐行输入触发自动保存
5. **草稿保存机制**：头条没有"存草稿"按钮，依赖编辑器自动保存（失焦后5-8秒触发）。stealth 模式下 API 返回 `code:0 保存成功`，非 stealth 返回 `7050 保存失败`
6. **AI助手浮层**：头条后台有AI抽屉的 `.byte-drawer-mask` 全屏蒙层会拦截点击，必须 `el.remove()` 彻底删除（`display:none` 无效）
7. **声明勾选**：头条用自研 checkbox 组件，必须用真实 `click()` 事件触发 React 状态更新，JS设 `checked=true` 无效
8. **草稿箱验证**：跳转 `/profile_v4/manage/draft` 检查"共 X 条"确认保存成功
9. **封面上传：走真实 UI 流程（v1.3.0 方案，推荐）**：直接走头条的图片库弹窗——删 AI 蒙层（两个都要删）→ click `.article-cover-add` → 弹窗出现 → `set_input_files` 给弹窗里的 `input[type="file"]` → 等"已上传 N 张"文字出现 → 点"确定"按钮。**不要**用 base64 dataUrl 注入 onChange（v1.2.0 方案）—— 头条服务端只接受 CDN URL，dataUrl 在自动保存时会被丢弃
10. **正文配图穿插：spice API + execCommand insertHTML（v1.5.0 方案）**：
    - **不要再用工具栏按钮 [11] 插入图片**（v1.4.0 方案被废弃）—— 头条工具栏图片按钮有"一次性"限制：第一次点击后弹出 file input，上传完后再点不再弹出，导致配图2-4全部失败
    - **新方案**：
      1. 全部图片先批量上传到 `https://mp.toutiao.com/spice/image?upload_source=20020002&aid=1231&device_platform=web`（浏览器里 fetch，带 cookie 凭证），拿到 `image-tt-private.toutiao.com` CDN URLs
      2. 写正文遇到 `[配图N]` 占位符时，调 `document.execCommand('insertHTML', false, '<p><img src="CDN_URL" alt="" style="max-width:100%;"/></p>')` 在当前光标位置就地插入
      3. Syl/ProseMirror 编辑器自动处理 execCommand 插入的 HTML，包装为 `<div __syl_tag="...">` + "编辑搜图" 容器，正确注册到 ProseMirror state
      4. 图片3秒后仍持久存在，不会被状态同步清除
    - **优势**：图片真正穿插在正文中对应位置（如"对比图"在"全网笑话"段后），不是堆到末尾
11. **头条图床 API（v1.5.0 直接调用）**：
    - 上传接口：`POST https://mp.toutiao.com/spice/image?upload_source=20020002&aid=1231&device_platform=web` (multipart/form-data，字段 `image` + `upload_source` + `aid` + `device_platform`)
    - ⚠️ **正确路径是 `/spice/image`，不是 `/mp/agw/article_material/photo/spice/image`**（那个 404）
    - 响应 `{"code":0,"data":{"image_uri":"...","image_url":"https://image-tt-private.toutiao.com/..."}}`
    - **必须在浏览器里 fetch**（带 credentials: include），不能从 Python 端直接 requests（缺 cookie）

## 踩坑记录

1. **7050 保存失败 = 反爬检测（核心问题！）**：头条API `/mp/agw/article/publish` 在检测到 Playwright 时返回 `{"code":7050,"message":"保存失败"}`。仅隐藏 `navigator.webdriver` 不够，必须用 `playwright-stealth` 库
2. **标题输入框是 textarea 不是 contenteditable**：页面上只有1个 `contenteditable`（ProseMirror正文），标题是独立的 `<textarea placeholder="请输入文章标题（2～30个字）">`。之前用 `div[contenteditable]:first-of-type` 选错了元素，标题被输入到正文区域，API请求 `title=` 为空
3. **JS注入不触发自动保存**：`execCommand('insertHTML')` 和 `innerText=` 能让内容显示在编辑器里，但不触发 React 状态更新，自动保存API收到的 `title` 和 `content` 为空或不完整。必须用 `keyboard.type()` 真实键盘输入
4. **byte-drawer-mask 拦截点击**：头条AI助手抽屉的 `.byte-drawer-mask` 是全屏蒙层，`display:none` 仍拦截事件，必须 `el.remove()` 彻底删除
5. **自研 checkbox 不能 JS 设 checked**：头条 checkbox 是 React 组件，不监听原生 `checked` 属性变化，必须用真实 `click()` 事件触发
6. **"草稿保存中..."是常驻UI**：不代表保存成功或失败，唯一可靠验证方式是跳转草稿箱页面检查文章数量
7. **发布有两步**：先点"预览并发布"，弹出确认框后再点"确认发布"
8. **Cookie有效期约30天**：过期后需要重新执行 `login` 命令
9. **封面"+号"必须清 AI 蒙层才能 click**（v1.2.0 → v1.3.0 修复）：头条后台有 `.byte-drawer-wrapper.ai-assistant-drawer` AI 助手抽屉和 `.byte-drawer-mask` 蒙层，**两个都会拦截 click**。只删 mask 是不够的，wrapper 也会拦截 click，必须**两个都 remove()**。清干净后 click `.article-cover-add` 就能弹出图片库弹窗
10. **封面不能注入 base64 dataUrl**（v1.2.0 → v1.3.0 修复）：用 React fiber onChange 注入 `data:image/png;base64,...` 看起来 state 有数据、预览图显示，但**草稿箱实际无封面**！头条服务端只接受 CDN URL，dataUrl 在自动保存时被丢弃。**正确做法**：走真实 UI 流程 —— set_input_files 给弹窗里的 file input，让头条内部 `spice/image` + `photo/info` 走完拿到 CDN URL
11. **工具栏图片按钮 [11] 一次性限制**（v1.4.0 痛点，v1.5.0 彻底解决）：用 `.syl-toolbar-button` 的第12个按钮插入图片时，**第一次成功上传后，再点不再弹出 file input**（头条内部缓存了"已添加图片"状态）。重置工具栏、滚动、重新 focus 全部无效。导致配图2-4全部失败。
    - **错误解决思路**：尝试重试3次、多文件一次传（multiple=true导致重复插入8张）、刷新页面（代价大且丢失已写内容）
    - **正确方案（v1.5.0）**：完全抛弃工具栏按钮，**用 `document.execCommand('insertHTML')` 在光标位置就地插入 `<img src="CDN_URL">`**。先通过 spice API 拿 CDN URL，再 insertHTML，Syl/ProseMirror 编辑器自动处理，图片3秒后仍持久存在
12. **ProseMirror view 找不到**（v1.4.0 调研过程）：Syl 编辑器的 `div.ProseMirror` 只有 `pmViewDesc` 属性（没有 `view`）。`pmViewDesc.parent` 为 null（只有一层）。React fiber 向上/向下遍历 stateNode/memoizedState 都没有 dispatch 函数。**结论：无法从 DOM 直接拿到 ProseMirror EditorView**，必须改用其他机制（execCommand 或 paste event）
13. **spice API 路径注意**（v1.5.0）：**正确**是 `https://mp.toutiao.com/spice/image?upload_source=20020002&aid=1231&device_platform=web`，**错误**（404）是 `/mp/agw/article_material/photo/spice/image`。注意 `upload_source=20020002`（正文用），封面上传是 `20020003`
14. **fetch spice API 必须在浏览器里**（v1.5.0）：用 page.evaluate 在浏览器上下文 fetch，带 credentials: include。从 Python 端 requests 调会缺 cookie 凭证失败
15. **封面失败不阻断（v1.5.1）**：`.article-cover-add` 选择器不稳定（有时被 AI 抽屉遮挡），封面上传失败时 try/except 捕获后继续流程。**头条系统兜底**：自动从正文配图里挑第一张作为封面。策略建议：正文第一张配图就按封面风格设计（带标题文字、信息密度高），这样即使封面上传步骤失败，头条自动选的图也够用

## 关于作者

**摸鱼哥** — 8年Java程序员，业余搞科技评论和AI自动化工具。

- 微信公众号：**咸鱼观天下**（科技吐槽 + AI踩坑日记）
- GitHub：[@xiaohao80](https://github.com/xiaohao80)（Star一下，下次更新更快）
- 小红书：搜「咸鱼观天下」

这个 Skill 是摸鱼哥开发并开源的，如果对你有帮助，来个 Star 或关注公众号支持一下！
