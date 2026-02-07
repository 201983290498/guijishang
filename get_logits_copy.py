import os
import json
import torch
import traceback
import matplotlib
import gc
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from transformers import AutoModelForCausalLM, AutoTokenizer
from tqdm.auto import tqdm
from contextlib import contextmanager

os.environ["CUDA_VISIBLE_DEVICES"] = "2,3,4,5,6,7"
MAX_TOKENS = 128000
MODEL_PATH = "/home/fangjingluo/hjw/tracject_example/models/ZhipuAI/GLM-4.7-Flash"
INPUT_FILE = "data/parsed_messages.jsonl"
PLOT_DIR = "outputs/plots"
BATCH_SIZE = 1

def glm4_msg_process(messages):
    """
    处理 GLM-4 模型的消息格式，修复 tool_calls 中 arguments 的格式问题。
    """
    for msg in messages:
        if "tool_calls" in msg:
            for tc in msg["tool_calls"]:
                if "function" in tc:
                    func = tc["function"]
                    if "arguments" in func and isinstance(func["arguments"], str):
                        try:
                            func["arguments"] = json.loads(func["arguments"])
                        except json.JSONDecodeError:
                            pass
    return messages

@contextmanager
def safe_inference():
    """推理上下文管理器：确保所有资源被清理"""
    tensors_to_clean = []
    try:
        yield tensors_to_clean
    finally:
        # 清理所有注册的张量
        for t in tensors_to_clean:
            if isinstance(t, torch.Tensor):
                del t
        gc.collect()
        torch.cuda.empty_cache()
        # 同步所有卡确保清理完成
        for i in range(torch.cuda.device_count()):
            torch.cuda.synchronize(i)

def calculate_entropy(logits):
    probs = torch.softmax(logits, dim=-1)
    entropy = -torch.sum(probs * torch.log(probs.clamp_min(1e-10)), dim=-1)
    return entropy

def get_visualization_data(messages, tokenizer, tools=None):
    segments = []
    tool_sequence_count = 0
    start_idx = 0
    
    # We need to iterate through all messages to get their ranges and colors
    for i in range(len(messages)):
        curr_role = messages[i]['role']
        
        # Determine content color
        content_color = 'black' # default
        if curr_role == 'user':
            content_color = 'red'
            tool_sequence_count = 0
        elif curr_role == 'assistant':
            content_color = 'blue'
            tool_sequence_count = 0
        elif curr_role == 'tool':
            # Check if previous was tool to handle alternating colors
            if i > 0 and messages[i-1]['role'] == 'tool':
                tool_sequence_count += 1
            else:
                tool_sequence_count = 0
                
            if tool_sequence_count % 2 == 1:
                content_color = '#FFD700' # Gold/Yellow
            else:
                content_color = 'black'
        
        # Determine boundary color (line at the end of this message)
        boundary_color = None
        if i < len(messages) - 1:
            next_role = messages[i+1]['role']
            if (curr_role == 'user' and next_role == 'assistant') or (curr_role == 'assistant' and next_role == 'user'):
                boundary_color = 'red'
            elif (curr_role == 'assistant' and next_role == 'tool') or (curr_role == 'tool' and next_role == 'assistant'):
                boundary_color = 'blue'
            elif curr_role == 'tool' and next_role == 'tool':
                boundary_color = 'black'
        
        # Calculate end index
        try:
            prefix_ids = tokenizer.apply_chat_template(
                messages[:i+1], 
                tools=tools, 
                add_generation_prompt=False, 
                tokenizer_kwargs={"return_tensors": None}
            )
            end_idx = len(prefix_ids)
            
            # Append segment data
            segments.append({
                'start': start_idx,
                'end': end_idx,
                'content_color': content_color,
                'boundary_color': boundary_color
            })
            
            start_idx = end_idx
        except Exception:
            pass
            
    return segments

