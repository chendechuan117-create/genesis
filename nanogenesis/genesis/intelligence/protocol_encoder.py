"""
协议编码器 - 通过协议压缩传输，不丢失信息

核心思想：
- 不是让 LLM 删减内容
- 而是通过协议编码减少 token
- 云端 API 通过解码表还原完整信息
"""

from typing import Dict, List, Optional
import json


class ProtocolEncoder:
    """协议编码器"""
    
    def __init__(self):
        # 定义协议字典
        self.protocols = {
            # 错误类型
            'permission denied': '[ERR:PERM]',
            'permission_denied': '[ERR:PERM]',
            'connection refused': '[ERR:CONN]',
            'connection_refused': '[ERR:CONN]',
            'module not found': '[ERR:MOD]',
            'module_not_found': '[ERR:MOD]',
            'no such file': '[ERR:NOFILE]',
            'file not found': '[ERR:NOFILE]',
            'timeout': '[ERR:TIMEOUT]',
            'out of memory': '[ERR:OOM]',
            'syntax error': '[ERR:SYNTAX]',
            'import error': '[ERR:IMPORT]',
            'attribute error': '[ERR:ATTR]',
            'type error': '[ERR:TYPE]',
            'value error': '[ERR:VALUE]',
            'key error': '[ERR:KEY]',
            
            # 领域
            'docker': '[DOM:DKR]',
            'python': '[DOM:PY]',
            'javascript': '[DOM:JS]',
            'typescript': '[DOM:TS]',
            'git': '[DOM:GIT]',
            'linux': '[DOM:LNX]',
            'network': '[DOM:NET]',
            'database': '[DOM:DB]',
            'web': '[DOM:WEB]',
            'api': '[DOM:API]',
            
            # 用户偏好
            'prefer config': '[PREF:CFG]',
            'prefer configuration': '[PREF:CFG]',
            'prefer code': '[PREF:CODE]',
            'prefer simple': '[PREF:SIMP]',
            'prefer minimal': '[PREF:MIN]',
            'prefer detailed': '[PREF:DTL]',
            'prefer fast': '[PREF:FAST]',
            'prefer thorough': '[PREF:THOR]',
            
            # 环境
            'linux': '[ENV:LNX]',
            'windows': '[ENV:WIN]',
            'macos': '[ENV:MAC]',
            'user not in group': '[ENV:NOGRP]',
            'port in use': '[ENV:PORT]',
            'disk full': '[ENV:DISK]',
            'network unreachable': '[ENV:NONET]',
            
            # 操作
            'install': '[OP:INST]',
            'uninstall': '[OP:UNINST]',
            'configure': '[OP:CFG]',
            'debug': '[OP:DBG]',
            'deploy': '[OP:DEPLOY]',
            'test': '[OP:TEST]',
            'build': '[OP:BUILD]',
            
            # 状态
            'running': '[ST:RUN]',
            'stopped': '[ST:STOP]',
            'failed': '[ST:FAIL]',
            'pending': '[ST:PEND]',
            'success': '[ST:OK]',
        }
        
        # 反向映射（解码用）
        self.decode_map = {v: k for k, v in self.protocols.items()}
    
    def encode(self, context: Dict) -> str:
        """
        编码上下文
        
        Args:
            context: 包含以下字段的字典
                - problem: 问题描述
                - env_info: 环境信息（可选）
                - diagnosis: 诊断结果（可选）
                - strategy: 策略（可选）
                - user_pref: 用户偏好（可选）
        
        Returns:
            编码后的字符串
        """
        encoded_parts = []
        
        # 编码问题
        if 'problem' in context:
            problem = context['problem']
            encoded_problem = self._encode_text(problem)
            encoded_parts.append(f"[Q]{encoded_problem}")
        
        # 编码环境信息
        if 'env_info' in context and context['env_info']:
            env_codes = self._encode_env_info(context['env_info'])
            if env_codes:
                encoded_parts.append(f"[E]{env_codes}")
        
        # 编码诊断结果
        if 'diagnosis' in context and context['diagnosis']:
            diagnosis = self._encode_text(str(context['diagnosis']))
            encoded_parts.append(f"[D]{diagnosis}")
        
        # 编码策略
        if 'strategy' in context and context['strategy']:
            strategy = self._encode_text(str(context['strategy']))
            encoded_parts.append(f"[S]{strategy}")
        
        # 编码用户偏好
        if 'user_pref' in context and context['user_pref']:
            pref = self._encode_text(str(context['user_pref']))
            encoded_parts.append(f"[U]{pref}")
        
        return '|'.join(encoded_parts)
    
    def _encode_text(self, text: str) -> str:
        """编码文本"""
        encoded = text
        
        # 按长度排序，优先匹配长的短语
        sorted_protocols = sorted(
            self.protocols.items(),
            key=lambda x: len(x[0]),
            reverse=True
        )
        
        for phrase, code in sorted_protocols:
            # 不区分大小写匹配
            if phrase.lower() in encoded.lower():
                # 保持原文大小写，只替换匹配部分
                import re
                pattern = re.compile(re.escape(phrase), re.IGNORECASE)
                encoded = pattern.sub(code, encoded)
        
        return encoded
    
    def _encode_env_info(self, env_info: Dict) -> str:
        """编码环境信息"""
        codes = []
        
        for key, value in env_info.items():
            # 尝试编码 key
            encoded_key = self._encode_text(key)
            
            # 尝试编码 value
            if isinstance(value, str):
                encoded_value = self._encode_text(value)
            else:
                encoded_value = str(value)
            
            # 如果有编码，使用编码；否则使用原文
            if encoded_key != key or encoded_value != str(value):
                codes.append(f"{encoded_key}:{encoded_value}")
        
        return ','.join(codes) if codes else ''
    
    def get_decoder_prompt(self) -> str:
        """
        返回解码器提示词（给云端 API）
        
        Returns:
            解码器提示词
        """
        return f"""## 协议解码表

你将收到使用协议编码的上下文，格式如下：
- [Q]问题描述 - 用户问题
- [E]环境信息 - 环境状态
- [D]诊断结果 - 问题诊断
- [S]策略建议 - 推荐策略
- [U]用户偏好 - 用户偏好

编码映射表：
```json
{json.dumps(self.protocols, indent=2, ensure_ascii=False)}
```

当你看到编码如 [ERR:PERM] 时，解码为 "permission denied"。
当你看到编码如 [DOM:DKR] 时，解码为 "docker"。

请先在内部解码，然后按解码后的完整信息进行思考和回答。
"""
    
    def decode(self, encoded_text: str) -> str:
        """
        解码文本（用于测试）
        
        Args:
            encoded_text: 编码后的文本
        
        Returns:
            解码后的文本
        """
        decoded = encoded_text
        
        for code, phrase in self.decode_map.items():
            decoded = decoded.replace(code, phrase)
        
        return decoded
    
    def estimate_compression_ratio(self, original: str, encoded: str) -> float:
        """
        估算压缩比
        
        Args:
            original: 原始文本
            encoded: 编码后的文本
        
        Returns:
            压缩比（0-1，越小压缩越多）
        """
        # 简单估算：按字符数计算
        original_len = len(original)
        encoded_len = len(encoded)
        
        if original_len == 0:
            return 1.0
        
        return encoded_len / original_len


# 示例用法
if __name__ == '__main__':
    encoder = ProtocolEncoder()
    
    # 测试编码
    context = {
        'problem': 'Docker container failed to start, permission denied error',
        'env_info': {
            'os': 'linux',
            'user_not_in_group': 'docker'
        },
        'diagnosis': 'UID/GID mapping issue',
        'strategy': 'Modify docker-compose.yml user field',
        'user_pref': 'prefer configuration file approach'
    }
    
    encoded = encoder.encode(context)
    print("原始上下文:")
    print(json.dumps(context, indent=2))
    print("\n编码后:")
    print(encoded)
    
    # 估算压缩比
    original_text = json.dumps(context)
    ratio = encoder.estimate_compression_ratio(original_text, encoded)
    print(f"\n压缩比: {ratio:.2%}")
    print(f"Token 节省: {(1-ratio)*100:.1f}%")
    
    # 解码测试
    print("\n解码后:")
    print(encoder.decode(encoded))
    
    # 解码器提示词
    print("\n" + "="*60)
    print("解码器提示词（给云端 API）:")
    print("="*60)
    print(encoder.get_decoder_prompt())
