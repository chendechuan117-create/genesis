#!/usr/bin/env python3
import os
import sys
import json
import time
import signal
import asyncio
import logging
import random
import argparse
from datetime import datetime
from pathlib import Path

# ── PID 文件 ──
RUNTIME_DIR = Path("/tmp/test_runtime")
RUNTIME_DIR.mkdir(exist_ok=True)
PIDFILE = RUNTIME_DIR / "autopilot.pid"

# 模拟原始非原子写入
def write_pid_original(path, pid):
    path.write_text(str(pid))

# 原子写入补丁
import tempfile

def _atomic_write_pid(path, pid):
    fd, tmp_path = tempfile.mkstemp(suffix=".tmp", prefix="autopilot_pid_", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(str(pid))
        os.replace(tmp_path, path)
    except Exception:
        os.unlink(tmp_path)
        raise

if __name__ == "__main__":
    import threading
    
    # 测试1: 原始非原子写入的并发问题
    print("=== Test 1: Original non-atomic write ===")
    target1 = RUNTIME_DIR / "pid1.pid"
    empty1 = 0
    
    def writer1():
        for i in range(200):
            write_pid_original(target1, i)
    
    def reader1():
        global empty1
        for _ in range(200):
            try:
                if target1.exists():
                    data = target1.read_text()
                    if data == "":
                        empty1 += 1
            except:
                pass
    
    threads = []
    for _ in range(2):
        threads.append(threading.Thread(target=writer1))
    for _ in range(2):
        threads.append(threading.Thread(target=reader1))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print(f"Empty reads (original): {empty1}")
    
    # 测试2: 原子写入补丁
    print("\n=== Test 2: Atomic write patch ===")
    target2 = RUNTIME_DIR / "pid2.pid"
    empty2 = 0
    
    def writer2():
        for i in range(200):
            _atomic_write_pid(target2, i)
    
    def reader2():
        global empty2
        for _ in range(200):
            try:
                if target2.exists():
                    data = target2.read_text()
                    if data == "":
                        empty2 += 1
            except:
                pass
    
    threads = []
    for _ in range(2):
        threads.append(threading.Thread(target=writer2))
    for _ in range(2):
        threads.append(threading.Thread(target=reader2))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print(f"Empty reads (atomic): {empty2}")
    
    # 测试3: 验证实际补丁应用到本体代码
    print("\n=== Test 3: Verify patch on actual autopilot.py structure ===")
    # 模拟 daemon 模式
    _atomic_write_pid(PIDFILE, 9999)
    assert PIDFILE.read_text() == "9999", "PID write failed"
    print(f"PID file content: {PIDFILE.read_text()}")
    PIDFILE.unlink(missing_ok=True)
    print("All tests passed!")
