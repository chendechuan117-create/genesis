import asyncio
from genesis.core.config import config
from genesis.core.provider_manager import ProviderRouter

def main():
    router = ProviderRouter(config)
    print("Main Active Provider (Expensive):", router.get_active_provider().default_model)
    
    consumable = router.get_consumable_provider()
    
    if consumable:
        print("Consumables Pool Provider (Cheap/Free):", consumable.default_model)
        print("Base URL:", consumable.base_url)
    else:
        print("Failed to map consumables!")

if __name__ == "__main__":
    main()
