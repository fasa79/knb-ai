"""RAGAS evaluation — measures RAG pipeline quality on ground truth dataset.

Metrics:
  - Faithfulness:       Is the answer grounded in the retrieved context?
  - Answer Relevancy:   Does the answer actually address the question?
  - Context Precision:  Are the top-ranked chunks truly relevant?
  - Context Recall:     Were the relevant chunks retrieved?

Usage:
    cd knb-ai
    python -m app.evaluation.run_eval
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# Must set env before importing app modules
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from datasets import Dataset

from app.agents.tools.search_tool import SearchTool
from app.core.llm_client import get_llm_client
from app.config import get_settings
from app.evaluation.dataset import EVAL_DATASET

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

RESULTS_DIR = PROJECT_ROOT / "app" / "evaluation" / "results"


async def collect_predictions(search_tool: SearchTool) -> list[dict]:
    """Run each ground-truth question through the RAG pipeline."""
    predictions = []

    for i, item in enumerate(EVAL_DATASET):
        question = item["question"]
        logger.info(f"[{i+1}/{len(EVAL_DATASET)}] Querying: {question}")

        try:
            response = await search_tool.search(question)
            contexts = [s.text_snippet for s in response.sources] if response.sources else [""]
            predictions.append({
                "question": question,
                "answer": response.answer,
                "contexts": contexts,
                "ground_truth": item["ground_truth"],
            })
            logger.info(f"  → confidence={response.confidence}, sources={len(response.sources)}")
        except Exception as e:
            logger.error(f"  → FAILED: {e}")
            predictions.append({
                "question": question,
                "answer": f"Error: {e}",
                "contexts": [""],
                "ground_truth": item["ground_truth"],
            })

        # Rate limiting — Gemini free tier
        time.sleep(2)

    return predictions


def run_ragas_evaluation(predictions: list[dict]) -> dict:
    """Run RAGAS metrics on collected predictions."""
    dataset = Dataset.from_dict({
        "question": [p["question"] for p in predictions],
        "answer": [p["answer"] for p in predictions],
        "contexts": [p["contexts"] for p in predictions],
        "ground_truth": [p["ground_truth"] for p in predictions],
    })

    logger.info(f"Running RAGAS evaluation on {len(predictions)} samples...")

    # Use our Gemini LLM + embeddings for evaluation
    llm_client = get_llm_client()
    chat_model = llm_client.get_chat_model(temperature=0.0)

    settings = get_settings()
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    lc_embeddings = GoogleGenerativeAIEmbeddings(
        model=f"models/{settings.embedding_model}",
        google_api_key=settings.gemini_api_key,
    )

    ragas_llm = LangchainLLMWrapper(chat_model)
    ragas_embeddings = LangchainEmbeddingsWrapper(lc_embeddings)

    metrics = [faithfulness, answer_relevancy, context_precision, context_recall]

    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=ragas_llm,
        embeddings=ragas_embeddings,
    )

    return result


def save_results(predictions: list[dict], ragas_result) -> Path:
    """Save evaluation results to JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = RESULTS_DIR / f"eval_{timestamp}.json"

    # EvaluationResult has a ._repr_dict attribute or we can use to_pandas()
    try:
        scores_dict = ragas_result._repr_dict
    except AttributeError:
        # Fallback: convert DataFrame row to dict
        df = ragas_result.to_pandas()
        metric_cols = [c for c in df.columns if c not in ("question", "contexts", "answer", "ground_truth", "user_input", "response", "retrieved_contexts", "reference")]
        scores_dict = {col: float(df[col].mean()) for col in metric_cols if df[col].dtype in ("float64", "float32")}

    scores = {k: round(v, 4) if isinstance(v, float) else v for k, v in scores_dict.items()}

    output = {
        "timestamp": timestamp,
        "num_samples": len(predictions),
        "scores": scores,
        "predictions": predictions,
    }

    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    logger.info(f"Results saved to {output_path}")
    return output_path


async def main():
    logger.info("=== RAGAS Evaluation ===")
    logger.info(f"Dataset: {len(EVAL_DATASET)} questions")

    # Initialize search tool (loads embeddings, vector store, BM25)
    logger.info("Initializing search tool...")
    search_tool = SearchTool()

    # Step 1: Collect predictions
    logger.info("Step 1/3: Collecting predictions...")
    predictions = await collect_predictions(search_tool)

    # Step 2: Run RAGAS
    logger.info("Step 2/3: Running RAGAS metrics...")
    ragas_result = run_ragas_evaluation(predictions)

    # Step 3: Save
    logger.info("Step 3/3: Saving results...")
    output_path = save_results(predictions, ragas_result)

    # Print summary
    print("\n" + "=" * 50)
    print("RAGAS EVALUATION RESULTS")
    print("=" * 50)
    try:
        scores_dict = ragas_result._repr_dict
    except AttributeError:
        df = ragas_result.to_pandas()
        metric_cols = [c for c in df.columns if c not in ("question", "contexts", "answer", "ground_truth", "user_input", "response", "retrieved_contexts", "reference")]
        scores_dict = {col: float(df[col].mean()) for col in metric_cols if df[col].dtype in ("float64", "float32")}
    for metric, score in scores_dict.items():
        if isinstance(score, float):
            print(f"  {metric:25s}: {score:.4f}")
    print("=" * 50)
    print(f"\nFull results: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
