"""Document optimization service.

When documents are uploaded to the knowledge base, this service uses the LLM
to refine the extracted text for maximum precision and effectiveness in RAG
prompting.  The goal is to produce a version of the document that, when
retrieved as context chunks, primes the LLM for high-quality strategic
analysis.

Optimization priorities (in order):
1. Precision — preserve every factual claim, number, and relationship exactly.
2. Clarity — restructure for unambiguous, direct language.
3. Conciseness — remove filler and redundancy only where it does not sacrifice
   precision or context.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

_FRAMEWORK_SYSTEM_PROMPT = """\
You are a knowledge-base editor for a multi-agent strategic analysis platform.
Your task is to optimize a document so that when its chunks are retrieved via
RAG and injected into an LLM's context window, they maximally prime the model
for precise strategic reasoning.

Rules:
- PRESERVE every factual claim, statistic, formula, named entity, and causal
  relationship.  Do NOT invent information or add interpretation.
- RESTRUCTURE sentences for clarity: prefer active voice, explicit subjects,
  and direct predication.
- REMOVE filler phrases, marketing language, unnecessary hedging, and
  repetition — but only when removal does not reduce information content.
- USE consistent terminology throughout.  If the source uses synonyms for the
  same concept, pick the most precise term and use it consistently.
- ORGANIZE the text into clearly delineated sections with descriptive headings
  (e.g., "Core Principles", "Application Conditions", "Limitations").
- For frameworks/algorithms, ensure every step or principle is numbered and
  self-contained.
- Output the optimized document text only — no commentary, no preamble."""

_SIMULATION_DESC_SYSTEM_PROMPT = """\
You are a knowledge-base editor for a multi-agent strategic analysis platform.
Your task is to optimize a simulation description document so that when its
chunks are retrieved via RAG, they tell the LLM exactly:
  (a) what the simulation computes and why it matters for strategic decisions,
  (b) what each input variable represents and valid ranges/units,
  (c) how to interpret each output and what thresholds or benchmarks apply,
  (d) common usage patterns and which strategic questions this simulation helps
      answer.

Rules:
- PRESERVE every variable name, unit, formula reference, and numeric
  constraint exactly.
- RESTRUCTURE for maximum clarity — one concept per paragraph, explicit
  section headings.
- REMOVE filler but never remove information about inputs, outputs, or usage.
- Output the optimized document text only — no commentary."""

_PRACTICALITY_SYSTEM_PROMPT = """\
You are a knowledge-base editor for a multi-agent strategic analysis platform.
Your task is to optimize a practicality/constraints document so that when its
chunks are retrieved via RAG, they tell the feasibility-scoring LLM exactly:
  (a) what real-world constraints, risks, or feasibility factors apply,
  (b) what scoring criteria and thresholds define low/medium/high feasibility,
  (c) what industry benchmarks, regulatory limits, or resource constraints are
      relevant,
  (d) common failure modes and risk mitigations that should inform scoring.

Rules:
- PRESERVE every constraint, threshold, benchmark, regulatory reference, and
  risk factor exactly.
- RESTRUCTURE for maximum clarity — one constraint or criterion per paragraph,
  explicit section headings (e.g., "Regulatory Constraints", "Resource Limits",
  "Risk Scoring Benchmarks").
- REMOVE filler but never remove information about constraints, scoring, or
  risk factors.
- Output the optimized document text only — no commentary."""

_CLASSIFY_SYSTEM_PROMPT = """\
You are a document classifier for a multi-agent strategic analysis platform.
The platform has two types of knowledge:

1. FRAMEWORK (theory) — analytical frameworks, algorithms, methodologies,
   models, strategic theories, decision-making approaches, and academic or
   domain-specific knowledge that helps agents reason about problems.

2. PRACTICALITY (constraints) — real-world constraints, feasibility criteria,
   risk frameworks, regulatory requirements, resource limitations, industry
   benchmarks, cost structures, timeline constraints, and scoring rubrics
   used to evaluate how feasible recommendations are.

Classify the following document excerpt. Respond with ONLY one word:
"framework" or "practicality"."""


def classify_document(text: str, api_key: str | None = None) -> str:
    """Use AI to classify document as 'framework' or 'practicality'.

    Returns 'framework' as default if classification fails or no API key.
    """
    if not api_key or not text or len(text.strip()) < 50:
        return "framework"

    excerpt = text[:2000]

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=10,
            system=_CLASSIFY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": excerpt}],
        )

        result = "".join(
            block.text
            for block in message.content
            if getattr(block, "type", None) == "text"
        ).strip().lower()

        if "practicality" in result:
            return "practicality"
        return "framework"

    except Exception as e:
        logger.error("Document classification failed: %s — defaulting to framework", e)
        return "framework"


def optimize_document(
    raw_text: str,
    document_type: str = "framework",
    api_key: str | None = None,
) -> str:
    """Optimize extracted document text for RAG precision.

    Args:
        raw_text: The raw extracted text from the uploaded document.
        document_type: "framework" for framework/algorithm TXT files,
                       "simulation_description" for simulation companion TXT.
        api_key: Anthropic API key.  If None, returns raw_text unmodified.

    Returns:
        Optimized text string.
    """
    if not api_key:
        logger.warning("No API key available — skipping document optimization")
        return raw_text

    if not raw_text or len(raw_text.strip()) < 50:
        return raw_text

    if document_type == "simulation_description":
        system_prompt = _SIMULATION_DESC_SYSTEM_PROMPT
    elif document_type == "practicality":
        system_prompt = _PRACTICALITY_SYSTEM_PROMPT
    else:
        system_prompt = _FRAMEWORK_SYSTEM_PROMPT

    user_prompt = (
        "Optimize the following document for knowledge-base ingestion.  "
        "Return ONLY the optimized text.\n\n"
        "--- DOCUMENT START ---\n"
        f"{raw_text}\n"
        "--- DOCUMENT END ---"
    )

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        start = time.time()
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max(4096, len(raw_text) // 2),
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        elapsed_ms = int((time.time() - start) * 1000)

        optimized = "".join(
            block.text
            for block in message.content
            if getattr(block, "type", None) == "text"
        )

        if not optimized.strip():
            logger.warning("LLM returned empty optimization — using raw text")
            return raw_text

        logger.info(
            "Document optimized: %d chars → %d chars in %dms",
            len(raw_text),
            len(optimized),
            elapsed_ms,
        )
        return optimized

    except Exception as e:
        logger.error("Document optimization failed: %s — using raw text", e)
        return raw_text
