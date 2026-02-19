import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import json
import csv
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime
import os
from typing import Dict, List, Any, Optional
import logging

class DataPipelineTool:
    """数据管道工具 - 支持多种数据源的抓取、处理和导出"""
    
    name = "data_pipeline_tool"
    description = "灵活的数据抓取与处理工具，支持JSON、HTML、CSV等多种格式"
    parameters = {
        "type": "object",
        "properties": {
            "config": {
                "type": "object",
                "description": "数据抓取配置，包含target_url, method, data_type, extraction_rules等"
            },
            "output_path": {
                "type": "string", 
                "description": "输出文件路径（可选）"
            },
            "test_mode": {
                "type": "boolean",
                "description": "测试模式，不实际保存文件",
                "default": False
            }
        },
        "required": ["config"]
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def execute(self, config: Dict[str, Any], output_path: Optional[str] = None, test_mode: bool = False) -> Dict[str, Any]:
        """执行数据抓取任务"""
        
        try:
            # 提取配置
            target_url = config.get("target_url")
            method = config.get("method", "GET")
            data_type = config.get("data_type", "json")
            extraction_rules = config.get("extraction_rules", {})
            
            if not target_url:
                return {"success": False, "error": "缺少 target_url 配置"}
            
            # 执行请求
            response = self._make_request(target_url, method)
            if not response.get("success"):
                return response
            
            raw_data = response["data"]
            
            # 根据数据类型处理
            processed_data = self._process_data(raw_data, data_type, extraction_rules)
            
            # 生成输出
            result = {
                "success": True,
                "timestamp": datetime.now().isoformat(),
                "config": config,
                "data": processed_data,
                "stats": {
                    "data_points": len(processed_data) if isinstance(processed_data, list) else 1,
                    "processing_time": response.get("processing_time", 0)
                }
            }
            
            # 保存到文件（如果不是测试模式）
            if not test_mode and output_path:
                save_result = self._save_to_file(processed_data, output_path, config.get("output_format", "json"))
                result["output_file"] = output_path if save_result["success"] else None
                result["save_result"] = save_result
            
            return result
            
        except Exception as e:
            return {"success": False, "error": str(e), "timestamp": datetime.now().isoformat()}
    
    def _make_request(self, url: str, method: str) -> Dict[str, Any]:
        """发送HTTP请求"""
        start_time = time.time()
        
        try:
            if method.upper() == "GET":
                response = requests.get(url, timeout=10)
            elif method.upper() == "POST":
                response = requests.post(url, timeout=10)
            else:
                return {"success": False, "error": f"不支持的HTTP方法: {method}"}
            
            response.raise_for_status()
            
            processing_time = time.time() - start_time
            
            return {
                "success": True,
                "data": response.content,
                "status_code": response.status_code,
                "processing_time": processing_time
            }
            
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"请求失败: {str(e)}", "processing_time": time.time() - start_time}
    
    def _process_data(self, raw_data: bytes, data_type: str, extraction_rules: Dict[str, str]) -> Any:
        """根据数据类型处理原始数据"""
        
        if data_type == "json":
            try:
                json_data = json.loads(raw_data.decode('utf-8'))
                return self._extract_from_json(json_data, extraction_rules)
            except json.JSONDecodeError:
                return {"error": "JSON解析失败", "raw_data": raw_data[:500]}
                
        elif data_type == "html":
            try:
                soup = BeautifulSoup(raw_data, 'html.parser')
                return self._extract_from_html(soup, extraction_rules)
            except Exception as e:
                return {"error": f"HTML解析失败: {str(e)}", "raw_data": raw_data[:500]}
                
        elif data_type == "csv":
            try:
                csv_text = raw_data.decode('utf-8')
                return self._extract_from_csv(csv_text, extraction_rules)
            except Exception as e:
                return {"error": f"CSV解析失败: {str(e)}", "raw_data": raw_data[:500]}
                
        else:
            return {"error": f"不支持的数据类型: {data_type}", "raw_data": raw_data[:500]}
    
    def _extract_from_json(self, json_data: Any, rules: Dict[str, str]) -> List[Dict[str, Any]]:
        """从JSON中提取数据"""
        results = []
        
        # 简化版JSON路径提取（实际应使用jsonpath库）
        for key, path in rules.items():
            if path == "*":
                results.append({key: json_data})
            else:
                # 简单实现：按点分割路径
                parts = path.split('.')
                current = json_data
                for part in parts:
                    if part == "*" and isinstance(current, list):
                        # 处理数组
                        extracted = []
                        for item in current:
                            if isinstance(item, dict) and key in item:
                                extracted.append(item[key])
                        results.append({key: extracted})
                        break
                    elif isinstance(current, dict) and part in current:
                        current = current[part]
                    else:
                        results.append({key: None})
                        break
                else:
                    results.append({key: current})
        
        # 合并结果
        if results and len(results) > 1:
            merged = {}
            for item in results:
                merged.update(item)
            return [merged]
        elif results:
            return results
        else:
            return [{"raw_json": json_data}]
    
    def _extract_from_html(self, soup: BeautifulSoup, rules: Dict[str, str]) -> List[Dict[str, Any]]:
        """从HTML中提取数据"""
        results = []
        
        for key, selector in rules.items():
            elements = soup.select(selector)
            if elements:
                extracted = []
                for elem in elements:
                    if elem.name in ['a', 'link']:
                        value = elem.get('href', '').strip()
                    elif elem.name in ['img']:
                        value = elem.get('src', '').strip()
                    else:
                        value = elem.get_text(strip=True)
                    extracted.append(value)
                results.append({key: extracted})
            else:
                results.append({key: []})
        
        # 合并结果（假设所有选择器提取相同数量的元素）
        if results:
            merged_results = []
            first_key = list(results[0].keys())[0]
            item_count = len(results[0][first_key])
            
            for i in range(item_count):
                item = {}
                for result_dict in results:
                    for key, values in result_dict.items():
                        if i < len(values):
                            item[key] = values[i]
                        else:
                            item[key] = None
                merged_results.append(item)
            
            return merged_results
        
        return [{"raw_html": str(soup)[:1000]}]
    
    def _extract_from_csv(self, csv_text: str, rules: Dict[str, str]) -> List[Dict[str, Any]]:
        """从CSV中提取数据"""
        import io
        
        try:
            # 使用csv模块解析
            csv_reader = csv.DictReader(io.StringIO(csv_text))
            rows = list(csv_reader)
            
            # 如果指定了规则，只提取需要的列
            if rules:
                filtered_rows = []
                for row in rows:
                    filtered_row = {}
                    for key, column_name in rules.items():
                        if column_name in row:
                            filtered_row[key] = row[column_name]
                        else:
                            filtered_row[key] = None
                    filtered_rows.append(filtered_row)
                return filtered_rows
            else:
                return rows
                
        except Exception as e:
            return [{"error": f"CSV处理失败: {str(e)}", "raw_csv": csv_text[:500]}]
    
    def _save_to_file(self, data: Any, output_path: str, format_type: str = "json") -> Dict[str, Any]:
        """保存数据到文件"""
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            if format_type == "json":
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    
            elif format_type == "csv":
                if isinstance(data, list) and data:
                    with open(output_path, 'w', encoding='utf-8', newline='') as f:
                        writer = csv.DictWriter(f, fieldnames=data[0].keys())
                        writer.writeheader()
                        writer.writerows(data)
                else:
                    return {"success": False, "error": "CSV格式需要列表数据"}
                    
            elif format_type == "txt":
                with open(output_path, 'w', encoding='utf-8') as f:
                    if isinstance(data, (dict, list)):
                        f.write(json.dumps(data, ensure_ascii=False, indent=2))
                    else:
                        f.write(str(data))
                        
            else:
                return {"success": False, "error": f"不支持的输出格式: {format_type}"}
            
            return {"success": True, "file_size": os.path.getsize(output_path)}
            
        except Exception as e:
            return {"success": False, "error": str(e)}