#!/usr/bin/env python3
"""
Genesis Architecture Enforcer (Anti-Amnesia Protocol)
=====================================================
AI coding assistants have a nature of forgetting or hallucinating codebase structures.
To combat this, this script mechanically enforces that `ARCHITECTURE.md` is the 
ABSOLUTE SOURCE OF TRUTH.

It scans the core directories and cross-references them with `ARCHITECTURE.md`.
If a `.py` file exists in `genesis/core` or `genesis/intelligence` but is NOT 
documented in `ARCHITECTURE.md`, this script will fail, forcing the AI to update 
the documentation.
"""

import os
import re
from pathlib import Path

# Paths to check
PROJECT_ROOT = Path(__file__).parent.parent
ARCH_FILE = PROJECT_ROOT / "ARCHITECTURE.md"
CORE_DIR = PROJECT_ROOT / "genesis" / "core"
INTELLIGENCE_DIR = PROJECT_ROOT / "genesis" / "intelligence"

# Files to ignore (e.g., init files or pure data files)
IGNORE_FILES = {"__init__.py"}

def get_documented_files(arch_path: Path) -> set:
    """Parses ARCHITECTURE.md and extracts all mentioned nanogenesis/genesis/**/*.py files."""
    documented = set()
    if not arch_path.exists():
        print(f"❌ CRITICAL ERROR: {arch_path.name} is missing!")
        return documented
        
    with open(arch_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Look for paths mentioned like `nanogenesis/genesis/.../xxx.py`
    # We'll be forgiving and just extract the raw filenames mentioned
    # Specifically looking for `genesis/core/xxx.py` or just `xxx.py` in the document
    matches = re.finditer(r'`(?:[a-zA-Z0-9_\-/]+)?(genesis/(?:core|intelligence)/[a-zA-Z0-9_]+\.py)`', content)
    for match in matches:
        full_path = match.group(1)
        # Extract just the filename to be simple, but mapping by relative path is safer
        # Let's use the relative path starting from 'genesis/'
        documented.add(full_path)
        
    return set(documented)

def get_actual_files(directories: list) -> set:
    """Scans directories and returns set of relative paths of all .py files."""
    actual = set()
    for directory in directories:
        if not directory.exists():
            continue
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".py") and file not in IGNORE_FILES:
                    full_path = Path(root) / file
                    # Get path relative to PROJECT_ROOT
                    rel_path = full_path.relative_to(PROJECT_ROOT).as_posix()
                    actual.add(rel_path)
    return actual

def main():
    print("🛡️ Genesis Architecture Enforcer Running...")
    
    documented_files = get_documented_files(ARCH_FILE)
    actual_files = get_actual_files([CORE_DIR, INTELLIGENCE_DIR])
    
    errors = 0
    
    # Check 1: Undocumented Files (Amnesia Detected)
    undocumented = actual_files - documented_files
    if undocumented:
        print("\n❌ [AMNESIA DETECTED] The following files exist in the codebase but are MISSING from ARCHITECTURE.md:")
        for file in sorted(undocumented):
            print(f"   - {file}")
        print("   -> Fix: You MUST document these files in ARCHITECTURE.md before proceeding.")
        errors += 1
        
    # Check 2: Ghost Files (Hallucination Detected)
    ghosts = documented_files - actual_files
    if ghosts:
        print("\n👻 [HALLUCINATION DETECTED] The following files are in ARCHITECTURE.md but do NOT exist in the codebase:")
        for file in sorted(ghosts):
            print(f"   - {file}")
        print("   -> Fix: Remove them from ARCHITECTURE.md or create the actual files.")
        errors += 1
        
    if errors > 0:
        print("\n💥 Architecture validation FAILED. The physical codebase and the Source of Truth are out of sync.")
        exit(1)
    else:
        print("\n✅ Architecture validation PASSED. `ARCHITECTURE.md` perfectly matches the physical codebase.")
        exit(0)

if __name__ == "__main__":
    main()
