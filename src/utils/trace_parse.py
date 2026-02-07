import os
import glob
import json
import re
from typing import Any, List, Optional, Dict
import dataclasses
import datetime

class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        if hasattr(o, "__dict__"):
            return o.__dict__
        if isinstance(o, (datetime.date, datetime.datetime)):
            return o.isoformat()
        return super().default(o)

def save_to_json(data: Any, file_path: str):
    """
    将数据序列化并保存为 JSON 文件。
    支持 dataclass 和自定义对象。
    """
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, cls=EnhancedJSONEncoder, ensure_ascii=False, indent=2)

def save_to_jsonl(data_list: List[Any], file_path: str):
    """
    将列表数据序列化并保存为 JSONL 文件。
    每一行是一个 JSON 对象。
    """
    with open(file_path, 'w', encoding='utf-8') as f:
        for item in data_list:
            f.write(json.dumps(item, cls=EnhancedJSONEncoder, ensure_ascii=False) + '\n')

def parse_json_response(response: str) -> Any:
    """
    解析字符串中的 JSON 内容，支持对象 {} 和数组 [] 格式。
    自动处理 markdown 代码块包裹的情况。
    """
    if not response:
        return {"error": "Empty response"}
    
    text = response.strip()
    code_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    code_match = re.search(code_block_pattern, text)
    if code_match:
        content = code_match.group(1).strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
    # 策略 B：贪婪匹配（处理嵌套的 ``` 情况，例如 mermaid 图表）。
    code_block_pattern_greedy = r'```(?:json)?\s*([\s\S]*)\s*```'
    code_match_greedy = re.search(code_block_pattern_greedy, text)
    if code_match_greedy:
        content_greedy = code_match_greedy.group(1).strip()
        try:
            return json.loads(content_greedy)
        except json.JSONDecodeError:
            pass

    candidates = []
    if code_match:
        candidates.append(code_match.group(1).strip())
    if code_match_greedy:
        greedy_content = code_match_greedy.group(1).strip()
        if not candidates or greedy_content != candidates[0]:
            candidates.append(greedy_content)
    
    # 如果未找到代码块，则使用原始文本。
    if not candidates:
        candidates.append(text)
        
    for content in candidates:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        obj_pattern = r'\{[\s\S]*\}'
        obj_match = re.search(obj_pattern, content)
        if obj_match:
            try:
                return json.loads(obj_match.group(0))
            except json.JSONDecodeError:
                pass
        
        # 4. 尝试提取 JSON 数组 [...]
        arr_pattern = r'\[[\s\S]*\]'
        arr_match = re.search(arr_pattern, content)
        if arr_match:
            try:
                return json.loads(arr_match.group(0))
            except json.JSONDecodeError:
                pass
    return {"error": "Invalid JSON format", "raw": response}


def find_trace_files(root_dir: str) -> List[str]:
    """
    Recursively finds all trace JSON files in the directory.
    """
    trace_files = []
    
    search_pattern = os.path.join(root_dir, "**", "*.json")
    for fpath in glob.iglob(search_pattern, recursive=True):
        filename = os.path.basename(fpath)
        if filename.startswith("trace_"):
            trace_files.append(fpath)
    return trace_files

def get_tools_schema(include_tools: Optional[List[str]] | str = None, json_path="data/all_tools_schema.json") -> List[Dict]:
    """
    Load tool schemas from the local JSON file.
    
    Args:
        include_tools: List of tool names to include. If None, returns all tools.
        
    Returns:
        List of tool schema dictionaries.
    """
    
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Tool schema file not found at {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        all_schemas = json.load(f)
    if include_tools is None:
        return all_schemas
    if type(include_tools) == str:
        include_tools = [tool.strip() for tool in include_tools.split(",")]
    filtered_schemas = []
    for schema in all_schemas:
        tool_name = schema.get('function', {}).get('name')
        if tool_name and tool_name in include_tools:
            filtered_schemas.append(schema)
    return filtered_schemas



def parser_answer(response):
    assistant_msg = {
        'role': 'assistant', 
        'content': response.get('content', ''), 
        "reasoning_content": response.get("reasoning_content", None),
        "thought_signature": response.get("thought_signature", None)
    }
    if 'tool_calls' in response and response['tool_calls']:
        assistant_msg['tool_calls'] = response['tool_calls']
    return assistant_msg


def filter_reasoning(messages: list, enable_filter: bool = True) -> list:
    """
    Filter reasoning_content from messages if enable_filter is True.
    Handles both dicts and objects.
    """
    if not enable_filter:
        return messages
    # 1. Find the last user conversation message
    last_user_idx = -1
    for i, msg in enumerate(messages):
        if msg['role'] == 'user' and msg['content'] and not msg['content'].startswith('[Tool Execution Result'):
            last_user_idx = i

    sanitized_messages = []
    for i, msg in enumerate(messages):
        msg_copy = msg.copy()
        if i <= last_user_idx and "reasoning_content" in msg_copy:
            msg_copy['reasoning_content'] = None
            msg_copy['thought_signature'] = None
        sanitized_messages.append(msg_copy) 
    return sanitized_messages