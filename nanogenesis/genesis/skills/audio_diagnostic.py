import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class AudioDiagnosticTool(Tool):
    @property
    def name(self) -> str:
        return "audio_diagnostic"
        
    @property
    def description(self) -> str:
        return "诊断音频系统状态，检测问题并提供修复建议。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "执行动作：'check'(检查状态) 或 'fix'(自动修复)",
                    "enum": ["check", "fix"],
                    "default": "check"
                }
            },
            "required": []
        }
        
    async def execute(self, action: str = "check") -> str:
        import subprocess
        import json
        from datetime import datetime
        
        def run_command(cmd):
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
                return result.stdout.strip(), result.stderr.strip(), result.returncode
            except Exception as e:
                return "", str(e), 1
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if action == "check":
            # 检查音频状态
            report = f"# 🎵 音频系统诊断报告\n"
            report += f"**诊断时间**: {timestamp}\n\n"
            
            # 1. 检查默认音频设备
            default_sink, _, _ = run_command("pactl info | grep 'Default Sink' | cut -d: -f2 | xargs")
            report += f"## 📊 默认音频设备\n"
            report += f"- **输出设备**: `{default_sink if default_sink else '未设置'}`\n"
            
            # 2. 检查设备状态
            sinks, _, _ = run_command("pactl list sinks short")
            report += f"\n## 🔊 音频设备状态\n"
            if sinks:
                for line in sinks.split('\n'):
                    if line:
                        parts = line.split()
                        sink_id = parts[0]
                        sink_name = parts[1]
                        
                        # 获取音量状态
                        vol_out, _, _ = run_command(f"pactl get-sink-volume {sink_id}")
                        mute_out, _, _ = run_command(f"pactl get-sink-mute {sink_id}")
                        
                        report += f"- `{sink_name}` (ID: {sink_id})\n"
                        report += f"  - 音量: {vol_out if vol_out else '未知'}\n"
                        report += f"  - 静音: {'是' if 'yes' in mute_out.lower() else '否'}\n"
            else:
                report += "无音频设备\n"
            
            # 3. 检查活跃音频流
            sink_inputs, _, _ = run_command("pactl list sink-inputs")
            report += f"\n## 📡 活跃音频流\n"
            
            if "Sink Input #" in sink_inputs:
                lines = sink_inputs.split('\n')
                stream_count = 0
                
                for i, line in enumerate(lines):
                    if line.strip().startswith("Sink Input #"):
                        stream_count += 1
                        stream_id = line.strip().split("#")[1]
                        
                        # 查找应用名称
                        app_name = "未知"
                        for j in range(i+1, min(i+10, len(lines))):
                            if "application.name" in lines[j]:
                                app_name = lines[j].split("=")[1].strip().strip('"')
                                break
                        
                        report += f"### 音频流 #{stream_count}\n"
                        report += f"- **ID**: {stream_id}\n"
                        report += f"- **应用**: `{app_name}`\n"
                        
                        # 检查静音状态
                        for j in range(i+1, min(i+10, len(lines))):
                            if "Mute:" in lines[j]:
                                mute_status = lines[j].split(":")[1].strip()
                                report += f"- **静音**: {mute_status}\n"
                                if mute_status.lower() == "yes":
                                    report += "  ⚠️ **检测到静音问题**\n"
                                break
            else:
                report += "无活跃音频流\n"
            
            # 4. 问题总结
            report += f"\n## 🔍 问题检测\n"
            
            # 检查是否有yesplaymusic相关音频流
            if "yesplaymusic" in sink_inputs.lower() or "chromium" in sink_inputs.lower():
                report += "✅ **检测到yesplaymusic/Chromium音频流**\n"
            else:
                report += "❌ **未检测到yesplaymusic音频流**\n"
                report += "可能原因：\n"
                report += "1. 应用未播放音频\n"
                report += "2. 音频流被识别为其他名称\n"
                report += "3. 应用音频引擎故障\n"
            
            report += f"\n---\n"
            report += f"*诊断完成时间: {timestamp}*"
            
            return report
            
        elif action == "fix":
            # 自动修复
            fixes = []
            
            # 1. 取消默认设备静音
            default_sink, _, _ = run_command("pactl info | grep 'Default Sink' | cut -d: -f2 | xargs")
            if default_sink:
                run_command(f"pactl set-sink-mute {default_sink} 0")
                run_command(f"pactl set-sink-volume {default_sink} 70%")
                fixes.append(f"取消默认设备静音并设置音量到70%")
            
            # 2. 查找并修复yesplaymusic音频流
            sink_inputs, _, _ = run_command("pactl list sink-inputs")
            lines = sink_inputs.split('\n')
            current_id = None
            
            for i, line in enumerate(lines):
                line = line.strip()
                if line.startswith("Sink Input #"):
                    current_id = line.split("#")[1]
                elif current_id and ("yesplaymusic" in line.lower() or "chromium" in line.lower()):
                    # 修复该音频流
                    run_command(f"pactl set-sink-input-mute {current_id} 0")
                    run_command(f"pactl set-sink-input-volume {current_id} 100%")
                    
                    # 获取应用名称
                    app_name = "unknown"
                    for j in range(i+1, min(i+10, len(lines))):
                        if "application.name" in lines[j]:
                            app_name = lines[j].split("=")[1].strip().strip('"')
                            break
                    
                    fixes.append(f"修复音频流: {app_name} (ID: {current_id})")
                    current_id = None
            
            if fixes:
                report = f"# ✅ 音频修复完成\n"
                report += f"**修复时间**: {timestamp}\n\n"
                report += "已应用以下修复：\n\n"
                for fix in fixes:
                    report += f"- {fix}\n"
                report += f"\n请测试音频是否恢复正常。"
            else:
                report = f"# ℹ️ 无需修复\n"
                report += f"未检测到需要修复的音频问题。\n"
                report += f"如果仍有问题，可能是应用内部问题。"
            
            return report