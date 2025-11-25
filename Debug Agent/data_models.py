#Date Models file - Jonathan C. Licurse - 11/24/25 #

from pydantic import BaseModel
from typing import List, Optional

class DebugContext(BaseModel):
    description: str                        #User's description of the bug
    log_snippets: List[str]                 #Extracted relevant parts from log files
    code_snippets: List[str]                #Extracted relevant parts from the code
    project_path: Optional[str] = None

class Hypothesis(BaseModel):
    title: str              #e.g. "Null pointer in _____
    likelihood: str         #"high", "medium", "low"
    reasoning: str          #Explanation

class DebugStep(BaseModel):
    step_number: int
    action: str                 # e.g. "Add debug log before calling x"
    details: str                #More detail
    expected_outcome: str       # What this step should reveal

class DebugPlan(BaseModel):
    summary: str                        #Overall Diagnostics Summary 
    hypothesis: List[Hypothesis]
    steps: List[DebugStep]

