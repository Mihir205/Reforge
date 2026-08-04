"""
LangSmith Tracing Configuration.

Sets up environment for LangSmith observability.
"""

import os
from typing import Callable, Any

def enable_tracing(project_name: str = "automigrate") -> None:
    """Configure LangSmith tracing."""
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = project_name
    
    if not os.getenv("LANGCHAIN_API_KEY"):
        print("Warning: LANGCHAIN_API_KEY not set. Tracing will not be sent to LangSmith.")

# Utility decorator for tracing generic python functions (if not using LangChain natives)
try:
    from langsmith import traceable
except ImportError:
    # Dummy decorator if langsmith is not installed during certain tests
    def traceable(*args, **kwargs) -> Callable:
        def decorator(func: Callable) -> Callable:
            return func
        return decorator
