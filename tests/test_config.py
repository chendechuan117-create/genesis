from nanogenesis.core.config import ConfigManager
import logging

logging.basicConfig(level=logging.INFO)

cm = ConfigManager()
print(f"API Key: {cm.config.deepseek_api_key}")
print(f"Proxy: {cm.config.http_proxy}")
print(f"Token: {cm.config.telegram_bot_token}")
