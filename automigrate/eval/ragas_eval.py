"""
Ragas Evaluation Script.

Evaluates the quality of retrieved contexts and LLM transformations.
"""

from __future__ import annotations

import os
import json
from datasets import Dataset

# Only load Ragas if requested, to avoid slowing down imports everywhere
def evaluate_rag_pipeline(queries: list[str], contexts: list[list[str]], answers: list[str]):
    """Evaluate retrieval faithfulness and context relevance.
    
    In a real implementation, you would load an evaluation dataset,
    run it through your retriever and LLM, and pass it to ragas.
    """
    try:
        from ragas import evaluate
        from ragas.metrics import faithfulness, context_relevance
    except ImportError:
        print("Ragas not installed.")
        return
        
    data = {
        "question": queries,
        "contexts": contexts,
        "answer": answers,
    }
    
    dataset = Dataset.from_dict(data)
    
    # This requires an LLM (like OpenAI) to act as a judge
    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY required for Ragas evaluation.")
        return
        
    result = evaluate(
        dataset,
        metrics=[faithfulness, context_relevance],
    )
    
    print("Ragas Evaluation Results:")
    print(result)
    
    # Save results
    with open("reports/ragas_eval.json", "w") as f:
        # Assuming result is a dict-like object (ragas returns a Result object)
        f.write(json.dumps(result, indent=2, default=str))
        
    return result
