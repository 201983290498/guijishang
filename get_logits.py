import os
import json
import torch
import traceback
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from transformers import AutoModelForCausalLM, AutoTokenizer
from tqdm.auto import tqdm

# 设置 GPU 使用 6 张空闲显卡（基于 nvidia-smi 的索引 2, 3, 4, 5, 6, 7）
os.environ["CUDA_VISIBLE_DEVICES"] = "2,3,4,5,6,7"

MODEL_PATH = "/home/fangjingluo/hjw/tracject_example/models/ZhipuAI/GLM-4.7-Flash"
INPUT_FILE = "data/parsed_messages.jsonl"
PLOT_DIR = "outputs/plots"

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

def calculate_entropy(logits):
    """
    计算 logits 的熵值。
    logits: (seq_len, vocab_size)
    Returns: (seq_len,)
    """
    probs = torch.softmax(logits, dim=-1)
    # entropy = -sum(p * log(p))
    entropy = -torch.sum(probs * torch.log(probs + 1e-9), dim=-1)
    return entropy

def plot_entropy_curve(entropies, output_path, title="Logits Entropy Curve"):
    """
    画出每个 token 的 logits 熵值变化曲线。
    entropies: (seq_len,) tensor or numpy array
    """
    plt.figure(figsize=(12, 6))
    plt.plot(entropies.cpu().numpy(), marker='o', markersize=2, linestyle='-', linewidth=1)
    plt.title(title)
    plt.xlabel("Token Index")
    plt.ylabel("Entropy")
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()

def main():
    if not os.path.exists(PLOT_DIR):
        os.makedirs(PLOT_DIR)

    print(f"Loading model from {MODEL_PATH}...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH, 
        device_map="auto", 
        trust_remote_code=True, 
        torch_dtype=torch.bfloat16
    ).eval()
    print(f"Model loaded successfully on devices: {model.device}")

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data_items = [ json.loads(line) for line in f.readlines() if line.strip()]
    print(f"Found {len(data_items)} messages to process.")

    for i, data in enumerate(tqdm(data_items)):
        try:
            print(f"\n--- Processing Message {i+1} ---")
            messages = data.get("messages", [])
            tools = data.get("tools", None)
            
            # 修复 tool_calls 中的 arguments 格式问题，适配 GLM-4 模板
            messages = glm4_msg_process(messages)
            # 应用聊天模板
            try:
                template_kwargs = {
                    "return_tensors": "pt", 
                    "add_generation_prompt": False
                }
                if tools:
                    template_kwargs["tools"] = tools
                inputs = tokenizer.apply_chat_template(messages, **template_kwargs)
            except Exception as e:
                print(f"Chat template application failed with tools, retrying without tools. Error: {e}")
                inputs = tokenizer.apply_chat_template(
                    messages, 
                    return_tensors="pt", 
                    add_generation_prompt=False
                )
            input_ids = inputs["input_ids"]
            if not isinstance(input_ids, torch.Tensor):
                 input_ids = torch.tensor(input_ids)

            if input_ids.dim() == 1:
                input_ids = input_ids.unsqueeze(0)
                
            input_ids = input_ids.to(model.device)
            # 生成并输出 logits
            with torch.no_grad():
                outputs = model(input_ids)
                logits = outputs.logits # (batch_size, seq_len, vocab_size)
            
            if logits is not None:
                seq_logits = logits[0] # (seq_len, vocab_size)
                # 计算熵
                seq_logits = seq_logits.detach().cpu().float()
                entropies = calculate_entropy(seq_logits)
                plot_filename = os.path.join(PLOT_DIR, f"entropy_trace_{i+1}.png")
                plot_entropy_curve(entropies, plot_filename, title=f"Entropy Trace - Message {i+1}")
                print(f"Entropy plot saved to {plot_filename}")
                
        except Exception as e:
            print(f"Error processing line {i+1}: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    main()
