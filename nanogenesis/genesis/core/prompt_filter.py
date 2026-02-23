"""
ContextualPromptFilter — Genesis 动态 Prompt 排序器
======================================================
根据当前任务类型，对 system_prompt 中各段落进行**权重排序**。
不删除任何信息，只调整顺序——确保适应性完整保留。

设计原则：
  - "降低噪声" 而非 "减少信息"
  - 重要段落推前 → LLM attention 自然对齐
  - 不相关段落退后 → Context 头部保持高信噪比

任务类型自动识别（基于关键词，无模型依赖）：
  code     : 代码、编程、debug、python、函数…
  system   : pacman、systemctl、配置、权限、安装…
  media    : 音乐、视频、截图、播放、yesplay…
  web      : 搜索、网页、fetch、URL、网络请求…
  general  : 其他

每种任务类型对应一套段落优先级模板。
"""

import re
import logging
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# 任务类型关键词映射
# --------------------------------------------------------------------------
_TASK_KEYWORDS: dict = {
    "code": [
        "代码", "编程", "debug", "python", "函数", "class", "import",
        "error", "traceback", "script", "写一个", "实现", "bug", "syntax",
    ],
    "system": [
        "pacman", "systemctl", "配置", "权限", "安装", "卸载", "进程",
        "服务", "启动", "journalctl", "arch", "linux", "shell", "bash",
    ],
    "media": [
        "音乐", "视频", "播放", "截图", "screenshot", "yesplay", "mpv",
        "ffmpeg", "声音", "音频", "歌", "图片", "visual",
    ],
    "web": [
        "搜索", "网页", "fetch", "url", "http", "网络", "浏览器",
        "下载", "request", "api", "爬", "login",
    ],
}

# --------------------------------------------------------------------------
# 段落权重模板
# 每种任务类型下，段落关键词的优先级得分调整
# 正值 = 推前，负值 = 退后
# --------------------------------------------------------------------------
_PRIORITY_BOOST: dict = {
    "code": {
        "工具": +3, "tool": +3, "代码": +3, "python": +3,
        "能力": +2, "调试": +2,
        "偏好": -2, "习惯": -2, "生活": -3, "饮食": -3,
    },
    "system": {
        "系统": +3, "权限": +3, "工具": +2,
        "user_profile": -1, "偏好": -2,
    },
    "media": {
        "工具": +2, "visual": +3, "screenshot": +3,
        "代码": -1,
    },
    "web": {
        "网络": +3, "search": +3, "fetch": +3, "工具": +2,
        "系统配置": -1,
    },
    "general": {},  # 不调整，保持原始顺序
}


class ContextualPromptFilter:
    """
    动态 Prompt 段落排序器。

    参数：
      section_delimiter : 用于分割 prompt 各段的分隔符（默认双换行）
    """

    def __init__(self, section_delimiter: str = "\n\n"):
        self.delimiter = section_delimiter

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rank(self, prompt: str, user_input: str) -> str:
        """
        根据 user_input 任务类型，对 prompt 段落重新排序。

        Args:
            prompt     : 当前完整的 system_prompt 字符串
            user_input : 用户的当前输入（用于任务类型检测）

        Returns:
            重排序后的 prompt（段落数量、内容完全不变）
        """
        if not prompt or not user_input:
            return prompt

        task_type = self._detect_task_type(user_input)
        if task_type == "general":
            # general 类型无需重排
            return prompt

        sections = self._split_sections(prompt)
        if len(sections) <= 1:
            # 无法分段，直接返回
            return prompt

        scored = self._score_sections(sections, task_type)
        reordered = [s for s, _ in sorted(scored, key=lambda x: -x[1])]

        logger.debug(f"🎯 PromptFilter: task_type={task_type}, sections={len(sections)}")
        return self.delimiter.join(reordered)

    def detect(self, user_input: str) -> str:
        """仅返回检测到的任务类型（供外部调试用）"""
        return self._detect_task_type(user_input)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _detect_task_type(self, user_input: str) -> str:
        text = user_input.lower()
        scores = {task: 0 for task in _TASK_KEYWORDS}
        for task, keywords in _TASK_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    scores[task] += 1
        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] > 0 else "general"

    def _split_sections(self, prompt: str) -> List[str]:
        """按分隔符拆分 prompt 段落，过滤空段"""
        parts = prompt.split(self.delimiter)
        return [p for p in parts if p.strip()]

    def _score_sections(
        self, sections: List[str], task_type: str
    ) -> List[Tuple[str, float]]:
        """
        对每个段落打分：
          - 基础分 = 原始位置权重（越靠前基础分越高，保持原有顺序的惯性）
          - 调整分 = 根据任务类型的关键词 boost
        """
        boost_map = _PRIORITY_BOOST.get(task_type, {})
        n = len(sections)
        scored = []

        for i, section in enumerate(sections):
            # 基础分：原始位置越靠前分越高（归一化到 0-10）
            base_score = (n - i) / n * 10.0
            # 关键词调整
            adjustment = 0.0
            section_lower = section.lower()
            for keyword, delta in boost_map.items():
                if keyword in section_lower:
                    adjustment += delta
            scored.append((section, base_score + adjustment))

        return scored
