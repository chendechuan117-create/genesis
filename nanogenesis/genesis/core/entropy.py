
import hashlib
import logging
from typing import List, Dict, Any, Deque
from collections import deque
import json

logger = logging.getLogger(__name__)

class EntropyMonitor:
    """
    Monitors 'Cognitive Entropy' (State Delta) to detect stagnation loops.
    If the environment/context doesn't change despite actions, we are looping.
    """
    
    def __init__(self, window_size: int = 3):
        self.window_size = window_size
        self.history: Deque[str] = deque(maxlen=window_size)
        self.last_action_hash = None
    
    def capture(self, tool_output: str, cwd: str, active_mission_id: str) -> None:
        """
        Capture current state vector hash.
        Vector = (ToolOutput + CWD + MissionID)
        """
        # Normalize inputs
        t_out = (tool_output or "").strip()
        cwd_norm = (cwd or "").strip()
        mis_id = (active_mission_id or "").strip()
        
        # Create state string
        state_str = f"TO:{t_out}|CWD:{cwd_norm}|MID:{mis_id}"
        
        # Hash it
        state_hash = hashlib.md5(state_str.encode()).hexdigest()
        
        self.history.append(state_hash)
        logger.debug(f"Entropy Capture: {state_hash[:8]} (Window: {len(self.history)})")

    def is_stagnant(self) -> bool:
        """
        Check if state has stagnated.
        Criteria:
        1. History full (window size reached)
        2. All hashes in history are IDENTICAL
        """
        if len(self.history) < self.window_size:
            return False
            
        # Check if all elements are the same
        first = self.history[0]
        return all(h == first for h in self.history)

    def analyze_entropy(self) -> Dict[str, Any]:
        """
        Analyze current entropy state.
        Returns detailed signal for Metacognition.
        """
        if len(self.history) < 2:
            return {"status": "initializing", "repetition_count": 0, "window_size": self.window_size}
            
        # Check for repetition
        # Count consecutive identical states from the end
        repetition_count = 1
        last_hash = self.history[-1]
        for i in range(len(self.history) - 2, -1, -1):
            if self.history[i] == last_hash:
                repetition_count += 1
            else:
                break
                
        status = "volatile" # Default: changing
        if repetition_count >= self.window_size:
            status = "stagnant" # Critical: Full window is identical
        elif repetition_count >= (self.window_size / 2):
            status = "stable" # Warning: Half window is identical
            
        return {
            "status": status,
            "repetition_count": repetition_count,
            "window_size": self.window_size,
            "last_hash": last_hash[:8] if last_hash else None
        }

    def get_entropy_report(self) -> str:
        analysis = self.analyze_entropy()
        status = analysis["status"].upper()
        rep = analysis["repetition_count"]
        return f"State Entropy: {status} (Repetitions: {rep}/{self.window_size})"

    def reset(self):
        self.history.clear()
