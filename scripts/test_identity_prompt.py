import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "nanogenesis"))

from genesis.core.context import SimpleContextBuilder
from genesis.intelligence.adaptive_learner import AdaptiveLearner

def test_prompts():
    print("🚀 Verifying Identity Rebirth...")
    
    # 1. Check Context Builder (Default)
    context = SimpleContextBuilder()
    sys_prompt = context.pipeline.build_system_context("test input")
    
    print("\n[ContextBuilder Prompt Snippet]")
    print("-" * 40)
    print(sys_prompt[:300] + "...")
    print("-" * 40)
    
    if "AI engineering assistant" in sys_prompt:
        print("❌ FAIL: Old identity found in ContextBuilder.")
    elif "System Operator" in sys_prompt or "User Privileges" in sys_prompt:
        print("✅ PASS: New identity found in ContextBuilder.")
    else:
        print("❓ WARNING: Identity definition unclear in ContextBuilder.")

    # 2. Check Adaptive Learner (Override)
    learner = AdaptiveLearner()
    # Mock some pattern data to avoid file I/O issues if needed, but default is fine
    adaptive_prompt = learner.generate_adaptive_prompt()
    
    print("\n[AdaptiveLearner Prompt Snippet]")
    print("-" * 40)
    print(adaptive_prompt[:300] + "...")
    print("-" * 40)
    
    if "Be genuinely helpful" in adaptive_prompt and not "User Privileges" in adaptive_prompt:
         print("❌ FAIL: Old identity found in AdaptiveLearner.")
    elif "User Privileges" in adaptive_prompt:
         print("✅ PASS: New identity found in AdaptiveLearner.")
    else:
         print("❓ WARNING: Identity definition unclear in AdaptiveLearner.")

if __name__ == "__main__":
    test_prompts()
