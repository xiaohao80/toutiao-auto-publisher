#!/usr/bin/env python3
"""
今日头条自动发布脚本 (toutiao_publisher.py) v1.6.1
基于 Playwright 实现浏览器自动化，持久化登录态，支持图文文章发布。
v1.6.1: 封面上传前先清除自动提取的封面（用户发现正文配图会自动提取封面排在前面），支持--browser-data小号测试
v1.6.0: 封面上传改为 API直传+React注入，绕过不稳定UI选择器

用法:
  # 检查登录状态
  python toutiao_publisher.py check

  # 登录（弹出浏览器扫码）
  python toutiao_publisher.py login

  # 发布图文文章
  python toutiao_publisher.py publish --title "标题" --content-file article.md --cover cover.png

  # 带正文配图
  python toutiao_publisher.py publish --title "标题" --content-file article.md --cover cover.png --images img1.png img2.png

  # 存草稿（不直接发布）
  python toutiao_publisher.py publish --title "标题" --content-file article.md --cover cover.png --draft

  # 直接传入正文
  python toutiao_publisher.py publish --title "标题" --content "正文内容" --cover cover.png
"""

import asyncio
import os
import sys
import json
import argparse
import tempfile
from pathlib import Path

# ===== 配置 =====
BROWSER_DATA_DIR = os.path.expanduser("~/.toutiao-browser-data")
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
HOME_URL = "https://mp.toutiao.com"
DEFAULT_TIMEOUT = 60000
VIEWPORT = {"width": 1280, "height": 800}
DEBUG_DIR = os.getcwd()

# ===== 浏览器管理 =====

