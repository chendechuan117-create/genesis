#!/bin/bash
set -e

echo "=== GitNexus Diagnostic & Setup Tool ==="

# 1. Check Node.js
echo "[1/5] Checking Node.js environment..."
if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found!"
    exit 1
fi
node_version=$(node -v)
echo "✅ Node.js version: $node_version"

# 2. Check GitNexus CLI
echo "[2/5] Checking GitNexus CLI..."
if ! command -v gitnexus &> /dev/null; then
    echo "⚠️ GitNexus not found in PATH. Attempting to install globally..."
    npm install -g @gitnexus/mcp-server
else
    echo "✅ GitNexus found: $(which gitnexus)"
    echo "   Version: $(gitnexus --version)"
fi

# 3. Check/Build Index
echo "[3/5] Checking Repository Index..."
REPO_PATH=$(pwd)
echo "   Target: $REPO_PATH"

if [ -d ".gitnexus" ]; then
    echo "   Found existing .gitnexus directory."
    # Check if we can query it
    echo "   Testing query capability..."
    if gitnexus query "run" --limit 1 &> /dev/null; then
         echo "✅ Index is valid and queryable."
    else
         echo "⚠️ Index seems corrupted or incompatible. Rebuilding..."
         gitnexus analyze .
    fi
else
    echo "   No index found. Analyzing repository..."
    gitnexus analyze .
fi

# 4. MCP Server Test
echo "[4/5] Testing MCP Server startup (dry run)..."
# We run it with a timeout to ensure it starts and doesn't crash immediately
# exit code 124 means timeout (success in this case, meaning it kept running)
timeout 5s gitnexus mcp &> /dev/null || exit_code=$?
if [ "$exit_code" = "124" ]; then
    echo "✅ MCP Server starts correctly."
else
    echo "⚠️ MCP Server exited unexpectedly with code $exit_code"
    # Try capturing output to see why
    timeout 2s gitnexus mcp
fi

# 5. Configuration Output
echo "[5/5] Windsurf Configuration Helper"
echo "---------------------------------------------------"
echo "Please ensure your ~/.codeium/windsurf/mcp_config.json contains:"
echo ""
echo "{"
echo "  \"mcpServers\": {"
echo "    \"gitnexus\": {"
echo "      \"command\": \"$(which gitnexus)\","
echo "      \"args\": [\"mcp\"],"
echo "      \"env\": {"
echo "        \"GITNEXUS_REPO_PATH\": \"$REPO_PATH\""
echo "      }"
echo "    }"
echo "  }"
echo "}"
echo "---------------------------------------------------"
echo "✅ Diagnosis complete."
