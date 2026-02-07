import sys
import os
from tqdm.auto import tqdm
import json
import argparse

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.trace_parser import TraceParser
from src.utils.trace_parse import find_trace_files, save_to_json, save_to_jsonl, get_tools_schema

def main(args):
    target_dir = args.target_dir
    output_base_dir = "/home/fangjingluo/hjw/tracject_example/dataset/SFT"
         
    parser = TraceParser(filter_reasoning=args.filter_reasoning)
    total_files = find_trace_files(target_dir)
    total_messages = []
    print(f"Found {len(total_files)} trace files.")
    
    for fpath in tqdm(total_files):
        # print(f"Processing {fpath}")
        task = parser.parse_file(fpath)
        total_messages.extend([{"messages": msg, "tools": get_tools_schema(task.metadata.get('tools', None))} for msg in task.messages])
        rel_path = os.path.relpath(fpath, "/home/fangjingluo/hjw/tracject_example/dataset/最终的实验")
        save_path = os.path.join(output_base_dir, rel_path.replace(".json", "_parsed.json"))
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        save_to_json(task, save_path)
    if args.output_file:
        save_to_jsonl(total_messages, args.output_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process trace files.")
    parser.add_argument("--target_dir", type=str, default="dataset/最终的实验/主实验/trace_85_glm-4.7_think_final1", help="Target directory containing trace files")
    parser.add_argument("--filter_reasoning", action="store_true", help="Filter reasoning content")
    parser.add_argument("--output_file", type=str, default="data/parsed_messages.jsonl", help="Output file for parsed messages")
    args = parser.parse_args()
    main(args)
