
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "nanogenesis"))

from genesis.core.config import ConfigManager

def test_config_loading():
    # Force reload
    ConfigManager._instance = None
    config = ConfigManager().config
    
    print(f"TAVILY_API_KEY: {config.tavily_api_key}")
    
    if config.tavily_api_key and "tvly-" in config.tavily_api_key:
        print("✅ Config loaded successfully.")
    else:
        print("❌ Config load failed or key is wrong.")

if __name__ == "__main__":
    test_config_loading()
