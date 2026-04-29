from pydantic import BaseModel, Field
from typing import List, Any, Annotated, Dict, Optional
import operator
from langgraph.graph.message import add_messages

def keep_last(a, b):
    return b if b is not None else a

class BugState(BaseModel):
    code: Annotated[str, keep_last] = ""
    remaining_steps: int = 100
    cycle_count: Annotated[int, keep_last] = Field(default=0)
    messages: Annotated[List[Any], add_messages] = Field(default_factory=list)