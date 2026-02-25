import time
import subprocess
import threading
from datetime import datetime, timedelta
from genesis.core.base import Tool

class ActivityMonitor(Tool):
    @property
    def name(self) -> str:
        return "activity_monitor"
        
    @property
    def description(self) -> str:
        return "监控用户活动状态，根据空闲时间触发相应动作（播放/暂停音乐、久坐提醒等）"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "idle_threshold": {
                    "type": "integer",
                    "description": "久坐提醒阈值（秒），默认1800秒（30分钟）",
                    "default": 1800
                },
                "check_interval": {
                    "type": "integer", 
                    "description": "检查间隔（秒），默认5秒",
                    "default": 5
                },
                "music_player": {
                    "type": "string",
                    "description": "音乐播放器命令，默认'yesplaymusic'",
                    "default": "yesplaymusic"
                },
                "reminder_message": {
                    "type": "string",
                    "description": "久坐提醒消息",
                    "default": "🪑 您已经久坐 {minutes} 分钟，该起来活动一下了！"
                }
            },
            "required": []
        }
        
    async def execute(self, idle_threshold: int = 1800, check_interval: int = 5, 
                     music_player: str = "yesplaymusic", reminder_message: str = None) -> str:
        """
        启动活动监控系统
        
        功能：
        1. 监控键盘/鼠标活动
        2. 根据活动状态控制音乐播放
        3. 久坐提醒
        4. 活动恢复检测
        """
        
        if reminder_message is None:
            reminder_message = "🪑 您已经久坐 {minutes} 分钟，该起来活动一下了！"
        
        # 获取初始活动时间
        last_activity_time = datetime.now()
        is_music_playing = False
        reminder_sent = False
        
        def check_user_activity():
            """检查用户是否有输入活动"""
            nonlocal last_activity_time
            
            try:
                # 方法1：检查X11输入事件（Linux桌面）
                result = subprocess.run(
                    ["xinput", "test-xi2", "--root"],
                    capture_output=True, text=True, timeout=1
                )
                if "EVENT" in result.stdout:
                    return True
            except:
                pass
            
            try:
                # 方法2：检查键盘状态
                result = subprocess.run(
                    ["xset", "q"],
                    capture_output=True, text=True
                )
                if "Keyboard" in result.stdout:
                    # 解析键盘状态
                    for line in result.stdout.split('\n'):
                        if "auto repeat" in line:
                            return True
            except:
                pass
            
            return False
        
        def control_music(action: str):
            """控制音乐播放"""
            nonlocal is_music_playing
            
            try:
                if action == "play" and not is_music_playing:
                    # 启动或恢复音乐
                    subprocess.Popen([music_player], start_new_session=True)
                    time.sleep(2)  # 等待播放器启动
                    
                    # 发送播放命令
                    subprocess.run(["xdotool", "key", "space"], check=False)
                    is_music_playing = True
                    return f"音乐已{action}"
                    
                elif action == "pause" and is_music_playing:
                    # 暂停音乐
                    subprocess.run(["xdotool", "key", "space"], check=False)
                    is_music_playing = False
                    return f"音乐已{action}"
                    
            except Exception as e:
                return f"音乐控制失败: {e}"
            
            return f"音乐状态未改变 ({action})"
        
        def send_reminder(idle_minutes: int):
            """发送久坐提醒"""
            nonlocal reminder_sent
            
            message = reminder_message.format(minutes=idle_minutes)
            
            # 方法1：桌面通知（Linux）
            try:
                subprocess.run([
                    "notify-send", 
                    "久坐提醒", 
                    message,
                    "--icon=dialog-information",
                    "--urgency=normal"
                ], check=False)
            except:
                pass
            
            # 方法2：终端输出
            print(f"\n🔔 {message}")
            
            # 方法3：声音提醒（可选）
            try:
                subprocess.run(["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"], 
                             check=False)
            except:
                pass
            
            reminder_sent = True
            return message
        
        # 主监控循环
        print(f"🎯 活动监控已启动")
        print(f"⏰ 久坐提醒: {idle_threshold//60} 分钟")
        print(f"📊 检查间隔: {check_interval} 秒")
        print(f"🎵 音乐播放器: {music_player}")
        print("-" * 50)
        
        try:
            while True:
                current_time = datetime.now()
                
                # 检查当前活动状态
                if check_user_activity():
                    # 用户有活动
                    last_activity_time = current_time
                    
                    if not is_music_playing and not reminder_sent:
                        # 恢复音乐播放
                        result = control_music("play")
                        print(f"🔄 检测到活动: {result}")
                    
                    if reminder_sent:
                        print("✅ 活动恢复，提醒重置")
                        reminder_sent = False
                        
                else:
                    # 用户无活动
                    idle_seconds = (current_time - last_activity_time).total_seconds()
                    idle_minutes = int(idle_seconds // 60)
                    
                    if idle_seconds >= idle_threshold and not reminder_sent:
                        # 触发久坐提醒
                        message = send_reminder(idle_minutes)
                        print(f"⏳ 空闲时间: {idle_minutes} 分钟 - {message}")
                        
                        # 暂停音乐
                        control_music("pause")
                    
                    elif idle_seconds < idle_threshold and is_music_playing:
                        # 正常空闲，保持音乐播放
                        pass
                
                # 显示状态
                idle_seconds = (current_time - last_activity_time).total_seconds()
                status = "活动" if idle_seconds < 5 else f"空闲 {int(idle_seconds//60)}分{int(idle_seconds%60)}秒"
                music_status = "播放中" if is_music_playing else "暂停"
                
                print(f"\r📊 状态: {status} | 🎵 音乐: {music_status}", end="", flush=True)
                
                time.sleep(check_interval)
                
        except KeyboardInterrupt:
            print("\n\n🛑 监控已停止")
            return "活动监控已正常停止"
        except Exception as e:
            return f"监控错误: {str(e)}"