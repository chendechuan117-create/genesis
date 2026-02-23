import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class YesplaymusicDiagnosticTool(Tool):
    @property
    def name(self) -> str:
        return "yesplaymusic_diagnostic"
        
    @property
    def description(self) -> str:
        return "诊断yesplaymusic播放问题：黑屏、播放错误、无法切换歌曲等"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string", 
                    "enum": ["check_window", "check_audio", "check_process", "check_cache", "full_diagnosis"],
                    "description": "诊断动作"
                },
                "song_name": {
                    "type": "string", 
                    "description": "要播放的歌曲名称（用于测试）",
                    "default": ""
                }
            },
            "required": ["action"]
        }
        
    async def execute(self, action: str, song_name: str = "") -> str:
        import subprocess
        import json
        import os
        
        results = []
        
        if action == "check_window" or action == "full_diagnosis":
            # 检查窗口状态
            try:
                # 尝试使用xprop查找窗口
                xprop_cmd = ["xprop", "-root", "_NET_CLIENT_LIST"]
                xprop_result = subprocess.run(xprop_cmd, capture_output=True, text=True)
                
                if xprop_result.returncode == 0:
                    # 解析窗口列表
                    window_ids = []
                    for line in xprop_result.stdout.split('\n'):
                        if 'window id' in line:
                            parts = line.split('#')
                            if len(parts) > 1:
                                window_ids = [w.strip() for w in parts[1].split(',')]
                    
                    # 检查每个窗口的标题
                    yesplaymusic_windows = []
                    for win_id in window_ids[:10]:  # 限制检查数量
                        try:
                            title_cmd = ["xprop", "-id", win_id, "WM_NAME"]
                            title_result = subprocess.run(title_cmd, capture_output=True, text=True, timeout=2)
                            if "yesplaymusic" in title_result.stdout.lower():
                                yesplaymusic_windows.append(win_id)
                        except:
                            continue
                    
                    if yesplaymusic_windows:
                        results.append(f"✅ 找到yesplaymusic窗口: {yesplaymusic_windows}")
                    else:
                        results.append("❌ 未找到yesplaymusic窗口（可能黑屏或最小化）")
                else:
                    results.append("⚠️ 无法检查X11窗口（xprop不可用）")
            except Exception as e:
                results.append(f"⚠️ 窗口检查失败: {str(e)}")
        
        if action == "check_process" or action == "full_diagnosis":
            # 检查进程状态
            try:
                ps_cmd = ["ps", "aux"]
                ps_result = subprocess.run(ps_cmd, capture_output=True, text=True)
                
                yesplaymusic_processes = []
                for line in ps_result.stdout.split('\n'):
                    if 'yesplaymusic' in line.lower() or 'electron' in line.lower() and 'app.asar' in line:
                        yesplaymusic_processes.append(line.strip())
                
                if yesplaymusic_processes:
                    results.append(f"✅ yesplaymusic进程正在运行（共{len(yesplaymusic_processes)}个）")
                    for proc in yesplaymusic_processes[:3]:
                        results.append(f"  - {proc[:80]}...")
                else:
                    results.append("❌ 未找到yesplaymusic进程")
            except Exception as e:
                results.append(f"⚠️ 进程检查失败: {str(e)}")
        
        if action == "check_audio" or action == "full_diagnosis":
            # 检查音频状态
            try:
                # 检查PipeWire/PulseAudio状态
                pactl_cmd = ["pactl", "info"]
                pactl_result = subprocess.run(pactl_cmd, capture_output=True, text=True)
                
                if pactl_result.returncode == 0:
                    results.append("✅ 音频服务正常（PipeWire/PulseAudio）")
                    
                    # 检查Chromium音频流
                    sink_cmd = ["pactl", "list", "sink-inputs"]
                    sink_result = subprocess.run(sink_cmd, capture_output=True, text=True)
                    
                    chromium_streams = []
                    for line in sink_result.stdout.split('\n'):
                        if 'application.name = "Chromium"' in line:
                            chromium_streams.append(line)
                    
                    if chromium_streams:
                        results.append(f"✅ 找到Chromium音频流（yesplaymusic使用Chromium引擎）")
                    else:
                        results.append("⚠️ 未找到Chromium音频流")
                else:
                    results.append("❌ 音频服务异常")
            except Exception as e:
                results.append(f"⚠️ 音频检查失败: {str(e)}")
        
        if action == "check_cache" or action == "full_diagnosis":
            # 检查缓存和配置
            config_path = os.path.expanduser("~/.config/yesplaymusic")
            if os.path.exists(config_path):
                results.append(f"✅ 配置文件目录存在: {config_path}")
                
                # 检查缓存大小
                cache_path = os.path.join(config_path, "Cache")
                if os.path.exists(cache_path):
                    try:
                        cache_size = sum(os.path.getsize(os.path.join(dirpath, filename))
                                       for dirpath, dirnames, filenames in os.walk(cache_path)
                                       for filename in filenames)
                        results.append(f"  缓存大小: {cache_size / (1024*1024):.2f} MB")
                    except:
                        results.append("  无法计算缓存大小")
            else:
                results.append("❌ 配置文件目录不存在")
        
        # 生成建议
        if action == "full_diagnosis":
            suggestions = []
            
            # 检查是否有"黑屏"相关线索
            has_process = any("进程正在运行" in r for r in results)
            has_window = any("找到yesplaymusic窗口" in r for r in results)
            has_audio = any("找到Chromium音频流" in r for r in results)
            
            if has_process and not has_window:
                suggestions.append("1. **黑屏问题**: 进程在运行但无窗口，可能是渲染问题")
                suggestions.append("   - 尝试重启yesplaymusic: `pkill -f yesplaymusic && yesplaymusic`")
                suggestions.append("   - 检查显卡驱动和Electron兼容性")
            
            if has_audio:
                suggestions.append("2. **播放控制问题**: 音频流存在但播放错误")
                suggestions.append("   - 可能是网易云API限制或网络问题")
                suggestions.append("   - 尝试清除缓存: `rm -rf ~/.config/yesplaymusic/Cache/*`")
            
            if suggestions:
                results.append("\n🔧 **修复建议**:")
                results.extend(suggestions)
        
        return "\n".join(results)