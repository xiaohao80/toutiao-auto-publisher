---
name: toutiao-auto-publisher
description: 今日头条自动发布工具 — 检查登录、扫码登录、发布图文文章到头条号，支持正文配图、封面图、声明勾选、草稿模式。触发词："发头条"、"头条发布"、"发布到头条"。
version: 1.6.1
author: 摸鱼哥（摸鱼观天下）
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

> 💡 **小号测试**：用 `--browser-data` 参数指定独立浏览器数据目录，避免污染主号登录态
> ```bash
> python {SKILL_DIR}/toutiao_publisher.py --browser-data ~/.toutiao-browser-data-small login
> ```

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

### 5. 小号发布

```bash
python {SKILL_DIR}/toutiao_publisher.py \
  --browser-data ~/.toutiao-browser-data-small \
  publish \
  --title "文章标题" \
  --content-file "article.md" \
  --cover "cover.png" \
  --images "img1.png" "img2.png" \
  --draft
```

## 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--title` | 是 | 文章标题 |
| `--content` | 否 | 文章正文（直接传入，与 --content-file 二选一） |
| `--content-file` | 否 | 文章正文文件路径（支持 Markdown 格式） |
| `--cover` | 否 | 封面图路径（建议 ≥672×462）。v1.6.1：先清除自动提取的封面再走真实UI流程上传，失败才降级API注入 |
| `--images` | 否 | 正文配图路径（可多张，空格分隔） |
| `--draft` | 否 | 存草稿（不直接发布） |
| `--debug-dir` | 否 | 调试截图目录（默认当前目录） |
| `--browser-data` | 否 | 浏览器数据目录（默认~/.toutiao-browser-data，小号用~/.toutiao-browser-data-small） |

`{SKILL_DIR}` 为本 skill 所在目录，通常为 `~/.workbuddy/skills/toutiao-auto-publisher/`。

## 发布流程

```
打开发布页 → 填标题 → 上传图片到头条图床拿CDN URL → 填正文（图片按[配图N]占位符穿插插入）→ 设置封面（先清除自动提取的封面 → 真实UI流程：点+号 → 切到「上传图片」tab → set_input_files → 点确定）→ 勾选声明 → 发布/存草稿
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
9. **封面上传：清除自动封面 + 真实UI流程（v1.6.1 方案，推荐）**：基于用户手动操作经验，封面流程必须分两步走：
   - **Step 1：清除自动提取的封面**（`_clear_auto_covers`）。当正文有配图时，头条会自动提取正文图片作为封面候选（最多4个），排在自定义封面前面。用户手动操作时也是先删这些自动封面。删除按钮是 `<i class="article-cover-delete">`（一个空文本的i元素）
   - **Step 2：真实UI流程上传自定义封面**（`_upload_cover_ui`）：
     1. 点击 `.article-cover-add`（+号按钮）
     2. 等待抽屉 `.byte-drawer.mp-ic-img-drawer` 打开
     3. **关键：切到「上传图片」tab**（`.byte-tabs-header-title:has-text("上传图片")`），默认在"正文图片"tab是没有 file input 的
     4. `set_input_files` 上传文件
     5. 等"已上传"提示
     6. 点确定（`.byte-drawer-footer button.btn-primary`）
   - **v1.6.0 失败教训**：React fiber 注入 `fiber[6].onChange(string)` 只能更新UI临时state，自动保存时头条还是用正文第一张图当封面。走真实UI流程才能让头条走自己的状态更新路径，封面才真正持久化
   - **降级链**：清除+UI → API+React注入（仅UI显示，保存可能不持久）→ 头条系统兜底（正文首图）
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
15. **封面失败不阻断（v1.5.1→v1.6.0）**：v1.5.1 时 `.article-cover-add` 选择器不稳定导致封面上传经常失败，只能靠头条系统兜底（自动用正文首图）。v1.6.0 改为 API直传+React注入方案，绕过UI选择器，封面上传成功率大幅提升。仍保留三级降级：API注入 → UI方案 → 正文首图兜底
16. **封面真实UI流程（v1.6.1 核心改进，v1.6.0 React注入被废弃）**：
    - **v1.6.0 问题**：React fiber `onChange(string)` 注入看起来成功，预览图也显示了，但**草稿箱里保存的是正文配图1，不是自定义封面**！自动保存时头条用的是另一套state，React注入只更新了UI临时state
    - **用户手动操作经验**（v1.6.1 突破口）：手动上传封面时必须先删除自动提取的封面（来自正文配图），否则自定义封面不显示
    - **新方案（v1.6.1 验证可行）**：
      1. `_clear_auto_covers`：找 `<i class="article-cover-delete">` 删除按钮（一个空文本i元素，className含"delete"），点击删除所有自动提取的封面
      2. 点击 `.article-cover-add` 打开抽屉 `.byte-drawer.mp-ic-img-drawer`
      3. **切tab**（关键！）：点 `.byte-tabs-header-title:has-text("上传图片")`，从"正文图片"切到"上传图片"，file input 才出现
      4. `set_input_files` 上传封面图
      5. 等"已上传"提示
      6. 点 `.byte-drawer-footer button.btn-primary` 确定
    - **v1.6.1 测试结果**：自动保存7秒就"成功"（之前v1.6.0是30秒"保存中"），草稿箱封面ID = 上传图片ID = 自定义封面
    - **降级链**：清除+UI → API+React注入（仅UI显示）→ 头条系统兜底（正文首图）
17. **`--browser-data` 参数支持小号测试**（v1.6.1 新增）：用独立浏览器数据目录登录小号，避免主号被风控
    - 主号：`--browser-data ~/.toutiao-browser-data`（默认）
    - 小号：`--browser-data ~/.toutiao-browser-data-small`
    - 用法：先 `python toutiao_publisher.py --browser-data ~/.toutiao-browser-data-small login` 扫码登录小号，再发布时同样带 `--browser-data`

## 关于作者

**摸鱼哥** — 8年Java程序员，业余搞科技评论和AI自动化工具。

- 微信公众号：**摸鱼观天下**（科技吐槽 + AI踩坑日记）
- GitHub：[@xiaohao80](https://github.com/xiaohao80)（Star一下，下次更新更快）
- 小红书：搜「摸鱼观天下」

这个 Skill 是摸鱼哥开发并开源的，如果对你有帮助，来个 Star 或关注公众号支持一下！
