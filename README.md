# OptikLink 每日自动登录脚本

自动登录 [OptikLink](https://optiklink.net) 面板，通过注入 Discord Token 完成 OAuth2 授权，并通过 WxPusher 推送登录结果和套餐到期提醒。

## 功能特性

- 使用 **CloakBrowser**（源码级指纹伪装）模拟真实浏览器行为
- 通过 **Xray** 代理访问，支持 SOCKS5 代理注入
- 自动注入 **Discord Token** 完成 OAuth2 授权，无需手动操作
- 自动处理 **Cloudflare / Cookie 弹窗 / Google Vignette 广告遮罩**
- 登录成功后读取套餐到期日期，临近到期时推送**紧急提醒**
- 截图**始终保存**，每个关键步骤自动截图
- 录屏**手动可选**，默认关闭，手动触发时可按需开启
- 通过 **WxPusher** 推送每日登录报告到微信
- **GitHub Actions** 每天定时自动运行，无需本地部署

## 目录结构

```
optiklink-main/
├── optiklink_cloakbrowser.py         # 主脚本
└── .github/
    └── workflows/
        └── optiklink.yml             # GitHub Actions 工作流
```

## 环境变量 / Secrets

在 GitHub 仓库 **Settings → Secrets and variables → Actions → New repository secret** 中添加以下配置：

| 变量名 | 必填 | 说明 |
|--------|------|------|
| `DISCORD_TOKEN` | ✅ | Discord 账号的 Token |
| `WXPUSHER_TOKEN` | ✅ | WxPusher AppToken |
| `WXPUSHER_UID` | ✅ | WxPusher 接收用户 UID |
| `V2RAY_CONFIG` | ✅ | Xray/V2Ray 代理配置（JSON 内容） |
| `EXPIRE_DATE` | ❌ | 套餐到期日期，格式 `DD.MM.YYYY`，用于到期提醒 |

> `EXPIRE_DATE` 不填时脚本仍可正常运行，但推送报告中到期信息会显示"未知"。

## 快速开始

### 方式一：GitHub Actions（推荐）

1. Fork 或克隆本仓库到你的 GitHub 账号
2. 在仓库 Secrets 中配置上方所有必填变量
3. 工作流默认每天 UTC 01:00（北京时间 09:00）自动运行
4. 也可在 **Actions** 页面手动触发，手动触发时可选择是否开启录屏

### 方式二：本地运行

**安装依赖：**

```bash
pip install "cloakbrowser[geoip]" Pillow
python -c "from cloakbrowser import ensure_binary; ensure_binary()"
```

**配置环境变量：**

```bash
export DISCORD_TOKEN="your_discord_token"
export WXPUSHER_TOKEN="your_wxpusher_token"
export WXPUSHER_UID="your_wxpusher_uid"
export EXPIRE_DATE="12.06.2026"        # 可选
export PROXY_URL="socks5://127.0.0.1:10808"   # 可选，默认值
export ENABLE_SCREENRECORD="false"     # 可选，true=开启录屏
```

**运行脚本：**

```bash
python optiklink_cloakbrowser.py
```

## GitHub Actions 工作流说明

工作流文件位于 `.github/workflows/optiklink.yml`，运行步骤如下：

1. 安装系统依赖（Xvfb、ffmpeg、字体、Chromium 依赖库等）
2. 安装 Python 依赖（`cloakbrowser[geoip]`、`Pillow`）
3. 下载 Xray 并启动代理（SOCKS5 10808 端口）
4. 启动虚拟显示 Xvfb `:99`，等待就绪后执行主脚本（超时 300 秒）
5. 上传截图为 Artifact（始终执行，保留 3 天）
6. 上传录屏为 Artifact（仅录屏开启时执行，保留 3 天）
7. 清理旧 workflow 运行记录，仅保留最新 2 条

```yaml
on:
  schedule:
    - cron: "0 1 * * *"    # 每天 UTC 01:00，定时触发默认不录屏
  workflow_dispatch:         # 手动触发，可选择是否录屏
    inputs:
      enable_recording:
        description: '是否开启录屏（true=录屏 / false=不录屏）'
        default: 'false'
        type: choice
        options: ['false', 'true']
```

### 录屏开关

| 触发方式 | 录屏默认值 | 说明 |
|----------|-----------|------|
| 定时触发（schedule） | `false` | 自动运行，不录屏 |
| 手动触发（workflow_dispatch） | `false` | 在 Actions 页面触发时可手动选择 `true` 开启录屏 |

手动触发路径：**Actions → OptikLink 每日自动登录 → Run workflow → 选择 `enable_recording`**

## 脚本执行流程

```
启动 CloakBrowser（headless=False，渲染到 Xvfb :99）
       │
       ▼
  打开登录页 /auth
  清理 Cookie 弹窗 / 广告遮罩
       │
       ▼
  点击 Discord 登录按钮
  处理 Google Vignette 广告弹窗（如有）
       │
       ▼
  等待跳转到 discord.com
  注入 Discord Token → 刷新页面
       │
       ▼
  处理 OAuth2 授权页（自动滚动 + 点击授权）
       │
       ▼
  等待跳回 optiklink.net
  读取 Dashboard（用户名、到期日、服务器数）
       │
       ▼
  生成推送报告（含到期预警）
  通过 WxPusher 推送到微信
```

## WxPusher 推送说明

每次运行后会推送一条 Markdown 格式的报告，包含：

| 字段 | 说明 |
|------|------|
| 状态 | ✅ 登录成功 / ❌ 登录失败 |
| 用户名 | 从页面解析 |
| 运行服务器 | 当前运行中的服务器数量 |
| 服务到期 | 套餐到期日期 |
| 剩余天数 | 距到期天数 |
| 执行时间 | UTC 时间 |

**到期预警规则：**

| 剩余天数 | 推送级别 |
|----------|---------|
| > 7 天 | 正常报告 |
| ≤ 7 天 | ⚠️ 警告：请尽快续期 |
| ≤ 3 天 | 🚨 紧急：立即续期 |

## 调试

每次运行会在 `./screenshots/` 目录下保存关键步骤截图，命名格式：

```
YYYYMMDD_HHMMSS_<步骤名>.png
```

截图步骤包括：`01_auth_page` → `02_discord_page` → `03_token_injected` → `04_after_oauth` → `05_home_page`，以及失败时的 `99_error`。

录屏开启时，视频保存至 `./recordings/` 目录，文件格式为 `.mp4`（ffmpeg x11grab 录制）。

GitHub Actions 运行结束后，截图和录屏会作为独立 Artifact 上传，可在对应 workflow 运行页面下载查看（保留 3 天）。

## 注意事项

- `headless` 必须设为 `False`：录屏依赖 ffmpeg 从 Xvfb 抓屏，`headless=True` 时浏览器不渲染到显示器，录屏文件会是 0 字节
- Xvfb 分辨率和 `VIEWPORT_H` 均设为 `754`（偶数）：h264 编码器要求宽高必须能被 2 整除，奇数高度会导致 ffmpeg 编码失败
- 本脚本仅用于自动化个人账号的每日签到，请勿用于批量账号或商业用途

## 依赖

| 依赖 | 说明 |
|------|------|
| `cloakbrowser[geoip]` | 指纹伪装浏览器，基于 Playwright |
| `Pillow` | 图像处理库（录屏后备方案） |
| `Xray-core` | 代理工具，支持 V2Ray/VLESS/VMess 等协议 |
| Python ≥ 3.12 | 脚本运行环境 |
| Xvfb | GitHub Actions 虚拟显示（本地有桌面则不需要） |
| ffmpeg | 可选，用于录屏（x11grab 模式） |
