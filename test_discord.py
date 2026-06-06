import os
import requests
import json

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")

headers = {
    "Authorization": DISCORD_TOKEN,
    "User-Agent": "Mozilla/5.0"
}

# 测试参数
params = {
    "client_id": "933437142254887052",
    "redirect_uri": "https://optiklink.com/login",
    "response_type": "code",
    "scope": "guilds guilds.join identify email",
    "prompt": "none"
}

print("正在请求 Discord API...")
r = requests.get(
    "https://discord.com/api/v10/oauth2/authorize",
    params=params,
    headers=headers,
    allow_redirects=False
)

print(f"状态码: {r.status_code}")
print(f"响应头 Content-Type: {r.headers.get('Content-Type')}")

try:
    data = r.json()
    print(f"\n完整响应 JSON:")
    print(json.dumps(data, indent=2, ensure_ascii=False))
except:
    print(f"\n原始响应: {r.text[:500]}")