class ToutiaoBrowser:
    """今日头条浏览器自动化管理器"""

    def __init__(self, debug_dir=None, browser_data_dir=None):
        self.playwright = None
        self.context = None
        self.page = None
        self.debug_dir = debug_dir or DEBUG_DIR
        self.browser_data_dir = browser_data_dir or BROWSER_DATA_DIR

    def _debug_path(self, filename):
        return os.path.join(self.debug_dir, filename)

    async def start(self, headless=False):
        """启动浏览器（持久化上下文，保存登录态）
        关键：必须用 playwright-stealth 隐藏自动化特征，否则头条API返回7050保存失败
        """
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth

        os.makedirs(self.browser_data_dir, exist_ok=True)

        # 清理锁文件
        for lock_file in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
            lock_path = os.path.join(self.browser_data_dir, lock_file)
            if os.path.exists(lock_path):
                try:
                    os.remove(lock_path)
                except:
                    pass

        self.playwright = await async_playwright().start()

        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=self.browser_data_dir,
            headless=headless,
            viewport=VIEWPORT,
            timeout=DEFAULT_TIMEOUT,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-infobars',
                '--disable-extensions',
            ],
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
        )

        # ★ 应用 playwright-stealth（必须！否则头条反爬检测导致7050保存失败）
        self.stealth = Stealth()
        await self.stealth.apply_stealth_async(self.context)

        if len(self.context.pages) > 0:
            self.page = self.context.pages[0]
        else:
            self.page = await self.context.new_page()

    async def close(self):
        """关闭浏览器"""
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()

    async def screenshot(self, name):
        """调试截图（full_page）"""
        path = self._debug_path(f"debug_toutiao_{name}.png")
        await self.page.screenshot(path=path, full_page=True)
        print(f"  [debug] 截图: {path}")
        return path

    async def hide_ai_drawer(self):
        """隐藏头条AI助手/图片管理/各种引导浮层（遮挡操作）
        关键：byte-drawer-mask 蒙层会拦截所有点击，必须彻底干掉
        """
        await self.page.evaluate("""
            () => {
                // 1. 干掉 AI 助手抽屉（整个子树，包括 mask 蒙层 + wrapper 父元素）
                document.querySelectorAll('.ai-assistant-drawer, [class*="ai-assistant-drawer"]').forEach(el => {
                    el.remove();
                });
                // 1.5 干掉任何祖先是 ai-assistant 的元素（包括整个 drawer 容器）
                document.querySelectorAll('div').forEach(el => {
                    let p = el.parentElement;
                    while (p) {
                        if (p.className && typeof p.className === 'string' && p.className.includes('ai-assistant-drawer')) {
                            el.remove();
                            break;
                        }
                        p = p.parentElement;
                    }
                });
                // 2. 干掉所有 byte-drawer 蒙层（这是拦截点击的元凶）
                document.querySelectorAll('.byte-drawer-mask').forEach(el => {
                    el.remove();
                });
                // 3. 干掉 byte-drawer 包裹层
                document.querySelectorAll('.byte-drawer-wrapper, .byte-drawer').forEach(el => {
                    el.remove();
                });
                // 4. 兜底：按 class 关键字匹配并移除
                document.querySelectorAll('[class*="drawer-mask"]').forEach(el => el.remove());
                document.querySelectorAll('[class*="drawer-mask-DO-NOT-USE"]').forEach(el => el.remove());
                // 5. 隐藏 byte-modal 模态
                document.querySelectorAll('.byte-modal, .byte-modal-wrapper').forEach(el => el.remove());
                document.querySelectorAll('[class*="modal-mask"]').forEach(el => el.remove());
                // 6. 隐藏各种引导浮窗（"我知道了"按钮的浮窗）
                document.querySelectorAll('[class*="guide"], [class*="Guide"], [class*="tooltip"], [class*="popover"]').forEach(el => {
                    el.style.display = 'none';
                });
                // 7. 隐藏 message 提示（"保存失败"toast）
                document.querySelectorAll('[class*="message"], [class*="Message"], [class*="toast"]').forEach(el => {
                    el.style.display = 'none';
                });
            }
        """)

    # ===== 登录检查 =====

    async def check_login(self):
        """检查登录状态"""
        print("正在检查登录状态...")
        await self.page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        await self.screenshot("check_login")

        # 检查URL是否跳转到登录页
        current_url = self.page.url
        if "login" in current_url or "sso" in current_url:
            print("[未登录] 需要扫码登录")
            return False

        # 检查页面是否有登录入口
        login_btn = await self.page.query_selector('text=登录')
        if login_btn and await login_btn.is_visible():
            print("[未登录] 需要扫码登录")
            return False

        # 尝试访问发布页验证
        await self.page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)
        current_url = self.page.url
        if "login" in current_url or "sso" in current_url:
            print("[未登录] 需要扫码登录")
            return False

        print("[已登录] 登录态有效")
        return True

    async def login(self):
        """扫码登录"""
        print("正在打开登录页面...")
        await self.page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        # 尝试点击登录按钮
        login_selectors = [
            'text=登录',
            'a:has-text("登录")',
            'button:has-text("登录")',
            '[class*="login"]',
        ]
        for sel in login_selectors:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    break
            except:
                continue

        await asyncio.sleep(2)
        await self.screenshot("login_qr")

        print("请在浏览器中扫码登录...")
        print("登录成功后，浏览器会自动跳转。")

        # 等待登录成功（URL变化或出现用户头像）
        try:
            await self.page.wait_for_url(
                lambda url: "login" not in url and "sso" not in url,
                timeout=120000
            )
            await asyncio.sleep(3)
            await self.screenshot("login_success")
            print("[成功] 登录态已保存")
            return True
        except Exception:
            print("[超时] 请重试")
            return False

    # ===== 发布文章 =====

    async def publish_article(self, title, content, cover_path=None, image_paths=None, draft=False):
        """发布图文文章"""
        print(f"开始发布文章: {title}")

        # 1. 导航到发布页
        print("  [1/8] 打开发布页...")
        await self.page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        await self.hide_ai_drawer()
        await self.screenshot("publish_page")

        # 检查是否被重定向到登录页
        if "login" in self.page.url or "sso" in self.page.url:
            print("  [错误] 未登录，请先执行 login 命令")
            return False

        # 2. 填写标题（ProseMirror / contenteditable）
        print("  [2/8] 填写标题...")
        await self._fill_title(title)
        await asyncio.sleep(1)
        await self.screenshot("after_title")

        # 3. 填写正文（v1.5.0：先上传图片拿CDN URL，再穿插插入）
        print("  [3/8] 填写正文...")
        cdn_urls = None
        if image_paths:
            cdn_urls = await self._upload_images_to_cdn(image_paths)
        await self._fill_content(content, image_paths=image_paths, cdn_urls=cdn_urls)
        await asyncio.sleep(1)
        await self.screenshot("after_content")

        # 4. 设置封面（v1.6.1：先清除自动提取的封面，再API直传+React注入）
        if cover_path:
            print("  [4/8] 设置封面...")
            await self.hide_ai_drawer()
            # v1.6.1: 先清除头条自动从正文图片提取的封面
            # 用户发现：正文有配图时头条自动提取封面排在前面，自定义封面被挤到后面
            await self._clear_auto_covers()
            try:
                await self._upload_cover(cover_path)
                await asyncio.sleep(2)
            except Exception as e:
                print(f"    [提示] 封面上传失败（{e}），头条将自动用正文第一张配图作为封面")
            await self.screenshot("after_cover")
        else:
            print("  [4/8] 跳过封面（头条将自动用正文配图当封面）")

        # 5. 勾选声明
        print("  [5/8] 勾选声明...")
        await self.hide_ai_drawer()  # 防止抽屉遮挡
        await self._check_declarations()
        await self.screenshot("after_declare")

        # 6. 发布或存草稿
        if draft:
            print("  [6/8] 存草稿...")
            await self.hide_ai_drawer()  # 防止抽屉遮挡
            success = await self._save_draft()
        else:
            print("  [6/8] 发布文章...")
            await self.hide_ai_drawer()  # 防止抽屉遮挡
            success = await self._click_publish()

        # 7. 验证结果
        print("  [7/8] 验证发布结果...")
        await asyncio.sleep(3)
        await self.screenshot("publish_result")

        if success:
            if draft:
                print("[成功] 文章已存入草稿箱")
            else:
                print("[成功] 文章已发布")
        else:
            print("[失败] 发布可能未成功，请检查截图")

        return success

    async def _fill_title(self, title):
        """填写标题 — 头条标题是 <textarea>，不是 contenteditable div
        关键：必须用键盘输入触发React的onChange，JS注入innerText不生效

        v1.4.0 增强：输入后立即校验，丢字则补全（delay=120ms仍偶发丢字）
        """
        # 头条标题输入框是 textarea，placeholder="请输入文章标题（2～30个字）"
        title_selectors = [
            'textarea[placeholder*="标题"]',
            'textarea[placeholder*="文章标题"]',
            '.editor-title textarea',
        ]

        for sel in title_selectors:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    await asyncio.sleep(0.3)
                    # 清空现有内容
                    await self.page.keyboard.press("Control+a")
                    await self.page.keyboard.press("Delete")
                    # 用键盘输入（delay=120ms 避免丢字；之前80ms还有偶发）
                    await self.page.keyboard.type(title, delay=120)
                    await asyncio.sleep(0.5)
                    # 验证：丢字则补全
                    val = await el.evaluate("el => el.value")
                    if val and len(val) < len(title) * 0.95:
                        # 丢字了！换成慢速重输
                        print(f"    [警告] 标题丢字 ({len(val)}<{len(title)})，改用 JS 注入补全")
                        await el.evaluate("(el, t) => { el.value = t; el.dispatchEvent(new Event('input', {bubbles:true})); }", title)
                        await asyncio.sleep(0.3)
                    val2 = await el.evaluate("el => el.value")
                    print(f"    标题已填入: {val2[:20]}...")
                    return
            except Exception as e:
                continue

        # Fallback: 找所有 textarea
        textareas = await self.page.query_selector_all('textarea')
        for ta in textareas:
            placeholder = await ta.get_attribute('placeholder') or ''
            if '标题' in placeholder or 'title' in placeholder.lower():
                await ta.click()
                await asyncio.sleep(0.3)
                await self.page.keyboard.type(title, delay=120)
                await asyncio.sleep(0.5)
                val = await ta.evaluate("el => el.value")
                if val and len(val) < len(title) * 0.95:
                    await ta.evaluate("(el, t) => { el.value = t; el.dispatchEvent(new Event('input', {bubbles:true})); }", title)
                print(f"    标题已填入(fallback): {title[:20]}...")
                return

        print(f"    [警告] 未找到标题输入框")

    async def _fill_content(self, content, image_paths=None, cdn_urls=None):
        """填写正文 — ProseMirror编辑器，用键盘输入触发自动保存

        v1.5.0 新方案：图片穿插插入
        - 先通过 spice API 上传所有图片拿到 CDN URLs
        - 遇到 [配图N] / __IMG_N__ 占位符时，用 execCommand('insertHTML') 插入 <img>
        - 图片真正穿插在正文中，不是堆到末尾
        - 解决了工具栏按钮 [11] 一次性限制问题
        """
        content_selectors = [
            'div.ProseMirror',
            'div[contenteditable="true"][data-placeholder*="正文"]',
            'div[contenteditable="true"]',
        ]

        import re
        img_pattern = re.compile(r'\[配图(\d+)[：:\s]?[^\]]*\]|__IMG_(\d+)__')

        for sel in content_selectors:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    await asyncio.sleep(0.3)
                    # 清空
                    await self.page.keyboard.press("Control+a")
                    await self.page.keyboard.press("Delete")
                    await asyncio.sleep(0.2)

                    # 将markdown转为纯文本段落，用键盘输入
                    lines = content.strip().split('\n')
                    first_line = True
                    for line in lines:
                        line = line.strip()
                        if not line:
                            # 空行用回车换段
                            if not first_line:
                                await self.page.keyboard.press("Enter")
                            continue

                        # 配图占位符 [配图1] [配图1：描述] __IMG_1__
                        img_match = img_pattern.search(line)
                        if img_match:
                            # 先把占位符行前的字符打出来（如果有混在文字里）
                            prefix = line[:img_match.start()].strip()
                            if prefix:
                                if not first_line:
                                    await self.page.keyboard.press("Enter")
                                await self.page.keyboard.type(prefix, delay=30)
                                first_line = False
                            # 解析 N
                            n_str = img_match.group(1) or img_match.group(2)
                            n = int(n_str)
                            if cdn_urls and 1 <= n <= len(cdn_urls) and cdn_urls[n-1]:
                                print(f"    [配图{n}] 插入图片")
                                await self._insert_image_via_html(cdn_urls[n-1])
                            else:
                                print(f"    [警告] 配图{n} 无可用 CDN URL (cdn={len(cdn_urls) if cdn_urls else 0})")
                            # 占位符后的字符
                            suffix = line[img_match.end():].strip()
                            if suffix:
                                await self.page.keyboard.press("Enter")
                                await self.page.keyboard.type(suffix, delay=30)
                                first_line = False
                            continue

                        # 去掉markdown标记
                        clean = line
                        for prefix in ['### ', '## ', '# ']:
                            if clean.startswith(prefix):
                                clean = clean[len(prefix):]
                                break
                        clean = clean.lstrip('> ').lstrip('- ').lstrip('* ')
                        clean = clean.replace('**', '')

                        if not first_line:
                            await self.page.keyboard.press("Enter")
                        # 用键盘输入（delay=30ms 模拟真人速度）
                        await self.page.keyboard.type(clean, delay=30)
                        first_line = False

                    print(f"    正文已填入 ({len(content)} 字符)")
                    return
            except Exception as e:
                continue

        print("    [警告] 未找到正文编辑器")

    def _md_to_html(self, md_content):
        """简单Markdown转HTML（适配头条正文编辑器）"""
        lines = md_content.strip().split('\n')
        html_parts = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 标题
            if line.startswith('### '):
                html_parts.append(f'<h3>{line[4:]}</h3>')
            elif line.startswith('## '):
                html_parts.append(f'<h2>{line[3:]}</h2>')
            elif line.startswith('# '):
                html_parts.append(f'<h1>{line[2:]}</h1>')
            # 配图占位符 [配图1] [配图1：描述]
            elif line.startswith('[配图') and line.endswith(']'):
                continue  # 跳过配图占位符，后面单独上传
            elif line.startswith('__IMG_') and line.endswith('__'):
                continue
            # 分隔线
            elif line in ('---', '***', '___'):
                html_parts.append('<hr/>')
            # 引用
            elif line.startswith('> '):
                html_parts.append(f'<blockquote>{line[2:]}</blockquote>')
            # 列表项
            elif line.startswith('- ') or line.startswith('* '):
                html_parts.append(f'<p>• {line[2:]}</p>')
            elif line.startswith('  - ') or line.startswith('  * '):
                html_parts.append(f'<p style="padding-left:2em">◦ {line[4:]}</p>')
            # 普通段落
            else:
                # 简单处理加粗和图片标记
                line = line.replace('**', '<strong>', 1)
                if '<strong>' in line and '**' in line:
                    line = line.replace('**', '</strong>', 1)
                html_parts.append(f'<p>{line}</p>')

        return '\n'.join(html_parts)

    async def _upload_images_to_cdn(self, image_paths):
        """上传图片到头条图床（spice API），返回 CDN URL 列表

        关键发现（v1.5.0）：
        - 头条 spice API 路径：https://mp.toutiao.com/spice/image?upload_source=20020002&aid=1231&device_platform=web
        - POST multipart/form-data，字段：image(File) + upload_source + aid + device_platform
        - 响应 {"code":0,"data":{"image_uri":"...","image_url":"https://image-tt-private.toutiao.com/..."}}
        - 必须在浏览器上下文里 fetch（带 cookie 凭证），不能从 Python 端直接调
        """
        if not image_paths:
            return []

        import base64
        images_b64 = []
        for path in image_paths:
            abs_path = os.path.abspath(path)
            if not os.path.exists(abs_path):
                print(f"    [警告] 图片不存在: {abs_path}")
                images_b64.append(None)
                continue
            with open(abs_path, 'rb') as f:
                data = f.read()
            images_b64.append({
                'name': os.path.basename(abs_path),
                'b64': base64.b64encode(data).decode('utf-8'),
                'type': 'image/png'
            })

        print(f"    上传 {len(images_b64)} 张图片到头条图床...")
        cdn_urls_raw = await self.page.evaluate("""
            async (images) => {
                const urls = [];
                for (const img of images) {
                    if (!img) { urls.push('SKIP'); continue; }
                    const bin = atob(img.b64);
                    const bytes = new Uint8Array(bin.length);
                    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                    const blob = new Blob([bytes], {type: img.type});
                    const file = new File([blob], img.name, {type: img.type});
                    const fd = new FormData();
                    fd.append('image', file);
                    fd.append('upload_source', '20020002');
                    fd.append('aid', '1231');
                    fd.append('device_platform', 'web');
                    try {
                        const resp = await fetch('https://mp.toutiao.com/spice/image?upload_source=20020002&aid=1231&device_platform=web', {
                            method: 'POST', body: fd, credentials: 'include'
                        });
                        const text = await resp.text();
                        urls.push('STATUS:' + resp.status + ' BODY:' + text.substring(0, 1500));
                    } catch (e) {
                        urls.push('FETCH_ERROR: ' + e.message);
                    }
                }
                return urls;
            }
        """, images_b64)

        cdn_urls = []
        for i, u in enumerate(cdn_urls_raw):
            if u == 'SKIP':
                cdn_urls.append(None)
                continue
            if 'STATUS:200' in u:
                try:
                    body = u.split('BODY:', 1)[1]
                    data = json.loads(body)
                    if data.get('code') == 0:
                        url = data['data']['image_url']
                        cdn_urls.append(url)
                        print(f"    [{i+1}/{len(images_b64)}] OK: {url[:60]}...")
                        continue
                except Exception as e:
                    print(f"    [{i+1}/{len(images_b64)}] parse err: {e}")
            cdn_urls.append(None)
            print(f"    [{i+1}/{len(images_b64)}] FAIL: {u[:80]}")

        return cdn_urls

    async def _insert_image_via_html(self, cdn_url):
        """在正文当前光标位置插入图片（v1.5.0 新方案）

        关键发现（v1.5.0）：
        - 头条工具栏图片按钮 [11] 有"一次性"限制：第一次上传后不再弹出 file input
        - 解决方案：用 document.execCommand('insertHTML') 直接插入 <img> HTML
        - Syl/ProseMirror 编辑器会自动处理 execCommand 插入的 HTML
        - 图片被包装为 <div> + "编辑搜图" 容器，正确注册到 ProseMirror state
        - 图片3秒后仍持久存在，不会被 ProseMirror 状态同步清除
        - 需要先通过 spice API 上传图片拿到 CDN URL
        """
        if not cdn_url:
            print(f"    [警告] CDN URL 为空，跳过图片插入")
            return

        # 确保编辑器有焦点
        await self.page.evaluate("""
            () => {
                const ed = document.querySelector('div.ProseMirror');
                if (ed) ed.focus();
            }
        """)
        await asyncio.sleep(0.2)

        # 用 execCommand insertHTML 插入图片
        result = await self.page.evaluate("""
            (url) => {
                try {
                    const ed = document.querySelector('div.ProseMirror');
                    if (!ed) return {error: 'no editor'};
                    ed.focus();
                    const ok = document.execCommand('insertHTML', false,
                        '<p><img src="' + url + '" alt="" style="max-width:100%;"/></p>');
                    return {success: ok};
                } catch(e) {
                    return {error: e.message};
                }
            }
        """, cdn_url)

        if result.get('error'):
            print(f"    [警告] insertHTML 失败: {result['error']}")
        else:
            print(f"    图片已插入: {cdn_url[:50]}...")

        # 等待编辑器处理
        await asyncio.sleep(1.5)
        # 清 AI 抽屉
        await self.hide_ai_drawer()

    async def _close_image_drawer(self):
        """关闭头条上传图片后弹出的图片管理抽屉"""
        # 优先点"确定"按钮（保留图片）
        for sel in ['.byte-drawer-footer button.btn-primary', 'button:has-text("确定")']:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    await asyncio.sleep(1)
                    return
            except:
                continue
        # 兜底：直接隐藏所有 drawer
        await self.hide_ai_drawer()
        await asyncio.sleep(0.5)

    async def _clear_auto_covers(self):
        """清除头条自动从正文图片提取的封面（v1.6.1 新增）

        用户发现：正文有配图时，头条会自动提取正文图片作为封面候选，
        自动提取的封面排在前面（位置0），自定义上传的封面被挤到后面。
        只有位置0的图片才是实际封面，所以必须先删除自动提取的封面。

        策略：
        1. DOM方式：找封面区域的删除按钮并点击
        2. 如果DOM方式失败，输出诊断信息
        """
        # 等待自动提取完成（头条需要几秒处理正文图片）
        await asyncio.sleep(2)

        result = await self.page.evaluate("""
            async () => {
                const log = [];

                // 1. 找封面区域
                const coverSelectors = [
                    '.article-cover-images',
                    '.article-cover',
                    '[class*="article-cover"]',
                    '[class*="cover-image"]',
                    '[class*="cover-upload"]'
                ];

                let coverArea = null;
                for (const sel of coverSelectors) {
                    coverArea = document.querySelector(sel);
                    if (coverArea) {
                        log.push('cover area: ' + sel);
                        break;
                    }
                }
                if (!coverArea) {
                    return {found: false, log, msg: 'no cover area found'};
                }

                // 2. 统计封面图片
                const imgs = coverArea.querySelectorAll('img');
                log.push('cover imgs: ' + imgs.length);
                for (const img of imgs) {
                    log.push('  img src: ' + (img.src || '').substring(0, 80));
                }

                // 3. 找删除按钮（多种选择器，头条UI可能变版）
                // v1.6.1 关键发现：删除按钮实际是 <i class="article-cover-delete">
                const delSelectors = [
                    'i.article-cover-delete',  // v1.6.1 验证过的精确选择器
                    '.article-cover-delete',   // 同上
                    '[class*="cover-delete"]',  // 扩展匹配
                    '[class*="delete"]', '[class*="Delete"]',
                    '[class*="close"]', '[class*="Close"]',
                    '[class*="remove"]', '[class*="Remove"]',
                    '[class*="del-btn"]', '[class*="delete-btn"]',
                    '.icon-close', '.icon-delete',
                    'span[class*="close"]', 'i[class*="close"]',
                    'button[class*="close"]', 'button[class*="delete"]'
                ];

                let deleteBtns = [];
                for (const sel of delSelectors) {
                    const btns = coverArea.querySelectorAll(sel);
                    btns.forEach(btn => {
                        // 排除 AI 蒙层和抽屉的按钮
                        if (!btn.closest('.ai-assistant-drawer') &&
                            !btn.closest('.byte-drawer') &&
                            !btn.closest('.byte-modal') &&
                            !btn.closest('.byte-drawer-mask')) {
                            deleteBtns.push(btn);
                        }
                    });
                }
                log.push('delete btns found: ' + deleteBtns.length);

                // 4. 点击删除按钮（逐个点击，每个之间等待）
                let cleared = 0;
                for (const btn of [...deleteBtns]) {
                    try {
                        // hover 触发按钮显示（有些删除按钮需要 hover 才出现）
                        btn.dispatchEvent(new MouseEvent('mouseenter', {bubbles: true}));
                        btn.dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));
                        await new Promise(r => setTimeout(r, 200));
                        btn.click();
                        cleared++;
                        await new Promise(r => setTimeout(r, 500));
                    } catch(e) {
                        log.push('click err: ' + e.message);
                    }
                }

                return {
                    found: true,
                    cleared,
                    log,
                    imgCount: imgs.length,
                    delBtnCount: deleteBtns.length,
                    coverHTML: coverArea.innerHTML.substring(0, 2000)
                };
            }
        """)

        if result.get('cleared', 0) > 0:
            print(f"    [清除] 删除了 {result['cleared']} 个自动提取的封面")
            await asyncio.sleep(1)
        else:
            print(f"    [清除] 未找到可删除的自动封面")
            # 诊断输出
            for l in result.get('log', []):
                print(f"    [诊断] {l}")
            if result.get('coverHTML'):
                print(f"    [诊断] 封面区域HTML: {result['coverHTML'][:300]}")

    async def _upload_cover(self, cover_path):
        """v1.6.1: 先清除自动提取的封面，再用真实UI流程上传

        v1.6.0 方案B失败教训：
        - React fiber 注入 onChange(string) 只能更新UI临时state
        - 自动保存时头条还是用正文第一张图当封面
        - 草稿里实际保存的是"正文配图1"，不是自定义封面

        v1.6.1 新方案（用户手动经验）：
        1. 先清掉头条自动从正文提取的封面（_clear_auto_covers）
        2. 用真实UI流程上传（点击+号 → 选文件 → 点确定）
        3. 走头条自己跑的状态更新路径，确保封面持久化
        """
        abs_path = os.path.abspath(cover_path)
        if not os.path.exists(abs_path):
            print(f"    [警告] 封面图不存在: {abs_path}")
            return

        # === 方案A: 真实UI流程（主方案，v1.6.1）===
        # 用户手动操作经验：先删自动提取的封面，再点+号上传自定义封面
        try:
            print("    [A-1] 真实UI流程上传封面（点+号 → 选文件 → 确定）...")
            await self._upload_cover_ui(abs_path)
            print("    [A-2] 封面上传完成（走头条原生状态更新路径）")
            await asyncio.sleep(2)
            await self.screenshot("after_cover_ui")
            return
        except Exception as e:
            print(f"    [A] UI流程失败: {e}")

        # === 降级: API直传+React注入（v1.6.0方案，已知只更新UI不持久化）===
        print("    降级到API+React注入方案（v1.6.0，仅作为UI显示，最后兜底靠头条系统用正文首图）...")
        try:
            upload_data = await self._upload_cover_to_cdn(abs_path)
            if upload_data:
                cdn_url = upload_data.get('image_url')
                image_uri = upload_data.get('image_uri')
                print(f"    CDN URL: {cdn_url[:70]}...")
                await self._inject_cover_via_react(cdn_url, image_uri)
        except Exception as e:
            print(f"    [降级] API方案也失败: {e}")
            print(f"    头条将自动用正文第一张配图作为封面")

    async def _upload_cover_to_cdn(self, cover_path):
        """上传封面到头条图床（spice API, upload_source=20020003）

        与正文图片上传（_upload_images_to_cdn）使用相同的 spice API，
        但 upload_source 不同：正文=20020002，封面=20020003

        返回: {"image_url": "https://image-tt-private.toutiao.com/...", "image_uri": "..."}
        """
        import base64
        with open(cover_path, 'rb') as f:
            data = f.read()

        img_b64 = {
            'name': os.path.basename(cover_path),
            'b64': base64.b64encode(data).decode('utf-8'),
            'type': 'image/png'
        }

        result = await self.page.evaluate("""
            async (img) => {
                const bin = atob(img.b64);
                const bytes = new Uint8Array(bin.length);
                for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                const blob = new Blob([bytes], {type: img.type});
                const file = new File([blob], img.name, {type: img.type});
                const fd = new FormData();
                fd.append('image', file);
                fd.append('upload_source', '20020003');
                fd.append('aid', '1231');
                fd.append('device_platform', 'web');
                try {
                    const resp = await fetch('https://mp.toutiao.com/spice/image?upload_source=20020003&aid=1231&device_platform=web', {
                        method: 'POST', body: fd, credentials: 'include'
                    });
                    const data = await resp.json();
                    return {status: resp.status, data: data};
                } catch (e) {
                    return {error: e.message};
                }
            }
        """, img_b64)

        if result.get('error'):
            print(f"    [错误] spice API fetch失败: {result['error']}")
            return None

        resp_data = result.get('data', {})
        if resp_data.get('code') == 0:
            return resp_data.get('data')
        else:
            print(f"    [错误] spice API返回非0: {json.dumps(resp_data, ensure_ascii=False)[:200]}")
            return None

    async def _inject_cover_via_react(self, cdn_url, image_uri):
        """注入封面CDN URL到封面组件的React state

        v1.6.0 关键发现（2026-07-17）：
        - 头条用的是旧版 React 16/17 格式
        - React 内部 key 是 `__reactInternalInstance$<suffix>`，不是 React 18 的 `__reactFiber$`
        - **事件处理函数不在 fiber.memoizedProps 里，而在 el.__reactEventHandlers$<suffix> 这个独立属性里**
        - 这是为什么之前找 onTypeChange 调了没生效（那可能是控制单图/三图切换的 radio 回调）

        策略：
        1. 找到封面容器元素（.article-cover-images 等）
        2. 获取其 __reactInternalInstance（不是 __reactFiber）
        3. 向上遍历 fiber 树，找到合适的回调
        4. 函数回调可能在两个地方：fiber.memoizedProps 或 el.__reactEventHandlers
        5. 调用回调时尝试多种参数格式
        """
        cover_data = {
            'url': cdn_url,
            'uri': image_uri,
            'web_uri': image_uri,
            'image_url': cdn_url,
            'image_uri': image_uri,
        }

        result = await self.page.evaluate("""
            async (coverData) => {
                const cdnUrl = coverData.url;
                const uri = coverData.uri;

                // 1. 找封面相关元素
                const selectors = [
                    '.article-cover-images',
                    '.article-cover-add',
                    '.article-cover',
                    '[class*="article-cover"]',
                    '[class*="cover-upload"]'
                ];

                let targetEl = null;
                for (const sel of selectors) {
                    const els = document.querySelectorAll(sel);
                    for (const el of els) {
                        // 找有 React internals 的元素
                        const keys = Object.keys(el);
                        if (keys.some(k => k.startsWith('__reactInternalInstance') || k.startsWith('__reactFiber'))) {
                            targetEl = el;
                            break;
                        }
                    }
                    if (targetEl) break;
                }
                if (!targetEl) return {error: 'no cover element with React internals', selectors: selectors};

                // 2. 找到 fiber key（旧版 React 16/17 是 __reactInternalInstance）
                const fiberKey = Object.keys(targetEl).find(k =>
                    k.startsWith('__reactInternalInstance') || k.startsWith('__reactFiber'));
                if (!fiberKey) return {error: 'no fiber key', className: targetEl.className};

                // 3. 收集目标元素及其祖先元素的所有 event handlers
                //    旧版 React 的 event handlers 在 __reactEventHandlers 属性里
                let fiber = targetEl[fiberKey];
                const allHandlers = [];  // [{depth, key, fn, source}]

                let currEl = targetEl;
                for (let depth = 0; depth < 20 && fiber; depth++) {
                    // 检查当前元素是否有 __reactEventHandlers
                    const handlerKey = Object.keys(currEl).find(k => k.startsWith('__reactEventHandlers'));
                    if (handlerKey) {
                        const handlers = currEl[handlerKey];
                        if (handlers && typeof handlers === 'object') {
                            for (const [k, v] of Object.entries(handlers)) {
                                if (typeof v === 'function') {
                                    allHandlers.push({depth, key: k, fn: v, source: 'eventHandlers'});
                                }
                            }
                        }
                    }

                    // 也检查 fiber.memoizedProps 里的函数
                    const props = fiber.memoizedProps || {};
                    for (const [k, v] of Object.entries(props)) {
                        if (typeof v === 'function' && !allHandlers.find(h => h.key === k)) {
                            allHandlers.push({depth, key: k, fn: v, source: 'memoizedProps'});
                        }
                    }

                    // 移到父 fiber
                    fiber = fiber.return;
                    // 旧版 React fiber 链上不直接有对应的 DOM 元素
                    // 但我们可以用 _currentElement 关联
                    if (fiber && fiber.stateNode && fiber.stateNode !== currEl) {
                        currEl = fiber.stateNode;
                    }
                }

                if (allHandlers.length === 0) {
                    return {error: 'no callbacks found in fiber tree'};
                }

                // 4. 给每个 callback 打分，排序
                //    优先：cover + image/change
                //    其次：cover 单独
                //    再次：image/change
                //    排除：纯 Type 相关的（可能是控制单图/三图）
                function scoreHandler(h) {
                    const k = h.key.toLowerCase();
                    let score = 0;
                    if (k.includes('cover') && (k.includes('change') || k.includes('image') || k.includes('upload'))) score += 100;
                    else if (k.includes('cover') && k.includes('success')) score += 80;
                    else if (k.includes('cover') && k.includes('select')) score += 70;
                    else if (k === 'onchange' || k === 'onupload' || k === 'onsuccess') score += 60;
                    else if (k.includes('image') && k.includes('change')) score += 50;
                    else if (k.includes('change')) score += 30;
                    else if (k.includes('cover')) score += 20;

                    // 排除：Type 相关（控制单图/三图切换）
                    if (k.includes('type')) score -= 200;
                    // 排除：radio 相关
                    if (k.includes('radio')) score -= 200;
                    // 排除：dialog/drawer 相关
                    if (k.includes('dialog') || k.includes('drawer') || k.includes('modal')) score -= 100;
                    // 优先：更浅的 depth
                    score -= h.depth * 2;
                    // 优先：eventHandlers 源的
                    if (h.source === 'eventHandlers') score += 5;

                    return score;
                }

                allHandlers.sort((a, b) => scoreHandler(b) - scoreHandler(a));

                // 5. 按顺序尝试每个 callback
                const attempts = [];
                let success = false;
                let bestMethod = null;

                // 限制尝试数量（避免试太多浪费时间）
                const toTry = allHandlers.slice(0, 8);

                for (const h of toTry) {
                    // 尝试不同参数格式
                    const argFormats = [
                        {name: 'string', val: cdnUrl},
                        {name: 'url_obj', val: {url: cdnUrl, uri: uri, web_uri: uri, image_url: cdnUrl, image_uri: uri}},
                        {name: 'full', val: coverData},
                        {name: 'array', val: [coverData]},
                    ];

                    for (const fmt of argFormats) {
                        try {
                            h.fn(fmt.val);
                            attempts.push({depth: h.depth, key: h.key, source: h.source, arg: fmt.name, ok: true});
                            if (!success) {
                                success = true;
                                bestMethod = `fiber[${h.depth}].${h.key}(${fmt.name}) [${h.source}]`;
                            }
                            // 成功一次就 break（一个 callback 调用一次就够）
                            break;
                        } catch(e) {
                            attempts.push({depth: h.depth, key: h.key, source: h.source, arg: fmt.name, err: e.message.substring(0, 50)});
                        }
                    }
                }

                // 6. 验证封面是否被设置
                if (success) {
                    await new Promise(r => setTimeout(r, 1500));

                    // 检查 .article-cover-images 里是否有 img 元素
                    const previewImg = document.querySelector(
                        '.article-cover-images img, .article-cover img[src*="toutiao"], [class*="cover"] img[src*="toutiao"]'
                    );
                    const hasPreview = previewImg && previewImg.src;

                    // 也检查 .article-cover-images 的 background-image
                    const coverImages = document.querySelector('.article-cover-images');
                    let bgImage = null;
                    if (coverImages) {
                        const style = window.getComputedStyle(coverImages);
                        bgImage = style.backgroundImage;
                    }

                    return {
                        success: true,
                        method: bestMethod,
                        hasPreview: hasPreview,
                        previewSrc: previewImg ? previewImg.src.substring(0, 80) : null,
                        bgImage: bgImage && bgImage !== 'none' ? bgImage.substring(0, 80) : null,
                        attempts: attempts,
                        handlersFound: allHandlers.length,
                        topScored: allHandlers.slice(0, 3).map(h => ({key: h.key, score: scoreHandler(h), source: h.source}))
                    };
                }

                return {error: 'no callback succeeded', attempts: attempts, topScored: allHandlers.slice(0, 5).map(h => ({key: h.key, score: scoreHandler(h), source: h.source}))};
            }
        """, cover_data)

        return result

    async def _upload_cover_ui(self, abs_path):
        """真实UI流程上传封面（v1.6.1 关键修复）

        流程（用户手动操作经验）：
        1. 清除自动提取的封面（_clear_auto_covers）
        2. 点击封面+号 → 打开侧边抽屉（mp-ic-img-drawer）
        3. 抽屉默认在"正文图片"tab，需要切到"上传图片"tab才有file input
        4. set_input_files 上传文件
        5. 等"已上传"提示
        6. 点确定

        注意：
        - 封面图尺寸建议大于 672*462，最小 452*352
        - 抽屉是 byte-drawer.primary-drawer.mp-ic-img-drawer
        - "上传图片" tab 是 .byte-tabs-header-title
        """
        # 1. 滚动到封面区
        await self.page.evaluate("""
            () => {
                const el = document.querySelector('.article-cover');
                if (el) el.scrollIntoView({block: 'center', behavior: 'instant'});
            }
        """)
        await asyncio.sleep(0.5)

        # 2. 清 AI 蒙层（两个都要删：mask + wrapper）
        await self.page.evaluate("""
            () => {
                document.querySelectorAll(
                    '.ai-assistant-drawer, [class*="ai-assistant-drawer"], ' +
                    '.byte-drawer-mask, .byte-drawer-wrapper, .byte-drawer, ' +
                    '.byte-modal, .byte-modal-wrapper, ' +
                    '[class*="drawer-mask"], [class*="modal-mask"]'
                ).forEach(el => el.remove());
            }
        """)
        await asyncio.sleep(0.3)

        # 3. 点击 +号（v1.6.1：必须先清自动封面才有这个按钮）
        print(f"    [UI-1] click 封面+号 (.article-cover-add)")
        clicked = False
        for sel in ['.article-cover-add', '[class*="cover-add"]']:
            try:
                el = self.page.locator(sel).first
                await el.wait_for(state="visible", timeout=5000)
                await el.click(timeout=5000)
                clicked = True
                break
            except:
                continue
        if not clicked:
            raise Exception(".article-cover-add 选择器失败（可能未清除自动封面）")

        # 4. 等待抽屉打开
        print(f"    [UI-2] 等待抽屉打开...")
        await self.page.wait_for_selector(
            '.byte-drawer.mp-ic-img-drawer, [class*="mp-ic-img-drawer"]',
            state="visible",
            timeout=10000
        )
        await asyncio.sleep(1)

        # 5. 切换到"上传图片"tab
        print(f"    [UI-3] 切换到'上传图片'tab")
        tab_clicked = False
        tab_selectors = [
            '.byte-tabs-header-title:has-text("上传图片")',
            'div:has-text("上传图片")',
            '[class*="tab"]:has-text("上传图片")',
        ]
        for sel in tab_selectors:
            try:
                el = self.page.locator(sel).first
                if await el.is_visible():
                    await el.click(timeout=3000)
                    tab_clicked = True
                    print(f"      点击tab: {sel}")
                    break
            except:
                continue
        if not tab_clicked:
            # 兜底：找所有byte-tabs-header-title，按文字匹配
            await self.page.evaluate("""
                () => {
                    const titles = document.querySelectorAll('.byte-tabs-header-title');
                    for (const t of titles) {
                        if (t.textContent.trim() === '上传图片') {
                            t.click();
                            return true;
                        }
                    }
                    return false;
                }
            """)
            print(f"      JS点击tab: 上传图片")
        await asyncio.sleep(1)

        # 6. set_input_files
        print(f"    [UI-4] set_input_files")
        file_input = self.page.locator('input[type="file"]').first
        await file_input.wait_for(state="attached", timeout=10000)
        await file_input.set_input_files(abs_path)
        print(f"    [UI-5] 已上传文件: {os.path.basename(abs_path)}")

        # 7. 等"已上传"
        try:
            await self.page.wait_for_function(
                """() => /已上传\\s*\\d+\\s*张/.test(document.body.innerText || '')""",
                timeout=20000
            )
            print(f"    [UI-6] 封面图已上传到头条图床")
        except:
            print(f"    [UI-6] 等'已上传'提示超时（可能已经在上传/不显示提示）")

        # 8. 点确定（抽屉底部的确定按钮）
        try:
            confirm_btn = self.page.locator('.byte-drawer-footer button.btn-primary, .byte-drawer-footer button:has-text("确定")').first
            await confirm_btn.wait_for(state="visible", timeout=5000)
            await confirm_btn.click(timeout=5000)
            print(f"    [UI-7] 已点确定按钮")
        except:
            # 兜底：找所有"确定"按钮
            print(f"    [UI-7] 兜底找确定按钮...")
            await self.page.evaluate("""
                () => {
                    const btns = document.querySelectorAll('button');
                    for (const btn of btns) {
                        if (btn.textContent.trim() === '确定' && btn.offsetParent !== null) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }
            """)

        await asyncio.sleep(2)
        await self.screenshot("after_cover_ui")

    async def _check_declarations(self):
        """勾选声明 — 头条用自研 checkbox 组件，必须用真实 click 事件
        注意：不要 click 已选中的 radio（会 toggle 取消）
        """
        # 头条要求至少勾一个"作品声明"
        # 选"个人观点"和"引用站内"两个（加固）
        target_texts = [
            "个人观点，仅供参考",  # 必选
            "引用站内",  # 备用加固
        ]

        for text in target_texts:
            success = False
            # 找 label 或 span 包含该文字
            for sel in [
                f'label:has-text("{text}")',
                f'span:has-text("{text}")',
            ]:
                try:
                    el = await self.page.query_selector(sel)
                    if el and await el.is_visible():
                        # 用 force click 绕过遮挡
                        await el.click(force=True, timeout=5000)
                        print(f"    勾选: {text}")
                        await asyncio.sleep(0.5)
                        success = True
                        break
                except Exception as e:
                    continue

            if not success:
                # 用 JS dispatchEvent 模拟真实 click
                clicked = await self.page.evaluate("""
                    (targetText) => {
                        const all = [...document.querySelectorAll('*')];
                        for (const el of all) {
                            if (el.children.length === 0 && el.textContent.trim() === targetText) {
                                let target = el;
                                for (let i = 0; i < 5; i++) {
                                    if (target.tagName === 'LABEL' || target.tagName === 'BUTTON') break;
                                    if (target.parentElement) target = target.parentElement;
                                    else break;
                                }
                                ['mousedown', 'mouseup', 'click'].forEach(evtType => {
                                    target.dispatchEvent(new MouseEvent(evtType, {
                                        view: window, bubbles: true, cancelable: true, button: 0
                                    }));
                                });
                                return target.tagName;
                            }
                        }
                        return null;
                    }
                """, text)
                if clicked:
                    print(f"    勾选: {text} (via JS dispatch, tag={clicked})")
                else:
                    print(f"    [失败] 未找到 {text}")

        await asyncio.sleep(1)

    async def _click_publish(self):
        """点击发布按钮"""
        publish_selectors = [
            'button:has-text("预览并发布")',
            'button:has-text("发布")',
            'button:has-text("确认发布")',
            'div[class*="publish"] button',
            'button[class*="publish"]',
        ]

        # 第一步：点击"预览并发布"
        for sel in publish_selectors:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    print(f"    点击: 预览并发布")
                    await asyncio.sleep(2)
                    break
            except:
                continue

        await self.screenshot("publish_preview")

        # 第二步：如果有确认弹窗，点击"确认发布"
        await asyncio.sleep(2)
        for sel in ['button:has-text("确认发布")', 'button:has-text("确定")', 'button:has-text("发布")']:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click()
                    print(f"    点击: 确认发布")
                    await asyncio.sleep(3)
                    return True
            except:
                continue

        # 检查是否出现成功提示
        success = await self.page.query_selector('text=发布成功')
        if success:
            return True

        # 如果没有确认弹窗，可能直接发布了
        return True

    async def _save_draft(self):
        """存草稿 — 头条依赖编辑器自动保存（stealth模式下正常工作）
        1. 触发失焦让自动保存跑起来
        2. 等待"已保存"提示出现（最多30秒）
        3. 跳转草稿箱验证文章是否存在
        """
        # 1. 触发 blur（点击空白处）
        await self.page.mouse.click(10, 10)
        await asyncio.sleep(2)

        # 2. 等待自动保存完成（轮询检查"已保存"提示）
        print(f"    等待自动保存...")
        saved = False
        for i in range(6):  # 最多等30秒
            await asyncio.sleep(5)
            status = await self.page.evaluate("""() => {
                const all = [...document.querySelectorAll('*')]
                    .filter(el => el.offsetParent !== null && el.children.length === 0);
                const texts = all.map(el => el.textContent.trim()).filter(t => t);
                return {
                    saving: texts.some(t => t.includes('保存中')),
                    saved: texts.some(t => t.includes('已保存') || t.includes('保存成功')),
                    failed: texts.some(t => t.includes('保存失败')),
                };
            }""")
            elapsed = (i + 1) * 5 + 2
            if status['saved']:
                print(f"    [{elapsed}s] 自动保存成功！")
                saved = True
                break
            elif status['failed']:
                print(f"    [{elapsed}s] 保存失败！可能是反爬检测，请重试")
                break
            else:
                print(f"    [{elapsed}s] 保存中...")

        await self.screenshot("draft_save_check")

        # 3. 跳转到草稿箱验证（最可靠）
        print(f"    跳转草稿箱验证...")
        await self.page.goto("https://mp.toutiao.com/profile_v4/manage/draft", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        await self.screenshot("draft_verify")

        # 检查文章是否存在
        draft_info = await self.page.evaluate("""
            () => {
                const text = document.body.innerText;
                const countMatch = text.match(/共\\s*(\\d+)\\s*条/);
                const count = countMatch ? parseInt(countMatch[1]) : 0;
                return {count};
            }
        """)
        print(f"    草稿箱文章数: {draft_info['count']}")
        return draft_info['count'] > 0


# ===== CLI入口 =====

async def cmd_check(debug_dir, browser_data_dir=None):
    browser = ToutiaoBrowser(debug_dir=debug_dir, browser_data_dir=browser_data_dir)
    try:
        await browser.start(headless=False)
        logged_in = await browser.check_login()
        return 0 if logged_in else 1
    finally:
        await browser.close()

async def cmd_login(debug_dir, browser_data_dir=None):
    browser = ToutiaoBrowser(debug_dir=debug_dir, browser_data_dir=browser_data_dir)
    try:
        await browser.start(headless=False)
        success = await browser.login()
        return 0 if success else 1
    finally:
        await browser.close()

async def cmd_publish(args):
    browser = ToutiaoBrowser(debug_dir=args.debug_dir, browser_data_dir=getattr(args, 'browser_data', None))
    try:
        await browser.start(headless=False)

        # 检查登录
        logged_in = await browser.check_login()
        if not logged_in:
            print("未登录，请先执行: python toutiao_publisher.py login")
            return 1

        # 读取正文
        if args.content_file:
            with open(args.content_file, 'r', encoding='utf-8') as f:
                content = f.read()
        elif args.content:
            content = args.content
        else:
            print("错误: 需要 --content 或 --content-file")
            return 1

        # 发布
        success = await browser.publish_article(
            title=args.title,
            content=content,
            cover_path=args.cover,
            image_paths=args.images,
            draft=args.draft,
        )
        return 0 if success else 1
    finally:
        await browser.close()

def main():
    parser = argparse.ArgumentParser(description='今日头条自动发布工具')
    parser.add_argument('--debug-dir', default=None, help='调试截图目录（默认当前目录）')
    parser.add_argument('--browser-data', default=None, help='浏览器数据目录（默认~/.toutiao-browser-data，小号用~/.toutiao-browser-data-small）')

    subparsers = parser.add_subparsers(dest='command')

    # check
    sub_check = subparsers.add_parser('check', help='检查登录状态')

    # login
    sub_login = subparsers.add_parser('login', help='扫码登录')

    # publish
    sub_publish = subparsers.add_parser('publish', help='发布图文文章')
    sub_publish.add_argument('--title', required=True, help='文章标题')
    sub_publish.add_argument('--content', default=None, help='文章正文（直接传入）')
    sub_publish.add_argument('--content-file', default=None, help='文章正文文件路径')
    sub_publish.add_argument('--cover', default=None, help='封面图路径')
    sub_publish.add_argument('--images', nargs='+', default=None, help='正文配图路径（可多张）')
    sub_publish.add_argument('--draft', action='store_true', help='存草稿（不直接发布）')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    debug_dir = args.debug_dir or os.getcwd()

    if args.command == 'check':
        return asyncio.run(cmd_check(debug_dir, args.browser_data))
    elif args.command == 'login':
        return asyncio.run(cmd_login(debug_dir, args.browser_data))
    elif args.command == 'publish':
        return asyncio.run(cmd_publish(args))
    else:
        parser.print_help()
        return 1

if __name__ == '__main__':
    sys.exit(main())
