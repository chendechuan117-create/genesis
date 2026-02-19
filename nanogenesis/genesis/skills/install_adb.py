from genesis.core.base import Tool
import subprocess

class InstallADBTool(Tool):
    name = "install_adb"
    description = "Install Android Debug Bridge (ADB) and related tools"
    parameters = {
        "type": "object",
        "properties": {
            "package_manager": {
                "type": "string",
                "description": "Package manager to use (pacman, apt, yum, etc.)",
                "default": "pacman"
            }
        }
    }
    
    def execute(self, package_manager="pacman"):
        commands = {
            'pacman': [
                'sudo pacman -S android-tools --noconfirm',
                'sudo pacman -S scrcpy --noconfirm',
                'sudo pacman -S ffmpeg --noconfirm'
            ],
            'apt': [
                'sudo apt update',
                'sudo apt install -y adb',
                'sudo apt install -y scrcpy',
                'sudo apt install -y ffmpeg'
            ],
            'yum': [
                'sudo yum install -y android-tools-adb',
                'sudo yum install -y scrcpy',
                'sudo yum install -y ffmpeg'
            ]
        }
        
        pm = package_manager.lower()
        if pm not in commands:
            return f"Unsupported package manager: {pm}"
            
        result = []
        for cmd in commands[pm]:
            try:
                output = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                result.append(f"{cmd}:\n{output.stdout}")
                if output.stderr:
                    result.append(f"Error: {output.stderr}")
            except Exception as e:
                result.append(f"Exception: {str(e)}")
        
        return "\n".join(result)
