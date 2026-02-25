import asyncio
from genesis.tools.code_analyzer_tool import CodeAnalyzerTool
from genesis.tools.db_tool import DatabaseQueryTool
from genesis.core.factory import GenesisFactory

async def main():
    analyzer = CodeAnalyzerTool()
    print("Testing AST Code Analyzer on factory.py...")
    res = await analyzer.execute("genesis/core/factory.py", target="classes")
    print(res[:500])
    
    print("\n----------------\n")
    
    db_tool = DatabaseQueryTool()
    print("Testing DB Tool on SQLite memory...")
    res_db = await db_tool.execute("data/genesis.db", "SELECT name FROM sqlite_master WHERE type='table'")
    print(res_db)
    
if __name__ == "__main__":
    asyncio.run(main())
