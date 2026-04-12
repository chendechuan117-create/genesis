#!/usr/bin/env python3
"""
最终IP测试 - 确认企业微信API看到的IP地址
"""

import json
import os

import requests

# 企业微信配置
CORP_ID = "ww17809bd1255d3ec9"
SECRET = "tj3QXRgmj9sL2k2Rv-P79HnJB7sEjhtgKpXQrmYAY40"
AGENT_ID = 1000002

PROXY_KEYS = (
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "all_proxy",
    "ALL_PROXY",
)


def clear_proxy_env():
    for key in PROXY_KEYS:
        os.environ.pop(key, None)


def get_proxy_url(default=None):
    for key in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY"):
        value = os.environ.get(key)
        if value:
            return value
    return default


def apply_proxy_env(proxy_url):
    os.environ["http_proxy"] = proxy_url
    os.environ["https_proxy"] = proxy_url
    os.environ["HTTP_PROXY"] = proxy_url
    os.environ["HTTPS_PROXY"] = proxy_url


def build_proxy_config(use_proxy=True, proxy_url=None):
    if not use_proxy:
        clear_proxy_env()
        return {}, None

    resolved_proxy = proxy_url or get_proxy_url()
    if not resolved_proxy:
        clear_proxy_env()
        return None, None

    apply_proxy_env(resolved_proxy)
    return {"http": resolved_proxy, "https": resolved_proxy}, resolved_proxy


def extract_ip_from_errmsg(errmsg):
    marker = "from ip:"
    if marker not in errmsg:
        return None

    tail = errmsg.split(marker, 1)[1].strip()
    return tail.split(",", 1)[0].strip()


def test_with_proxy_settings(use_proxy=True, proxy_url=None):
    """使用指定代理设置测试"""
    print(f"\n{'=' * 60}")
    proxies, resolved_proxy = build_proxy_config(use_proxy=use_proxy, proxy_url=proxy_url)

    if use_proxy:
        if proxies is None:
            print("测试配置：使用代理")
            print("未检测到代理环境变量，跳过代理测试，而不是误报为网络故障")
            return {"skipped": True, "reason": "proxy_not_configured"}
        print("测试配置：使用代理")
        print(f"代理地址: {resolved_proxy}")
    else:
        print("测试配置：不使用代理")
        proxies = {}

    try:
        token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={CORP_ID}&corpsecret={SECRET}"
        token_response = requests.get(token_url, timeout=10, proxies=proxies)
        token_result = token_response.json()

        if token_result.get("errcode") != 0:
            print(f"获取access_token失败: {token_result}")
            return token_result

        access_token = token_result.get("access_token")
        print("✓ access_token获取成功")

        message_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
        message = {
            "touser": "@all",
            "msgtype": "text",
            "agentid": AGENT_ID,
            "text": {
                "content": f"IP测试消息 - 代理设置: {use_proxy}"
            }
        }

        msg_response = requests.post(message_url, json=message, timeout=10, proxies=proxies)
        msg_result = msg_response.json()

        print("消息发送结果:")
        print(json.dumps(msg_result, indent=2, ensure_ascii=False))

        return msg_result

    except Exception as e:
        print(f"测试过程中出现异常: {e}")
        return None


def main():
    print("企业微信IP白名单配置测试")
    print(f"企业ID: {CORP_ID}")
    print(f"AgentId: {AGENT_ID}")

    print("\n测试1：不使用代理")
    result1 = test_with_proxy_settings(use_proxy=False)

    print("\n测试2：使用代理")
    result2 = test_with_proxy_settings(use_proxy=True)

    print("\n" + "=" * 60)
    print("分析结果:")

    if result1 and result1.get("errcode") == 60020:
        ip1 = extract_ip_from_errmsg(result1.get("errmsg", ""))
        if ip1:
            print(f"不使用代理时，企业微信看到的IP: {ip1}")

    if result2 and result2.get("errcode") == 60020:
        ip2 = extract_ip_from_errmsg(result2.get("errmsg", ""))
        if ip2:
            print(f"使用代理时，企业微信看到的IP: {ip2}")

    print("\n配置建议:")
    print("1. 登录企业微信管理后台 (work.weixin.qq.com)")
    print("2. 进入'我的企业' -> '安全与保密' -> 'IP白名单'")
    print("3. 添加上述IP地址到白名单中")
    print("4. 保存配置后重新测试")


if __name__ == "__main__":
    main()
