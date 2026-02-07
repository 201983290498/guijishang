import json
from typing import List, Optional, Dict, Any
from .models import Task, Action, EvaluationResult, QAEval


from src.utils.trace_parse import parse_json_response, parser_answer, filter_reasoning

class TraceParser:
    def __init__(self, filter_reasoning: bool = True):
        self.filter_reasoning = filter_reasoning
    
    def parser_trace_item(self, trace)  :
        last_trace = trace.copy()
        messages = last_trace.get('messages', [])
        response = last_trace.get('response', {})   
        if response:
            messages = messages + [parser_answer(response)]
            last_trace['messages'] = messages
        return messages
        
    def parse_metadata(self, data):
        """
        Extract metadata and full trajectory from JSON file.
        """
        metadata = data.get('metadata', {})
        trace_list = data.get('conversation_trace', [])
        last_messages = self.parser_trace_item(trace_list[-1]) if trace_list else {}
        return {"task": metadata.get('query'), "total_turns": metadata.get('total_turns'), "success": metadata.get('success')}, last_messages

    def parse_file(self, file_path: str) -> Task:
        """
        Parses a single trace JSON file into a Task object.
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        meta_data, last_trace = self.parse_metadata(data)
        evalution_data = self._parser_evaluation(data['evaluation'])
        qas = self.parse_conversation(last_trace, evalution_data)
        messages = self._parser_messages(data['conversation_trace'],meta_data)
    
        return Task(
            file_path=file_path,
            metadata=meta_data,
            qas=qas,
            messages=messages
        )

    def parse_conversation(self, messages, evalution_data):
        if not messages:
            return []
        actions = self._parse_openai_format(messages)
        qas = self.analyze_query_answer_pairs(actions, evalution_data)
        return qas

    def _parse_openai_format(self, messages):
        """
        专门处理 OpenAI 格式。将格式处理成一个个Action
        - Assistant 包含 tool_calls 字段。
        - 工具结果在 role='tool' 的消息中。
        - 答案通常是内容，没有标签，需要通过关键词或默认逻辑进行识别。
        """
        parsed_items = []
        turn_count = 0
        for msg in messages:
            role = msg.get('role')
            content = msg.get('content', '')
            if role == 'system':
                continue
            elif role == 'user': # user的回复包括两种，一种是[ERROR]格式，一种是用户提问。
                if content and ('[ERROR]' in content): # [ERROR] 格式
                    continue
                turn_count += 1 # 交互轮次加1
                parsed_items.append(Action(type="query", turn=turn_count, content=content))
            elif role == 'tool': # 工具的输出结果，追加到工具调用的的背后
                for item in parsed_items:
                    if item.type == 'tool' and item.result is None: # 找到第一个工具调用结果为空的。
                        if 'Error' in content or 'Exception' in content:
                            item.success = 'failure'
                        else:
                            item.success = 'success'
                        item.result = f"[Tool Execution Result]: {content}"
                        break
            elif role == 'assistant': # assistance的输出，两种，一种是工具调用，一种是普通回答。
                tool_calls_data = msg.get('tool_calls')
                thought = msg.get("reasoning_content") if msg.get("reasoning_content") else content  # 思考模式或者非思考模式
                if tool_calls_data: # 如果是工具调用
                    for tc in tool_calls_data:
                        func = tc.get('function', {})
                        tool_name = func.get('name')
                        tool_args = func.get('arguments')
                        try:
                            params = json.loads(tool_args) if isinstance(tool_args, str) else tool_args
                            tool_call_json = json.dumps({"tool": tool_name, "params": params}, ensure_ascii=False)
                        except:
                            tool_call_json = json.dumps({"tool": tool_name, "params": tool_args}, ensure_ascii=False)
                        parsed_items.append(Action(type="tool", thought=thought, turn=turn_count, content=tool_call_json))
                else: # 如果是普通回答
                    final_answer = None
                    json_data = parse_json_response(content)
                    if isinstance(json_data, dict) and "error" not in json_data and 'answer' in json_data:
                        ans = json_data['answer']
                        if isinstance(ans, str):
                            final_answer = ans.strip()
                        else:
                            final_answer = json.dumps(ans, ensure_ascii=False)
                        data_source = json_data.get('data_source', [])
                
                    if not final_answer: # 模型没有按照模式给出answer，尝试从content中提取
                        keywords = ["**Answer:**", "**Answer:**", "## Answer", "### Answer", "## Response", "### Response", "Answer:"]
                        for kw in keywords:
                            if kw in content:
                                parts = content.split(kw, 1)
                                if len(parts) > 1:
                                    final_answer = parts[1].strip()
                                    break
                    
                    if 'data_source' not in locals():
                        data_source = []

                    if final_answer:
                        parsed_items.append(Action(type="answer", thought=thought, turn=turn_count, content=final_answer, data_source=data_source))
                    else:
                        parsed_items.append(Action(type="answer", thought=thought, turn=turn_count, content=content.strip()  , data_source=data_source))
        return parsed_items

    def analyze_query_answer_pairs(self, action_items: list[Action], eval_info_list: Optional[List[EvaluationResult]] = None) -> List[QAEval]:
        """
        匹配 Query 和 Answer，包括中间的 tool calls。
        如果提供了 eval_info_list，则执行强制对齐，并根据 eval_info_list 标记 is_missing。
        """
        # 1. 第一遍：从 trace 中提取原始 pairs
        raw_pairs, current_query, current_tools = [], None, []
        
        for item in action_items: # 分为query， tool_call， answer
            if item.type == 'query':
                if current_query: # 当遇到新的query，将原本的query保存下来。
                    raw_pairs.append(QAEval(
                        query=current_query,
                        tool_call_turns=current_tools[:],
                        step_index=len(raw_pairs) + 1
                    ))
                current_query = item.content
                current_tools = []
            elif item.type in ['tool', 'unknown']:
                if current_query:
                    current_tools.append(item)
            elif item.type == 'answer':
                if current_query:
                    raw_pairs.append(QAEval(
                        query=current_query,
                        tool_call_turns=current_tools[:],
                        step_index=len(raw_pairs) + 1
                    ))
                    current_query = None
                    current_tools = []
        
        if current_query:
            raw_pairs.append(QAEval(
                query=current_query,
                tool_call_turns=current_tools[:],
                step_index=len(raw_pairs) + 1
            ))

        if eval_info_list:
            eval_map = {item.query.strip(): item for item in eval_info_list if item.query}
            for pair in raw_pairs:
                if pair.query and pair.query.strip() in eval_map:
                    pair.evalution_info = eval_map[pair.query.strip()]
        return raw_pairs
    
    def _parser_evaluation(self, evaluation: Dict[str, Any]) -> List[EvaluationResult]:
        if not evaluation: return []
        acc_map = {i['step_index']: i for i in evaluation.get('accuracy_steps', [])}
        td_map = {i['step_index']: i for i in evaluation.get('table_depend_steps', [])}
        
        results = []
        for idx in sorted(acc_map):
            acc = acc_map.get(idx, {}).get('accuracy', {})
            td = td_map.get(idx, {}).get('table_depend', {})
            ans = acc.get('true_answer') or ''
            if isinstance(ans, list): ans = '\n'.join(ans)
            results.append(EvaluationResult(
                step_index=idx,
                query=acc_map.get(idx, {}).get('query', ''),
                answer=acc.get('true_answer'), # 支持列表和普通格式的evalution
                model_answer=acc.get('model_answer'),
                acc_reasoning=acc.get('reasoning', ''),
                coverage_ratio=acc.get('coverage_ratio', 0.0),
                model_tables=td.get('model_tables', []),
                true_tables=td.get('true_tables', []),
                table_reason=td.get('reasoning', ''),
                recall=td.get('recall', 0.0)
            ))
        return results
        
    def _parser_messages(self, traces: List[Dict[str, Any]],meta_data) -> List[Dict[str, str]]:
        """
        Reconstructs the full conversation history for SFT training from trace data.
        返回所有SFT的数据，每次SFT的数据以大模型的输出为截止。
        """
        final_messages = []
        turns = set() # 记录所有以及已经转换成的sft数据
        if not traces: return final_messages
        for trace in traces:
            messages = self.parser_trace_item(trace)
            for idx, item in enumerate(messages):
                key_content = json.dumps(item, ensure_ascii=False)
                if item['role'] == 'assistant': 
                    if key_content in turns:
                        continue
                    if idx > 0 and 'tag' not in messages[idx-1]:
                         print(f"Warning: Missing tag in message {idx-1}. Role: {messages[idx-1].get('role')}")
                         continue

                    message_len = messages[idx-1]['tag']['window'] + 1
                    final_messages.append(filter_reasoning([messages[0]] + messages[idx-message_len+1:idx+1], self.filter_reasoning))
                    turns.add(key_content)
        final_messages.sort(key=len, reverse=True)
        # if meta_data.get('total_turns') == len(final_messages):
        #     print(1)
        unique_messages = []
        for msg in final_messages:
            is_covered = False
            for exist_msg in unique_messages:
                if msg == exist_msg[:len(msg)]:
                    is_covered = True
                    break
            if not is_covered:
                unique_messages.insert(0, msg)
        return unique_messages
        