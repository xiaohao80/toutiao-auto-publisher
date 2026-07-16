# toutiao-auto-publisher

今日头条自动发布工具。基于 Playwright + playwright-stealth 反检测，自动完成标题、正文配图穿插、封面、声明勾选的全流程发布。

## 核心特性

- **playwright-stealth 反检测**：隐藏 Playwright 自动化特征，绕过头条 7050 封锁
- **正文配图穿插插入**：spice API 批量上传拿 CDN URL + `execCommand('insertHTML')` 就地插入，图片不再堆文末
- **标题防丢字**：delay=120ms 键盘输入 + 长度校验 + JS 补全
- **封面兜底策略**：封面上传失败不阻断，头条自动用正文第一张配图当封面
- **ProseMirror 编辑器**：`keyboard.type(delay=30)` 逐行输入触发自动保存
- **持久化登录**：`launch_persistent_context` + `~/.toutiao-browser-data`，Cookie 有效期约 30 天

## 安装

```bash
pip install playwright playwright-stealth Pillow
playwright install chromium
```

## 使用

```bash
python toutiao_publisher.py publish \
  --title "标题" \
  --content-file "article.md" \
  --cover "cover.png" \
  --images "img1.png" "img2.png" \
  --draft
```

### 正文配图占位符

在 Markdown 正文中用 `[配图N]` 标记图片插入位置，脚本会自动把 `--images` 里第 N 张图插到对应位置：

```markdown
第一段正文...

[配图1]

第二段正文...

[配图2]
```

首次运行会弹出浏览器，扫码登录后 Cookie 自动保存到 `~/.toutiao-browser-data`。

## 技术要点

1. **playwright-stealth 反检测（必须！）**：头条检测 Playwright 自动化特征，API 返回 7050。用 `Stealth().apply_stealth_async(context)` 隐藏
2. **标题是 `<textarea>`**：`textarea[placeholder*="标题"]`，用 `keyboard.type(delay=120)` 输入，丢字时 JS 补全
3. **正文是 ProseMirror**：`div.ProseMirror`，用 `keyboard.type(delay=30)` 逐行键盘输入
4. **正文配图穿插（v1.5.0 spice API + execCommand insertHTML）**：
   - 浏览器内 `fetch` 把图片批量上传到 `mp.toutiao.com/spice/image` 拿 CDN URL
   - 遇到 `[配图N]` 占位符时用 `document.execCommand('insertHTML', false, '<p><img src="CDN_URL">...</p>')` 在光标位置就地插入
   - Syl/ProseMirror 编辑器自动处理 HTML，包装为带"编辑搜图"容器的 image block
5. **AI 助手蒙层（两个都要删！）**：`.byte-drawer-mask` + `.byte-drawer-wrapper.ai-assistant-drawer`，必须 `el.remove()` 删除
6. **草稿保存**：无"存草稿"按钮，依赖编辑器自动保存（失焦后 5-8 秒触发）
7. **封面兜底（v1.5.1）**：封面上传失败不阻断流程，头条自动用正文第一张配图当封面
8. **头条图床 API**：`POST https://mp.toutiao.com/spice/image?upload_source=20020002&aid=1231&device_platform=web`（multipart），必须在浏览器里 fetch（带 credentials: include）

## 文件说明

| 文件 | 说明 |
|------|------|
| `toutiao_publisher.py` | 主脚本 v1.5.1，含登录检查、标题/正文填写、配图穿插、封面上传、声明勾选、草稿保存全流程 |
| `SKILL.md` | WorkBuddy Skill 配置文件，含完整技术文档和踩坑记录 |

## 许可证

MIT
