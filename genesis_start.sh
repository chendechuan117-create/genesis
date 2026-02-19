#!/bin/bash
# Genesis Launcher
# 自动定位并启动 CLI

# 获取脚本所在目录 (Genesis root)
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 进入 nanogenesis 子目录
cd "$DIR/nanogenesis"

# 执行 CLI，传递所有参数
python3 cli.py "$@"
