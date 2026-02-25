#!/usr/bin/env python3
"""
Genesis Sanity Check & Smoke Test
=================================
File existence is not enough. To combat AI amnesia where we introduce syntax errors,
circular imports, or break class signatures, this script actually RUNS a smoke test.

It attempts to:
1. Initialize the `GenesisFactory`
2. Create the unified `NanoGenesis` agent via `create_common`
3. Verify that all essential sub-components (context, memory, scheduler, cognitition)
   were instantiated without crashing.

If this script fails, the Architecture is physically broken.
"""

import sys
import os
import asyncio
from pathlib import Path
import traceback

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def run_smoke_test():
    print("🔥 Starting Genesis Architecture Smoke Test...")
    
    try:
        from genesis.core.factory import GenesisFactory
        print("   [OK] GenesisFactory imported.")
        
        # We use enable_optimization=False to make it boot faster/lighter if possible,
        # but the core assembly process must run without raising exceptions.
        print("   [..] Attempting to construct full NanoGenesis Agent...")
        
        # Set dummy env vars if they don't exist, just to pass config validation
        os.environ.setdefault("ZHIPU_API_KEY", "dummy_key_for_test")
        os.environ.setdefault("DS_API_KEY", "dummy_key_for_test")
        
        # Test creation
        agent = GenesisFactory.create_common(
            user_id="SmokeTest_User",
            enable_optimization=True, # Test the full tree
            max_iterations=1
        )
        print("   [OK] Agent Assembled Successfully.")
        
        # Verify component bindings
        components = [
            ("Tools Registry", agent.tools),
            ("Context Pipeline", agent.context),
            ("Memory Store", agent.memory),
            ("Cognitive Processor", agent.cognition),
            ("Provider Router", agent.provider_router),
            ("System Scheduler", agent.scheduler),
            ("Adaptive Learner", agent.adaptive_learner),
            ("3D Mission Tree", agent.mission_manager),
            ("Trust Anchor", agent.trust_anchor)
        ]
        
        for name, comp in components:
            if comp is None:
                print(f"   [FAIL] Expected component '{name}' is None!")
                return False
            else:
                print(f"   [OK] {name} is bound and active ({comp.__class__.__name__}).")
                
        print("\n✅ All Architectural Components verified as USABLE and CONNECTED.")
        return True
        
    except Exception as e:
        print(f"\n❌ FATAL ARCHITECTURE FAILURE: Could not assemble Genesis.")
        print("This means the AI broke an import, signature, or dependency!")
        print("Traceback Details:")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if sys.platform != "win32":
        # Ensure we don't mess up async loops on exit
        pass
    
    success = run_smoke_test()
    if not success:
        sys.exit(1)
    else:
        sys.exit(0)
