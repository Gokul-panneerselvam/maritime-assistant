"""
Evaluation Engine CLI Runner.
Entry point for executing the Maritime AI Agent evaluation benchmark.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

from ai_agent.src.evaluation.dataset import get_benchmark_questions, get_benchmark_question_by_id
from ai_agent.src.evaluation.harness import EvaluationHarness
from ai_agent.src.evaluation.reporter import EvaluationReporter
from ai_agent.src.evaluation.schemas import BenchmarkSummary


def parse_args():
    parser = argparse.ArgumentParser(
        description="Maritime AI Agent Evaluation Benchmark Runner"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run against live LangGraph StateGraph pipeline instead of baseline mocks"
    )
    parser.add_argument(
        "--reference-only",
        action="store_true",
        help="Run only the 5 Original Reference Questions (Q1-Q5)"
    )
    parser.add_argument(
        "--parallel-only",
        action="store_true",
        help="Run only the 5 Proposed Parallel Questions (Q6-Q10)"
    )
    parser.add_argument(
        "--guardrail-only",
        action="store_true",
        help="Run only the Guardrail Scope & Profanity Questions (Q11-Q12)"
    )
    parser.add_argument(
        "--question",
        type=str,
        default=None,
        help="Run a specific question ID (e.g. Q1, Q6, Q11)"
    )
    parser.add_argument(
        "--llm-judge",
        action="store_true",
        help="Enable LLM-as-a-Judge semantic grading (requires configured LLM)"
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Path to save JSON benchmark summary"
    )
    parser.add_argument(
        "--output-markdown",
        type=str,
        default=None,
        help="Path to save Markdown benchmark report"
    )
    parser.add_argument(
        "--output-html",
        type=str,
        default=None,
        help="Path to save standalone Generative UI HTML report"
    )
    return parser.parse_args()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    args = parse_args()
    
    questions = get_benchmark_questions(
        reference_only=args.reference_only,
        parallel_only=args.parallel_only,
        guardrail_only=args.guardrail_only,
        question_id=args.question
    )

    if not questions:
        print(f"No benchmark questions matched filter (question={args.question}).")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("MARITIME OPERATIONS AI AGENT — EVALUATION BENCHMARK")
    print(f"Questions Selected: {len(questions)} | Mode: {'LIVE LANGGRAPH' if args.live else 'BASELINE GOLDEN MOCKS'}")
    print(f"LLM Judge: {'ENABLED' if args.llm_judge else 'DISABLED (Rule-Based Fast Path)'}")
    print("=" * 70 + "\n")

    summary: BenchmarkSummary = EvaluationHarness.evaluate_suite(
        questions=questions,
        live=args.live,
        enable_llm_judge=args.llm_judge
    )

    # Print Terminal Table
    print(f"{'ID':<5} | {'Pair':<16} | {'Category':<32} | {'Status':<20} | {'Score':<8} | {'Result':<6}")
    print("-" * 96)
    for r in summary.results:
        verdict = "PASS" if r.passed else "FAIL"
        print(
            f"{r.question_id:<5} | {r.pair_id:<16} | {r.category[:30]:<32} | "
            f"{r.response_status[:18]:<20} | {int(r.overall_score * 100):>3}%   | {verdict:<6}"
        )
    print("-" * 96)
    print(f"\n[+] Overall Pass Rate: {int(summary.overall_pass_rate * 100)}% ({summary.passed_questions}/{summary.total_questions})")
    print(f"[+] Composite Average Score: {int(summary.average_score * 100)}%")
    print(f"[+] Reference (Q1-Q5) Avg: {int(summary.reference_average_score * 100)}% | Parallel (Q6-Q10) Avg: {int(summary.parallel_average_score * 100)}% | Guardrail (Q11-Q12) Avg: {int(summary.guardrail_average_score * 100)}%")
    print(f"[+] Pillars: Epistemic {int(summary.epistemic_fidelity_score * 100)}% | Factual {int(summary.factual_accuracy_score * 100)}% | Robustness {int(summary.robustness_score * 100)}% | Operational {int(summary.operational_actionability_score * 100)}%\n")

    # Exports
    if args.output_json:
        out_p = Path(args.output_json)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
        print(f"[+] JSON report saved to: {out_p.resolve()}")

    if args.output_markdown:
        out_p = Path(args.output_markdown)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        md_content = EvaluationReporter.generate_markdown_report(summary)
        out_p.write_text(md_content, encoding="utf-8")
        print(f"[+] Markdown report saved to: {out_p.resolve()}")

    if args.output_html:
        out_p = Path(args.output_html)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        html_content = EvaluationReporter.generate_html_dashboard(summary)
        out_p.write_text(html_content, encoding="utf-8")
        print(f"[+] Generative UI HTML report saved to: {out_p.resolve()}")


if __name__ == "__main__":
    main()
