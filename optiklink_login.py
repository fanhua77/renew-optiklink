"""
OptikLink 每日自动登录脚本 v4 (CloakBrowser版)
原理：用 CloakBrowser 打开页面，注入 Discord Token 完成 OAuth2 授权
参考：natfreecloud_renew_CloakBrowser / FreezeHost
"""

import os
import re
import sys
import json
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# 配置（全部从 GitHub Secrets / 环境变量读取）
# ─────────────────────────────────────────────────────────────
DISCORD_TOKEN  = os.environ["DISCORD_TOKEN"]
WXPUSHER_TOKEN = os.environ["WXPUSHER_TOKEN"]
WXPUSHER_UID   = os.environ["WXPUSHER_UID"]
EXPIRE_DATE    = os.environ.get("EXPIRE_DATE", "")
PROXY_URL      = os.environ.get("PROXY_URL", "socks5://127.0.0.1:10808")
ENABLE_SCREENSHOT = os.environ.get("ENABLE_SCREENSHOT", "false").lower() == "true"

BASE_URL   = "https://optiklink.net"
AUTH_URL   = f"{BASE_URL}/auth"
HOME_URL   = f"{BASE_URL}/home"

# ─────────────────────────────────────────────────────────────
# 截图
# ─────────────────────────────────────────────────────────────
SCREENSHOT_DIR = Path("./screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)

def take_screenshot(page, name: str):
    if not ENABLE_SCREENSHOT:
        return
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = str(SCREENSHOT_DIR / f"{ts}_{name}.png")
        page.screenshot(path=path, full_page=True)
        log.info(f"📸 截图已保存: {path}")
    except Exception as e:
        log.warning(f"截图失败: {e}")

# ─────────────────────────────────────────────────────────────
# WxPusher 推送
# ─────────────────────────────────────────────────────────────
def wxpush(title: str, content: str):
    import urllib.request
    payload = json.dumps({
        "appToken":    WXPUSHER_TOKEN,
        "content":     content,
        "summary":     title,
        "contentType": 3,
        "uids":        [WXPUSHER_UID],
    }).encode()
    try:
        req = urllib.request.Request(
            "https://wxpusher.zjiecode.com/api/send/message",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if result.get("success"):
                log.info("📨 WxPusher 推送成功")
            else:
                log.warning(f"📨 WxPusher 推送失败: {result}")
    except Exception as e:
        log.warning(f"📨 WxPusher 推送异常: {e}")

# ─────────────────────────────────────────────────────────────
# Discord Token 注入工具
# ─────────────────────────────────────────────────────────────
def inject_discord_token(page, token: str):
    """向 Discord 页面注入 Token（localStorage），然后刷新"""
    page.evaluate("""(token) => {
        const f = document.createElement('iframe');
        f.style.display = 'none';
        document.body.appendChild(f);
        f.contentWindow.localStorage.setItem('token', '"' + token + '"');
        try { localStorage.setItem('token', '"' + token + '"'); } catch(e) {}
        document.body.removeChild(f);
    }""", token)
    log.info("Token 已注入 localStorage")

# ─────────────────────────────────────────────────────────────
# Discord OAuth 授权页处理（参考 FreezeHost）
# 自动向下滚动直到授权按钮可见，然后点击
# ─────────────────────────────────────────────────────────────
def handle_oauth_page(page):
    log.info("处理 Discord OAuth 授权页...")
    page.wait_for_timeout(2000)

    # 等待授权按钮出现（最多等 30 次 × 0.8s）
    for _ in range(30):
        if "discord.com" not in page.url:
            log.info("已离开 Discord，OAuth 完成")
            return

        btn_text = ""
        try:
            for sel in ['button[type="submit"]', 'div[class*="footer"] button', 'button[class*="primary"]']:
                btn = page.locator(sel).last
                if btn.is_visible():
                    btn_text = btn.inner_text().strip().lower()
                    break
        except Exception:
            pass

        if "authorize" in btn_text or "授权" in btn_text:
            break

        # 滚动页面让授权按钮出现
        page.evaluate("""() => {
            const sels = ['[class*="scroller"]','[class*="oauth2"]','[class*="permissionList"]',
                '[class*="content"] [class*="scroll"]','[class*="listScroller"]'];
            for (const sel of sels) {
                for (const el of document.querySelectorAll(sel)) {
                    const s = getComputedStyle(el);
                    if (el.scrollHeight > el.clientHeight &&
                        ['auto','scroll'].some(v => s.overflowY === v || s.overflow === v))
                        { el.scrollTop = el.scrollHeight; }
                }
            }
            scrollTo(0, document.body.scrollHeight);
        }""")
        page.wait_for_timeout(800)

    # 点击授权按钮
    for _ in range(10):
        if "discord.com" not in page.url:
            return
        for sel in [
            'button:has-text("Authorize")',
            'button:has-text("授权")',
            'button[type="submit"]',
            'div[class*="footer"] button',
            'button[class*="primary"]',
        ]:
            try:
                btn = page.locator(sel).last
                if not btn.is_visible():
                    continue
                text = btn.inner_text().strip()
                if any(k in text.lower() for k in ("取消", "cancel", "deny")):
                    continue
                if btn.is_disabled():
                    page.wait_for_timeout(1000)
                    break
                log.info(f"点击授权按钮: {text}")
                btn.click()
                page.wait_for_timeout(2000)
                if "discord.com" not in page.url:
                    return
                break
            except Exception:
                continue
        page.wait_for_timeout(1500)

# ─────────────────────────────────────────────────────────────
# 主登录流程
# ─────────────────────────────────────────────────────────────
def do_login(page) -> bool:
    """
    1. 打开 /auth 页面
    2. 点击 Discord 登录按钮
    3. 到达 discord.com 后注入 Token 并刷新
    4. 处理 OAuth 授权页
    5. 等待跳回 optiklink.net/home
    """
    log.info(f"[A] 打开登录页: {AUTH_URL}")
    try:
        page.goto(AUTH_URL, timeout=30000, wait_until="domcontentloaded")
    except Exception as e:
        log.warning(f"goto 超时: {e}")
    take_screenshot(page, "01_auth_page")

    # 点击 Discord 登录按钮
    log.info("[B] 点击 Discord 登录按钮...")
    try:
        # OptikLink 的按钮文字是 "DISCORD" 或包含 discord
        for sel in [
            'a:has-text("DISCORD")',
            'button:has-text("DISCORD")',
            'a[href*="discord"]',
            'a[href*="oauth2"]',
            '.discord-btn',
            'a:has-text("Sign in with Discord")',
            'a:has-text("Login with Discord")',
        ]:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=2000):
                    btn.click()
                    log.info(f"已点击: {sel}")
                    break
            except Exception:
                continue
    except Exception as e:
        log.warning(f"点击登录按钮失败: {e}")
        take_screenshot(page, "01b_click_fail")
        return False

    # 等待跳转到 discord.com
    log.info("[C] 等待跳转到 Discord...")
    try:
        page.wait_for_url(re.compile(r"discord\.com"), timeout=15000)
        log.info(f"已到达 Discord: {page.url}")
    except Exception as e:
        log.warning(f"等待 Discord 超时: {e}，当前URL: {page.url}")
        take_screenshot(page, "02_discord_timeout")
        return False

    take_screenshot(page, "02_discord_page")

    # 注入 Token
    log.info("[D] 注入 Discord Token...")
    inject_discord_token(page, DISCORD_TOKEN)
    page.reload(wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    # 检查 Token 注入是否成功
    if re.search(r"discord\.com/login", page.url):
        log.error("Token 注入失败，仍在登录页")
        take_screenshot(page, "03_token_failed")
        return False
    log.info("Token 注入成功")
    take_screenshot(page, "03_token_injected")

    # 处理 OAuth 授权页
    try:
        page.wait_for_url(re.compile(r"discord\.com/oauth2/authorize"), timeout=6000)
        page.wait_for_timeout(2000)
        if "discord.com" in page.url:
            handle_oauth_page(page)
    except Exception:
        # 可能已经自动跳过了授权页
        if "discord.com" in page.url:
            handle_oauth_page(page)

    take_screenshot(page, "04_after_oauth")

    # 等待跳回 optiklink.net
    log.info("[E] 等待跳回 OptikLink...")
    try:
        page.wait_for_url(re.compile(r"optiklink\.net"), timeout=20000)
        log.info(f"已跳回: {page.url}")
    except Exception as e:
        log.warning(f"等待跳回超时: {e}，当前URL: {page.url}")
        take_screenshot(page, "05_redirect_timeout")
        return False

    # 确保到达 /home
    if "/home" not in page.url:
        log.info("跳转到 /home ...")
        try:
            page.goto(HOME_URL, timeout=20000, wait_until="domcontentloaded")
        except Exception as e:
            log.warning(f"goto /home 超时: {e}")

    take_screenshot(page, "05_home_page")
    return True

# ─────────────────────────────────────────────────────────────
# 读取 Dashboard 信息
# ─────────────────────────────────────────────────────────────
def read_dashboard(page) -> dict:
    log.info("[F] 读取 Dashboard 信息...")
    info = {
        "logged_in":      False,
        "username":       "N/A",
        "expire_date":    EXPIRE_DATE,
        "running_servers": "N/A",
    }

    try:
        page.wait_for_timeout(3000)
        html = page.content()
        text = page.inner_text("body")
    except Exception as e:
        log.warning(f"读取页面失败: {e}")
        return info

    # 判断是否登录
    if "dashboard" in page.url.lower() or "DASHBOARD" in html.upper() or "My Plan" in text:
        info["logged_in"] = True
        log.info("✅ 确认已登录")
    else:
        log.warning(f"当前URL: {page.url}，未检测到 Dashboard")
        return info

    # 用户名
    for pat in [
        r'Welcome\s+(?:<[^>]+>)?(\w+)(?:<[^>]+>)?\s+to',
        r'"username"\s*:\s*"([^"]+)"',
        r'simeter\w+',
        r'Hello,?\s+(\w+)',
    ]:
        m = re.search(pat, html, re.I)
        if m:
            info["username"] = m.group(1) if m.lastindex else m.group(0)
            break

    # 到期日期（优先从页面文字提取）
    for pat in [
        r'(\d{2}\.\d{2}\.\d{4})',
        r'date:\s*(\d{2}\.\d{2}\.\d{4})',
        r'expire[^:]*:\s*(\d{2}\.\d{2}\.\d{4})',
    ]:
        m = re.search(pat, text, re.I)
        if m:
            info["expire_date"] = m.group(1)
            break

    # 运行服务器数
    m2 = re.search(r'(\d+)\s*(?:running\s*)?servers?', text, re.I)
    if m2:
        info["running_servers"] = m2.group(1)

    log.info(f"Dashboard 信息: {info}")
    return info

# ─────────────────────────────────────────────────────────────
# 构建推送消息
# ─────────────────────────────────────────────────────────────
def build_message(info: dict) -> tuple[str, str]:
    now_utc = datetime.now(timezone.utc)
    status = "✅ 登录成功" if info["logged_in"] else "❌ 登录失败"

    days_left = -1
    if info.get("expire_date"):
        try:
            expire_dt = datetime.strptime(info["expire_date"], "%d.%m.%Y").replace(tzinfo=timezone.utc)
            days_left = (expire_dt - now_utc).days
        except Exception:
            pass

    if days_left == -1:
        warning = "\n\n> ⚠️ 未能获取到期日期，请手动检查"
        title = f"OptikLink 签到 | {status} | 到期日期未知"
    elif days_left <= 3:
        warning = f"\n\n---\n## 🚨 紧急：服务即将到期！\n\n> **距到期仅剩 {days_left} 天，请立即续期！**"
        title = f"🚨 OptikLink 签到 | 紧急：{days_left}天后到期！"
    elif days_left <= 7:
        warning = f"\n\n---\n## ⚠️ 服务即将到期\n\n> 距到期还剩 **{days_left}** 天，请尽快续期。"
        title = f"⚠️ OptikLink 签到 | 警告：{days_left}天后到期"
    else:
        warning = f"\n\n> 📅 服务到期还剩 **{days_left}** 天" if days_left <= 30 else ""
        title = f"OptikLink 签到 | {status}"

    content = f"""## OptikLink 每日自动登录报告

| 项目 | 内容 |
|------|------|
| 状态 | {status} |
| 用户名 | {info['username']} |
| 运行服务器 | {info['running_servers']} 个 |
| 服务到期 | {info['expire_date']} |
| 剩余天数 | {days_left if days_left >= 0 else '未知'} 天 |
| 执行时间 | {now_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC |
{warning}
"""
    return title, content

# ─────────────────────────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────────────────────────
def main():
    log.info("=" * 55)
    log.info("  OptikLink 自动登录脚本 v4 (CloakBrowser)")
    log.info("=" * 55)

    from cloakbrowser import launch

    log.info("启动 CloakBrowser...")
    browser = launch(
        headless=True,
        humanize=True,
        proxy=PROXY_URL,
        geoip=True,
    )
    page = browser.new_page()

    try:
        success = do_login(page)

        if not success:
            wxpush(
                "OptikLink 签到 ❌ 失败",
                f"## 执行失败\n\n**错误：** 登录流程未完成，请查看截图\n\n"
                f"时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
            )
            sys.exit(1)

        info = read_dashboard(page)
        title, content = build_message(info)
        wxpush(title, content)

        if not info["logged_in"]:
            log.error("Dashboard 未出现登录状态")
            sys.exit(1)

        log.info("✅ 全部完成！")

    except Exception as e:
        log.exception(e)
        take_screenshot(page, "99_error")
        wxpush(
            "OptikLink 签到 ❌ 异常",
            f"## 执行异常\n\n```\n{e}\n```\n\n"
            f"时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
        )
        sys.exit(1)
    finally:
        time.sleep(3)
        browser.close()
        log.info("浏览器已关闭")


if __name__ == "__main__":
    main()
