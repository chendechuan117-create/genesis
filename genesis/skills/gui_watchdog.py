import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

class GuiWatchdog(Tool):
    @property
    def name(self) -> str:
        return "gui_watchdog"

    @property
    def description(self) -> str:
        return "对当前桌面做一次非阻塞 GUI 快照分析：采集进程、窗口、截图与可选 OCR 线索，判断是否疑似 GUI 阻塞以及是否建议人工接管。适用于超时、疑似卡在安装器/登录/确认弹窗/Wine 窗口等场景。"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "target_hint": {
                    "type": "string",
                    "description": "被观察的应用/任务提示词，例如 'wine', 'STOVE', 'installer', 'login'。"
                }
            },
            "required": ["target_hint"]
        }

    async def execute(self, target_hint: str) -> str:
        def run(cmd: str) -> str:
            try:
                p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=12)
                out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
                return out[:8000]
            except Exception as e:
                return f"ERR: {e}"

        def cmd_exists(name: str) -> bool:
            p = subprocess.run(f"command -v {shlex.quote(name)} >/dev/null 2>&1", shell=True)
            return p.returncode == 0

        env = {
            "DISPLAY": os.environ.get("DISPLAY", ""),
            "WAYLAND_DISPLAY": os.environ.get("WAYLAND_DISPLAY", ""),
            "XDG_SESSION_TYPE": os.environ.get("XDG_SESSION_TYPE", ""),
        }

        hint = (target_hint or "").strip()
        hint_re = re.escape(hint) if hint else ""
        keyword_re = r"wine|stove|setup|installer|install|update|login|sign[ -]?in|authorize|consent|agree|ok|confirm|password|verification|captcha|steam|epic"
        combined_re = f"({hint_re}|{keyword_re})" if hint_re else f"({keyword_re})"

        proc_cmd = "ps -eo pid,ppid,stat,etimes,%cpu,%mem,comm,args --sort=-etimes | sed -n '1,220p'"
        proc_all = run(proc_cmd)
        proc_hits = run(f"ps -eo pid,ppid,stat,etimes,%cpu,%mem,comm,args --sort=-etimes | grep -Ei {shlex.quote(combined_re)} | grep -v grep | sed -n '1,80p'")

        wmctrl_out = run("wmctrl -lx 2>/dev/null || true") if cmd_exists("wmctrl") else "wmctrl unavailable"
        xdotool_out = run("xdotool search --onlyvisible --name '.' 2>/dev/null | head -n 30 | while read id; do xdotool getwindowname \"$id\" 2>/dev/null; done") if cmd_exists("xdotool") else "xdotool unavailable"
        xprop_root = run("xprop -root _NET_ACTIVE_WINDOW 2>/dev/null || true") if cmd_exists("xprop") else "xprop unavailable"

        scratch_dir = Path("runtime/scratch/gui_watchdog")
        scratch_dir.mkdir(parents=True, exist_ok=True)
        fd, shot_path = tempfile.mkstemp(prefix="shot_", suffix=".png", dir=str(scratch_dir))
        os.close(fd)
        shot_ok = False
        shot_method = "none"

        if cmd_exists("scrot"):
            p = subprocess.run(f"scrot {shlex.quote(shot_path)}", shell=True, capture_output=True, text=True, timeout=20)
            if p.returncode == 0 and Path(shot_path).exists() and Path(shot_path).stat().st_size > 0:
                shot_ok = True
                shot_method = "scrot"
        if (not shot_ok) and cmd_exists("spectacle"):
            p = subprocess.run(f"spectacle -b -n -o {shlex.quote(shot_path)}", shell=True, capture_output=True, text=True, timeout=20)
            if Path(shot_path).exists() and Path(shot_path).stat().st_size > 0:
                shot_ok = True
                shot_method = "spectacle"

        ocr_text = ""
        if shot_ok:
            py = (
                "from PIL import Image; import pytesseract, sys; "
                "img=Image.open(sys.argv[1]); "
                "txt=pytesseract.image_to_string(img, lang='eng'); "
                "print(txt[:3000])"
            )
            try:
                p = subprocess.run(["python3", "-c", py, shot_path], capture_output=True, text=True, timeout=25)
                ocr_text = (p.stdout or "")[:3000]
            except Exception as e:
                ocr_text = f"OCR_ERR: {e}"

        evidence = []
        score = 0

        def add_if(cond: bool, pts: int, msg: str):
            nonlocal score
            if cond:
                score += pts
                evidence.append(msg)

        proc_hits_nonempty = proc_hits.strip() and not proc_hits.strip().startswith("ERR")
        wm_hits = [ln for ln in (wmctrl_out + "\n" + xdotool_out).splitlines() if re.search(combined_re, ln, re.I)]
        ocr_hits = [ln for ln in ocr_text.splitlines() if re.search(combined_re, ln, re.I)]

        add_if(proc_hits_nonempty, 2, "发现匹配 target_hint/阻塞关键词的进程")
        add_if(len(wm_hits) > 0, 3, f"窗口标题疑似命中 {len(wm_hits)} 条")
        add_if(len(ocr_hits) > 0, 4, f"截图 OCR 疑似命中 {len(ocr_hits)} 条")
        add_if(bool(re.search(r"wine", proc_hits, re.I)) or bool(re.search(r"wine", '\n'.join(wm_hits), re.I)) or bool(re.search(r"wine", ocr_text, re.I)), 2, "存在 Wine 相关线索")
        add_if(bool(re.search(r"login|sign[ -]?in|password|verify|captcha", ocr_text, re.I)), 4, "截图中出现登录/验证类文字")
        add_if(bool(re.search(r"agree|accept|confirm|ok|continue|next|install|update", ocr_text, re.I)), 3, "截图中出现确认/安装/继续类文字")
        add_if((not proc_hits_nonempty) and len(wm_hits) == 0 and len(ocr_hits) == 0, 0, "未直接发现 target 线索")

        if score >= 7:
            suspect = "HIGH"
            handoff = "YES"
        elif score >= 4:
            suspect = "MEDIUM"
            handoff = "MAYBE"
        else:
            suspect = "LOW"
            handoff = "NO"

        parts = []
        parts.append(f"target_hint={hint or '-'}")
        parts.append(f"session={env['XDG_SESSION_TYPE']} display={env['DISPLAY']} wayland={env['WAYLAND_DISPLAY']}")
        parts.append(f"suspicious_gui_block={suspect}")
        parts.append(f"recommend_human_handoff={handoff}")
        parts.append(f"screenshot={'OK' if shot_ok else 'NO'} method={shot_method} path={shot_path if shot_ok else '-'}")
        parts.append(f"active_window={xprop_root.strip()[:200] if xprop_root.strip() else 'unknown'}")
        if evidence:
            parts.append("evidence=" + "；".join(evidence[:8]))
        if proc_hits_nonempty:
            parts.append("process_hits=" + " || ".join(proc_hits.splitlines()[:6]))
        if wm_hits:
            parts.append("window_hits=" + " || ".join(wm_hits[:6]))
        if ocr_hits:
            parts.append("ocr_hits=" + " || ".join(ocr_hits[:6]))
        elif ocr_text.strip():
            compact = " ".join(ocr_text.split())[:400]
            parts.append("ocr_excerpt=" + compact)
        return "\n".join(parts)
