#!/usr/bin/env python3
"""
从 VLESS 链接生成 Xray 配置文件
"""

import urllib.parse
import json
import os
import sys

def parse_vless(vless_url):
    """解析 VLESS 链接"""
    if not vless_url or not vless_url.startswith('vless://'):
        print("❌ 无效的 VLESS 链接", file=sys.stderr)
        sys.exit(1)
    
    # 移除协议
    url = vless_url[8:]
    
    # 提取节点名称
    if '#' in url:
        url, name = url.split('#', 1)
        name = urllib.parse.unquote(name)
    else:
        name = "VLESS-Node"
    
    # 分离 UUID 和地址
    if '@' not in url:
        print("❌ 缺少 @ 分隔符", file=sys.stderr)
        sys.exit(1)
    uuid, rest = url.split('@', 1)
    
    # 分离地址端口和参数
    if '?' in rest:
        address_port, query = rest.split('?', 1)
        params = dict(urllib.parse.parse_qsl(query))
    else:
        address_port = rest
        params = {}
    
    # 分离地址和端口
    if ':' in address_port:
        address, port = address_port.split(':', 1)
        port = int(port)
    else:
        address = address_port
        port = 443
    
    return {
        "name": name,
        "uuid": uuid,
        "address": address,
        "port": port,
        "encryption": params.get('encryption', 'none'),
        "security": params.get('security', ''),
        "network": params.get('type', 'tcp'),
        "ws_path": params.get('path', '/'),
        "ws_host": params.get('host', address),
        "sni": params.get('sni', address),
        "fingerprint": params.get('fp', 'chrome'),
        "flow": params.get('flow', ''),
        "pbk": params.get('pbk', ''),
        "sid": params.get('sid', ''),
        "raw": vless_url
    }

def generate_xray_config(vless_url):
    """生成 Xray 配置"""
    node = parse_vless(vless_url)
    
    config = {
        "log": {
            "loglevel": "warning"
        },
        "inbounds": [
            {
                "port": 10808,
                "protocol": "socks",
                "settings": {
                    "auth": "noauth",
                    "udp": True
                },
                "streamSettings": {
                    "network": "tcp"
                }
            }
        ],
        "outbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": node["address"],
                            "port": node["port"],
                            "users": [
                                {
                                    "id": node["uuid"],
                                    "encryption": node["encryption"]
                                }
                            ]
                        }
                    ]
                },
                "streamSettings": {
                    "network": node["network"],
                    "security": node["security"]
                }
            }
        ]
    }
    
    # 添加 flow
    if node["flow"]:
        config["outbounds"][0]["settings"]["vnext"][0]["users"][0]["flow"] = node["flow"]
    
    # WebSocket 配置
    if node["network"] == "ws":
        config["outbounds"][0]["streamSettings"]["wsSettings"] = {
            "path": node["ws_path"],
            "headers": {
                "Host": node["ws_host"]
            }
        }
    elif node["network"] == "grpc":
        config["outbounds"][0]["streamSettings"]["grpcSettings"] = {
            "serviceName": node["ws_path"].lstrip("/") if node["ws_path"] else ""
        }
    
    # TLS 配置
    if node["security"] == "tls":
        config["outbounds"][0]["streamSettings"]["tlsSettings"] = {
            "serverName": node["sni"],
            "fingerprint": node["fingerprint"],
            "allowInsecure": False
        }
    elif node["security"] == "reality":
        config["outbounds"][0]["streamSettings"]["realitySettings"] = {
            "serverName": node["sni"],
            "fingerprint": node["fingerprint"],
            "publicKey": node.get("pbk", ""),
            "shortId": node.get("sid", ""),
            "allowInsecure": False
        }
    
    return config

def main():
    vless_url = os.environ.get('VLESS_NODE', '')
    
    if not vless_url:
        print("❌ 错误: 未设置 VLESS_NODE 环境变量", file=sys.stderr)
        sys.exit(1)
    
    try:
        config = generate_xray_config(vless_url)
        print(json.dumps(config, indent=2))
    except Exception as e:
        print(f"❌ 生成配置失败: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
