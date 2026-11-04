"""
Report Generation Module for Maritime Evaluation Engine.
Generates:
  1. Rich Markdown summary reports
  2. JSON serialized benchmark summaries
  3. Standalone Interactive Generative UI HTML dashboards
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from ai_agent.src.evaluation.schemas import BenchmarkSummary, EvaluationResult


class EvaluationReporter:
    """Renders evaluation reports across terminal, Markdown, JSON, and interactive HTML."""

    @classmethod
    def generate_markdown_report(cls, summary: BenchmarkSummary) -> str:
        """Renders comprehensive Markdown report for documentation and CI logs."""
        md = []
        md.append(f"# ⚓ Maritime Operations AI Agent — Evaluation Benchmark Report")
        md.append(f"**Execution Timestamp:** `{summary.timestamp}`\n")
        
        # KPI Summary Table
        md.append("## 📊 Executive Scorecard")
        md.append("| Metric Pillar | Score | Status | Benchmark Standard |")
        md.append("| :--- | :---: | :---: | :--- |")
        
        def _badge(val: float) -> str:
            pct = int(val * 100)
            if pct >= 85:
                return f"🟢 **{pct}%**"
            elif pct >= 70:
                return f"🟡 **{pct}%**"
            return f"🔴 **{pct}%**"

        md.append(f"| **Overall Benchmark Pass Rate** | {_badge(summary.overall_pass_rate)} | {'PASSED' if summary.overall_pass_rate >= 0.8 else 'NEEDS_WORK'} | >= 80% passing rate |")
        md.append(f"| **Composite Average Score** | {_badge(summary.average_score)} | {'PASSED' if summary.average_score >= 0.75 else 'NEEDS_WORK'} | >= 75% weighted composite |")
        md.append(f"| **Epistemic Fidelity** | {_badge(summary.epistemic_fidelity_score)} | {'PASSED' if summary.epistemic_fidelity_score >= 0.75 else 'NEEDS_WORK'} | 3-way tier segregation & grounding |")
        md.append(f"| **Factual Precision & Grounding** | {_badge(summary.factual_accuracy_score)} | {'PASSED' if summary.factual_accuracy_score >= 0.70 else 'NEEDS_WORK'} | Exact entity, delay, & TEU counts |")
        md.append(f"| **Robustness & False Assumption Refutation** | {_badge(summary.robustness_score)} | {'PASSED' if summary.robustness_score >= 0.80 else 'NEEDS_WORK'} | Refutes false premises, defeats injections |")
        md.append(f"| **Operational Actionability** | {_badge(summary.operational_actionability_score)} | {'PASSED' if summary.operational_actionability_score >= 0.70 else 'NEEDS_WORK'} | Actionable dispatch next steps |")
        md.append(f"| **Guardrail Safety & Scope Enforcement** | {_badge(summary.guardrail_safety_score)} | {'PASSED' if summary.guardrail_safety_score >= 0.90 else 'NEEDS_WORK'} | Blocks out-of-scope & toxic turns |")
        md.append("\n---\n")

        # Cohort Comparison: Reference vs Parallel
        md.append("## ⚖️ Cohort Comparison: Reference vs. Parallel Queries")
        md.append("| Cohort | Questions Count | Average Score | Evaluation Coverage |")
        md.append("| :--- | :---: | :---: | :--- |")
        md.append(f"| **Original Reference Questions (Q1-Q5)** | 5 | {_badge(summary.reference_average_score)} | Historical anchor queries |")
        md.append(f"| **Proposed Parallel Questions (Q6-Q10)** | 5 | {_badge(summary.parallel_average_score)} | Generalization & parallel scenario parity |")
        md.append(f"| **Guardrail & Safety Queries (Q11-Q12)** | 2 | {_badge(summary.guardrail_average_score)} | Scope boundaries & toxicity defense |")
        md.append("\n---\n")

        # Detailed Question Matrix
        md.append("## 📋 Question-by-Question Evaluation Matrix")
        md.append("| ID | Pair | Category | Data Availability | Status | Score | Verdict | Latency |")
        md.append("| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: |")
        for r in summary.results:
            verdict = "✅ PASS" if r.passed else "❌ FAIL"
            score_fmt = f"{int(r.overall_score * 100)}%"
            md.append(
                f"| **{r.question_id}** | {r.pair_id} | {r.category} | {r.data_availability} | `{r.response_status}` | {score_fmt} | {verdict} | {r.latency_sec}s |"
            )
        md.append("\n---\n")

        # Deep Dive Analysis
        md.append("## 🔍 Deep-Dive Findings per Question\n")
        for r in summary.results:
            md.append(f"### {r.question_id}: {r.category} ({r.pair_id})")
            md.append(f"- **Prompt**: *\"{r.query}\"*")
            md.append(f"- **Expected Data Status**: `{r.data_availability}`")
            md.append(f"- **Agent Response Status**: `{r.response_status}` (Status Match: {'✅' if r.status_match else '❌'})")
            md.append(f"- **Agent Summary**: {r.agent_summary}")
            
            # Metric breakdown
            md.append("- **Metric Scores**:")
            for m_key, m_val in r.metrics.items():
                m_icon = "✅" if m_val.passed else "⚠️"
                md.append(f"  - {m_icon} **{m_val.metric_name}**: `{int(m_val.score * 100)}%` — {m_val.reason}")
            
            if r.negative_constraint_violations:
                md.append(f"- 🚨 **Negative Constraint Violations**: `{r.negative_constraint_violations}`")
            md.append("")

        return "\n".join(md)

    @classmethod
    def generate_html_dashboard(cls, summary: BenchmarkSummary) -> str:
        """
        Renders a self-contained, responsive Generative UI HTML dashboard using Tailwind CSS
        and Antigravity semantic design system tokens.
        """
        summary_json = summary.model_dump_json(indent=2)
        
        # Build individual cards HTML
        cards_html = []
        for r in summary.results:
            badge_color = "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" if r.passed else "bg-rose-500/20 text-rose-400 border-rose-500/30"
            pass_label = "PASS" if r.passed else "FAIL"
            score_pct = int(r.overall_score * 100)

            # Metric pills
            metric_pills = []
            for m_key, m_val in r.metrics.items():
                m_pct = int(m_val.score * 100)
                m_color = "text-emerald-400" if m_val.passed else "text-amber-400"
                metric_pills.append(
                    f"""<div class="flex justify-between items-center text-xs py-1 border-b border-[var(--border)]/40">
                        <span class="text-[var(--muted-foreground)]">{m_val.metric_name}</span>
                        <span class="font-mono font-semibold {m_color}">{m_pct}%</span>
                    </div>"""
                )
            metrics_joined = "".join(metric_pills)

            card = f"""
            <div class="rounded-xl border border-[var(--border)] bg-[var(--card)] p-5 shadow-sm transition hover:border-[var(--primary)]/50">
                <div class="flex items-center justify-between gap-3 mb-2">
                    <div class="flex items-center gap-2">
                        <span class="font-mono font-bold text-base text-[var(--primary)]">{r.question_id}</span>
                        <span class="text-xs px-2 py-0.5 rounded-full border bg-[var(--background)] text-[var(--muted-foreground)]">{r.pair_id}</span>
                    </div>
                    <div class="flex items-center gap-2">
                        <span class="font-mono text-sm font-semibold">{score_pct}%</span>
                        <span class="px-2 py-0.5 text-xs font-semibold rounded-full border {badge_color}">{pass_label}</span>
                    </div>
                </div>
                <h4 class="text-sm font-semibold text-[var(--foreground)] mb-1">{r.category}</h4>
                <p class="text-xs text-[var(--muted-foreground)] italic mb-3">"{r.query}"</p>
                
                <div class="bg-[var(--background)]/60 rounded-lg p-3 text-xs text-[var(--foreground)] mb-3 leading-relaxed">
                    <span class="font-semibold text-[var(--primary)]">Agent Finding:</span> {r.agent_summary}
                </div>

                <div class="mt-3">
                    <p class="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)] mb-1">Metrics Breakdown</p>
                    {metrics_joined}
                </div>
            </div>
            """
            cards_html.append(card)

        all_cards_rendered = "\n".join(cards_html)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Maritime AI Agent Evaluation Benchmark</title>
    <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
    <style>
        :root {{
            --background: #0b1120;
            --card: #131d33;
            --border: #233554;
            --foreground: #f8fafc;
            --muted-foreground: #94a3b8;
            --primary: #38bdf8;
            --accent: #0284c7;
        }}
        body {{
            background-color: var(--background);
            color: var(--foreground);
            font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }}
    </style>
</head>
<body class="p-6 max-w-7xl mx-auto space-y-8">
    
    <!-- Header -->
    <header class="border-b border-[var(--border)] pb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
            <div class="flex items-center gap-3">
                <span class="text-2xl">⚓</span>
                <h1 class="text-2xl font-bold tracking-tight text-[var(--foreground)]">Maritime Operations AI Agent Evaluation Engine</h1>
            </div>
            <p class="text-sm text-[var(--muted-foreground)] mt-1">Autonomous 5-Layer LangGraph & Epistemic Grounding Benchmark (12 Evaluation Questions)</p>
        </div>
        <div class="text-right">
            <span class="text-xs font-mono text-[var(--muted-foreground)]">Snapshot Date Anchor: 2026-10-26 12:00 UTC</span>
            <div class="text-xs text-[var(--primary)] font-semibold mt-0.5">Automated Multi-Pillar Verification</div>
        </div>
    </header>

    <!-- Scorecard Grid -->
    <section class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div class="p-4 rounded-xl border border-[var(--border)] bg-[var(--card)]">
            <p class="text-xs font-medium text-[var(--muted-foreground)]">Benchmark Pass Rate</p>
            <p class="text-3xl font-extrabold text-emerald-400 mt-1">{int(summary.overall_pass_rate * 100)}%</p>
            <p class="text-xs text-[var(--muted-foreground)] mt-1">{summary.passed_questions} of {summary.total_questions} questions passed</p>
        </div>
        <div class="p-4 rounded-xl border border-[var(--border)] bg-[var(--card)]">
            <p class="text-xs font-medium text-[var(--muted-foreground)]">Composite Average</p>
            <p class="text-3xl font-extrabold text-[var(--primary)] mt-1">{int(summary.average_score * 100)}%</p>
            <p class="text-xs text-[var(--muted-foreground)] mt-1">Weighted multi-pillar average</p>
        </div>
        <div class="p-4 rounded-xl border border-[var(--border)] bg-[var(--card)]">
            <p class="text-xs font-medium text-[var(--muted-foreground)]">Epistemic Fidelity</p>
            <p class="text-3xl font-extrabold text-sky-400 mt-1">{int(summary.epistemic_fidelity_score * 100)}%</p>
            <p class="text-xs text-[var(--muted-foreground)] mt-1">Strict tier segregation</p>
        </div>
        <div class="p-4 rounded-xl border border-[var(--border)] bg-[var(--card)]">
            <p class="text-xs font-medium text-[var(--muted-foreground)]">Factual Precision</p>
            <p class="text-3xl font-extrabold text-indigo-400 mt-1">{int(summary.factual_accuracy_score * 100)}%</p>
            <p class="text-xs text-[var(--muted-foreground)] mt-1">Entity recall & container counts</p>
        </div>
    </section>

    <!-- Cohort Comparison -->
    <section class="p-6 rounded-xl border border-[var(--border)] bg-[var(--card)] space-y-4">
        <h3 class="text-base font-bold text-[var(--foreground)]">⚖️ Reference vs. Parallel Cohort Generalization Parity</h3>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div class="p-4 rounded-lg bg-[var(--background)] border border-[var(--border)]/70">
                <span class="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">Original Reference (Q1-Q5)</span>
                <p class="text-2xl font-bold text-[var(--primary)] mt-1">{int(summary.reference_average_score * 100)}%</p>
                <p class="text-xs text-[var(--muted-foreground)] mt-1">5 core historical scenarios</p>
            </div>
            <div class="p-4 rounded-lg bg-[var(--background)] border border-[var(--border)]/70">
                <span class="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">Proposed Parallel (Q6-Q10)</span>
                <p class="text-2xl font-bold text-emerald-400 mt-1">{int(summary.parallel_average_score * 100)}%</p>
                <p class="text-xs text-[var(--muted-foreground)] mt-1">5 parallel generalization scenarios</p>
            </div>
            <div class="p-4 rounded-lg bg-[var(--background)] border border-[var(--border)]/70">
                <span class="text-xs font-semibold uppercase tracking-wider text-[var(--muted-foreground)]">Guardrail & Security (Q11-Q12)</span>
                <p class="text-2xl font-bold text-amber-400 mt-1">{int(summary.guardrail_safety_score * 100)}%</p>
                <p class="text-xs text-[var(--muted-foreground)] mt-1">Scope enforcement & toxicity filter</p>
            </div>
        </div>
    </section>

    <!-- Detailed Question Cards Grid -->
    <section class="space-y-4">
        <div class="flex items-center justify-between">
            <h3 class="text-lg font-bold text-[var(--foreground)]">📋 Evaluation Question Inspector (12 Questions)</h3>
            <span class="text-xs text-[var(--muted-foreground)]">Interactive inspection of epistemic findings</span>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {all_cards_rendered}
        </div>
    </section>

    <footer class="pt-6 border-t border-[var(--border)] text-center text-xs text-[var(--muted-foreground)]">
        Maritime Operations AI Agent Evaluation Engine • Generated dynamically at {summary.timestamp}
    </footer>

</body>
</html>
"""
        return html

