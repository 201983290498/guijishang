from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class EvaluationResult:
    step_index: int
    query: str
    answer: str|list[str]
    model_answer: str
    acc_reasoning: str
    coverage_ratio: float
    model_tables: List[str]
    true_tables: List[str]
    table_reason: str
    recall: float

@dataclass
class QAEval:
    """
    Represents the detailed information for a single Question-Answer pair.
    """
    query: Optional[str] = None
    tool_call_turns: List[int] = field(default_factory=list)
    step_index: Optional[int] = None
    evalution_info: Optional[EvaluationResult] = None

@dataclass
class Task:
    """
    Represents the entire trace file (a multi-turn conversation task).
    """
    file_path: str
    metadata: Dict[str, Any]
    qas: List[QAEval]
    messages: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class Action:
    """
    Represents an action in the trace, such as a query or tool execution.
    """
    type: Optional[str] = None
    thought: Optional[str] = None
    content: Optional[str] = None
    result: Optional[str] = None
    turn: Optional[int] = None
    success: Optional[bool] = None
    data_source: Optional[str] = None