def plot_entropy_curve(entropies, output_path, segments=None, title="Entropy"):
    ent = entropies.cpu().numpy()    
    fig = plt.figure(figsize=(12, 6))
    try:
        if segments:
            for seg in segments:
                start = seg['start']
                end = seg['end']
                color = seg['content_color']
                
                if start >= len(ent):
                    continue
                current_ent = ent[start:min(end, len(ent))]
                x_axis = range(start, start + len(current_ent))
                
                if len(x_axis) > 0:
                    plt.plot(x_axis, current_ent, color=color, linewidth=0.8, alpha=0.7)
                
                if seg['boundary_color'] and end < len(ent):
                    plt.axvline(x=end, color=seg['boundary_color'], linestyle='-', alpha=1.0, linewidth=6.0, zorder=10)
        else:
            plt.plot(ent, linewidth=0.8, alpha=0.7)
            
        plt.title(title)
        plt.xlabel("Token")
        plt.ylabel("Entropy")
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.tight_layout()
        plt.savefig(output_path, dpi=150)
    finally:
        plt.close(fig)
        plt.close('all')

def main():
    if not os.path.exists(PLOT_DIR):
        os.makedirs(PLOT_DIR)

    print("Loading model...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH, 
        device_map="auto", 
        trust_remote_code=True, 
        torch_dtype=torch.bfloat16,
        # max_memory={0: "75GiB", 1: "75GiB", 2: "75GiB", 3: "75GiB"},  # 预留 5GB 安全余量
    ).eval()
    model.config.use_cache = False  # 重要：防止 past_key_values 累积
    

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data_items = [json.loads(line) for line in f if line.strip()]
    print(f"Total items: {len(data_items)}")

    # Ensure tokenizer has pad_token
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = 'right'

    for i in tqdm(range(0, len(data_items), BATCH_SIZE)):
        batch_items = data_items[i : i + BATCH_SIZE]
        batch_inputs = []
        batch_boundaries = []
        batch_indices = []
        
        for j, data in enumerate(batch_items):
            idx = i + j
            try:
                messages = data.get("messages", [])
                tools = data.get("tools", None)
                messages = glm4_msg_process(messages)
                
                segments = get_visualization_data(messages, tokenizer, tools)
                batch_boundaries.append(segments)
                batch_indices.append(idx)

                kwargs = {
                    "return_tensors": "pt", 
                    "add_generation_prompt": False,
                    "truncation": True,
                    "max_length": MAX_TOKENS,
                }
                if tools:
                    kwargs["tools"] = tools
                
                try:
                    inputs = tokenizer.apply_chat_template(messages, **kwargs)
                except Exception:
                    inputs = tokenizer.apply_chat_template(
                        messages, return_tensors="pt", 
                        add_generation_prompt=False, truncation=True, max_length=MAX_TOKENS
                    )

                if hasattr(inputs, "input_ids"):
                    input_ids = inputs.input_ids
                elif isinstance(inputs, dict) and "input_ids" in inputs:
                    input_ids = inputs["input_ids"]
                else:
                    input_ids = inputs
                
                if isinstance(input_ids, torch.Tensor):
                    input_ids = input_ids.squeeze(0)
                else:
                    # Handle case where input_ids might be a tokenizers.Encoding object
                    if hasattr(input_ids, 'ids'):
                        input_ids = input_ids.ids
                    input_ids = torch.tensor(input_ids)
                
                batch_inputs.append(input_ids)
                
            except Exception as e:
                print(f"Error preparing item {idx}: {e}")
                traceback.print_exc()
                continue
        
        if not batch_inputs:
            continue

        with safe_inference():
            try:
                padded_inputs = torch.nn.utils.rnn.pad_sequence(
                    batch_inputs, batch_first=True, padding_value=tokenizer.pad_token_id
                ).to(model.device)
                
                with torch.inference_mode():
                    outputs = model(padded_inputs)
                    logits = outputs.logits
                    
                    for k, item_logits in enumerate(logits):
                        valid_len = len(batch_inputs[k])
                        seq_logits = item_logits[:valid_len]
                        entropies = calculate_entropy(seq_logits)
                        entropies_cpu = entropies.detach().cpu().float()
                        idx = batch_indices[k]
                        segments = batch_boundaries[k]
                        plot_path = os.path.join(PLOT_DIR, f"entropy_trace_{idx+1}.png")
                        plot_entropy_curve(entropies_cpu, plot_path, segments=segments, title=f"Msg {idx+1}")
                    
                    del outputs, logits
            except Exception as e:
                print(f"Error in batch inference at index {i}: {e}")
                traceback.print_exc()
                torch.cuda.empty_cache()

if __name__ == "__main__":
    main()