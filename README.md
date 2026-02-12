# Trajectory Analysis Pipeline

本项目包含了一套完整的轨迹分析流程，主要用于处理、清洗和分析 SFT (Supervised Fine-Tuning) 训练数据中的轨迹信息。

## 目录结构

*   `fix_trace.py`: 用于修复和清洗原始轨迹文件中的冗余消息。
*   `src/parse_sft_msg.py`: 将处理后的轨迹文件解析为 SFT 训练所需的格式（jsonl）。
*   `get_logits.py`: 加载预训练模型，计算 parsed messages 的 logits 并绘制熵（entropy）曲线。
*   `dataset/`: 存放原始及处理后的轨迹数据。
*   `models/`: 存放预训练模型（需自行下载）。
*   `outputs/`: 存放分析结果（如熵的图像）。

## 流程概览

1.  **准备模型**: 下载所需的 GLM-4 或其他兼容模型。
2.  **修复轨迹 (Trace Fixing)**: 使用 `fix_trace.py` 清洗数据。
3.  **解析消息 (Parsing Messages)**: 使用 `src/parse_sft_msg.py` 将清洗后的数据转换为统一的 JSONL 格式。
4.  **计算熵 (Entropy Calculation)**: 使用 `get_logits.py` 计算生成的 Logits 熵并绘图。

---

## 详细步骤

### 1. 模型下载 (Model Download)

在运行分析脚本之前，请确保已下载所需的模型权重并放置在 `models/` 目录下。

例如，如果使用 `ZhipuAI/GLM-4.7-Flash`，可以使用 `huggingface-cli` 或 `modelscope` 进行下载。

```bash
# 示例：使用 huggingface-cli 下载
huggingface-cli download --resume-download ZhipuAI/GLM-4.7-Flash --local-dir models/ZhipuAI/GLM-4.7-Flash
```

请确保 `get_logits.py` 中的 `MODEL_PATH` 变量指向正确的模型路径。

### 2. 修复轨迹 (Fix Trace)

`fix_trace.py` 脚本用于扫描并修复轨迹文件中的冗余消息（例如去除重复的 Window 标记之间的非最后 Assistant 消息）。

**用法:**

```bash
python fix_trace.py --path <trace_file_or_directory>
```

*   `--path`: 指定需要处理的单个 `.json` 文件路径或包含 `.json` 文件的目录路径。默认为 `./dataset/最终的实验`。

**示例:**

```bash
# 处理默认目录下的所有文件
python fix_trace.py

# 处理特定目录
python fix_trace.py --path dataset/SFT/主实验
```

### 3. 解析 SFT 消息 (Parse SFT Messages)

使用 `src/parse_sft_msg.py` 将修复后的轨迹文件转换为 JSONL 格式，以便后续处理或训练使用。

**用法:**

```bash
python src/parse_sft_msg.py \
    --target_dir <input_directory> \
    --output_file <output_jsonl_path> \
    [--filter_reasoning]
```

*   `--target_dir`: 包含原始轨迹文件的目录（支持递归查找）。
*   `--output_file`: 输出的 JSONL 文件路径。默认为 `data/parsed_messages.jsonl`。
*   `--filter_reasoning`: (可选) 是否过滤掉 reasoning 内容。

**示例:**

```bash
python src/parse_sft_msg.py \
    --target_dir dataset/最终的实验 \
    --output_file data/parsed_messages.jsonl
```

### 4. 计算熵 (Calculate Entropy)

执行 `get_logits.py` 来加载模型并计算 `data/parsed_messages.jsonl` 中数据的 Token 熵。结果将保存为图像文件。

**注意**: 
1.  运行前请检查脚本中的 `MODEL_PATH` 是否正确。
2.  默认输入文件为 `data/parsed_messages.jsonl`（由上一步生成）。
3.  输出图片将保存在 `outputs/plots/` 目录下。

**用法:**

```bash
python get_logits.py
```

脚本会自动读取 `data/parsed_messages.jsonl`，使用指定 GPU 加载模型，计算 Logits 并生成熵曲线图。

---

## 常见问题

*   **CUDA Out of Memory**: 如果遇到显存不足，请在 `get_logits.py` 中调整 `os.environ["CUDA_VISIBLE_DEVICES"]` 或减少 batch size（当前脚本默认为处理单条消息）。
*   **路径错误**: 请确保所有脚本中的硬编码路径（如 `MODEL_PATH`）与您的实际文件结构一致。
