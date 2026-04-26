import os
import json
import subprocess
import sys
from pathlib import Path
import re
import importlib.util

skills_dir = Path("/workspace/genesis/skills")
results = {
    "scan_timestamp": "2026-04-26",
    "total_files": 0,
    "format_compliant": [],
    "format_error": [],
    "syntax_error": [],
    "dep_missing": [],
    "summary": {}
}

py_files = sorted([f for f in skills_dir.iterdir() if f.suffix == '.py' and f.is_file()])
results["total_files"] = len(py_files)

for py_file in py_files:
    file_result = {
        "file": str(py_file.relative_to("/workspace")),
        "status": None,
        "error_type": None,
        "error_detail": None,
        "fix_suggestion": None
    }
    
    # 1. 语法检查: python -m py_compile
    compile_result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(py_file)],
        capture_output=True,
        text=True
    )
    
    if compile_result.returncode != 0:
        file_result["status"] = "FAILED"
        file_result["error_type"] = "SYNTAX_ERROR"
        file_result["error_detail"] = compile_result.stderr.strip()
        file_result["fix_suggestion"] = "修复Python语法错误，检查缩进、括号匹配、关键字使用"
        results["syntax_error"].append(file_result)
        continue
    
    # 2. 检查是否有Tool子类定义
    content = py_file.read_text(encoding='utf-8')
    tool_class_pattern = re.compile(r'class\s+\w+\s*\(\s*Tool\s*(?:,\s*\w+\s*)*\s*\)\s*:')
    has_tool_class = tool_class_pattern.search(content) is not None
    
    if not has_tool_class:
        file_result["status"] = "FAILED"
        file_result["error_type"] = "FORMAT_ERROR"
        file_result["error_detail"] = "No Tool subclass found (class must inherit from Tool)"
        file_result["fix_suggestion"] = "添加Tool基类继承: class MyTool(Tool):"
        results["format_error"].append(file_result)
        continue
    
    # 3. 尝试导入检查依赖
    try:
        spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        file_result["status"] = "PASSED"
        results["format_compliant"].append(file_result)
    except ImportError as e:
        file_result["status"] = "FAILED"
        file_result["error_type"] = "DEP_MISSING"
        file_result["error_detail"] = str(e)
        missing_pkg = str(e).split("'")[1] if "'" in str(e) else "required-package"
        file_result["fix_suggestion"] = f"安装缺失依赖: pip install {missing_pkg}"
        results["dep_missing"].append(file_result)
    except Exception as e:
        file_result["status"] = "FAILED"
        file_result["error_type"] = "RUNTIME_ERROR"
        file_result["error_detail"] = str(e)
        file_result["fix_suggestion"] = "检查模块初始化代码"
        results["dep_missing"].append(file_result)

results["summary"] = {
    "total_scanned": results["total_files"],
    "format_compliant_count": len(results["format_compliant"]),
    "format_error_count": len(results["format_error"]),
    "syntax_error_count": len(results["syntax_error"]),
    "dep_missing_count": len(results["dep_missing"]),
    "compliance_rate": f"{len(results['format_compliant'])/results['total_files']*100:.1f}%"
}

print(json.dumps(results, indent=2, ensure_ascii=False))
