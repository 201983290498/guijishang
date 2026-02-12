import json
import os
import argparse
from typing import List, Dict, Any

def clean_messages_reverse_scan(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    通过倒序扫描清洗消息历史。
    
    新逻辑 (User Instruction):
    1. 两个 Window 标记之间，通常只保留“最后一个 Assistant 消息”及其后续的 Tool 消息（可能有多个）。
       在此之前的消息被视为冗余/重复，予以删除。
    2. 如果该区间内没有 Assistant 消息，则回退到“数量检查”逻辑（保留最后 expected_count 个）。
    3. 第一个 Window 标记之前的消息不做处理。
    """
    if not messages:
        return []
    
    tags = []
    for i, msg in enumerate(messages):
        if isinstance(msg, dict) and 'tag' in msg and 'window' in msg['tag']:
            tags.append((i, msg['tag']['window']))

    if not tags:
        return messages[:]
    keep_mask = [True] * len(messages)
    for k in range(len(tags) - 1, 0, -1):
        curr_idx, _ = tags[k]
        prev_idx, _ = tags[k-1]
        last_assistant_idx = -1
        for i in range(curr_idx, prev_idx, -1):
            if messages[i].get('role') == 'assistant':
                last_assistant_idx = i
                break
        if last_assistant_idx != -1:
            for i in range(prev_idx + 1, last_assistant_idx):
                keep_mask[i] = False
    new_messages = [msg for i, msg in enumerate(messages) if keep_mask[i]]
    return new_messages

def process_trace_file(file_path: str):
    """
    处理单个 trace 文件
    """
    print(f"正在处理文件: {file_path} ...")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"读取失败 {file_path}: {e}")
        return
    if 'conversation_trace' not in data:
        print(f"跳过: 缺少 conversation_trace 字段")
        return

    trace = data['conversation_trace']
    if not trace:
        print(f"跳过: trace 为空")
        return

    file_modified = False
    for turn in trace:
        messages = turn.get('messages', [])
        if not messages:
            continue
        cleaned_messages = clean_messages_reverse_scan(messages)
        if len(cleaned_messages) != len(messages):
            print(f"  [Turn {turn.get('turn')}] 发现冗余并清洗: 原长度 {len(messages)} -> 新长度 {len(cleaned_messages)}")
            turn['messages'] = cleaned_messages
            file_modified = True

    if file_modified:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"修复并保存: {file_path}")
        except Exception as e:
            print(f"保存出错 {file_path}: {e}")
    else:
        print(f"无需修改: {file_path}")

def main():
    parser = argparse.ArgumentParser(description="修复 Trace 文件中的消息重复问题 (倒序扫描版)")
    parser.add_argument("--path", type=str, help="Trace 文件或目录的路径", default="./dataset/最终的实验")
    args = parser.parse_args()
    target_path = args.path
    
    if os.path.isfile(target_path):
        process_trace_file(target_path)
    elif os.path.isdir(target_path):
        for root, dirs, files in os.walk(target_path):
            for file in files:
                if file.endswith(".json") and file.startswith("trace_"):
                    process_trace_file(os.path.join(root, file))
    else:
        print(f"无效路径: {target_path}")

if __name__ == "__main__":
    main()
