import React, { useState } from 'react';
import {
  ShieldCheck,
  AlertTriangle,
  Lightbulb,
  XCircle,
  HelpCircle,
  Database,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Copy,
  Check,
} from 'lucide-react';
import { MaritimeAgentResponse } from '../types/maritime';

interface EpistemicCardsProps {
  response: MaritimeAgentResponse;
  onSelectCitation: (citationId: string) => void;
  onClarificationChoice: (choice: string) => void;
}

export const EpistemicCards: React.FC<EpistemicCardsProps> = ({
  response,
  onSelectCitation,
  onClarificationChoice,
}) => {
  const [showCypher, setShowCypher] = useState(false);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  const handleCopyCypher = (query: string, index: number) => {
    navigator.clipboard.writeText(query);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  const hasConfirmed = response.confirmed_facts && response.confirmed_facts.length > 0;
  const hasUnverified = response.unverified_reports && response.unverified_reports.length > 0;
  const hasInferences = response.system_inferences && response.system_inferences.length > 0;
  const hasFalsePremises = response.false_premises_detected && response.false_premises_detected.length > 0;
  const hasClarification = !!response.clarification;
  const hasCypher = response.cypher_queries_executed && response.cypher_queries_executed.length > 0;

  return (
    <div className="space-y-3 mt-3">
      {/* 0. Data Unavailable Status Banner */}
      {response.status === 'DATA_UNAVAILABLE' && (
        <div className="rounded-xl border border-slate-700/80 bg-slate-900/60 p-3 text-xs text-slate-300 flex items-center gap-2 shadow-sm">
          <Database className="w-4 h-4 text-cyan-400 shrink-0" />
          <span>
            <strong className="text-white mr-1">No Matching Graph Records:</strong>
            Epistemically declared unavailable without guessing or hallucinating data.
          </span>
        </div>
      )}

      {/* 1. False Premises Banner (Shown prominently if detected) */}
      {hasFalsePremises && (
        <div className="rounded-xl border border-rose-900/80 bg-rose-950/30 overflow-hidden shadow-sm">
          <div className="px-3.5 py-2 bg-rose-950/60 border-b border-rose-900/60 flex items-center justify-between">
            <span className="text-xs font-bold text-rose-300 flex items-center gap-2">
              <XCircle className="w-4 h-4 text-rose-400" />
              Premise Discrepancy Corrected
            </span>
            <span className="text-[10px] font-mono text-rose-400 px-2 py-0.5 rounded-full bg-rose-900/60">
              GROUNDED REALITY
            </span>
          </div>
          <div className="p-3 space-y-2 text-xs">
            {response.false_premises_detected.map((p, idx) => (
              <div key={idx} className="bg-rose-900/20 p-2.5 rounded-lg border border-rose-900/40">
                <div className="text-slate-300 line-through decoration-rose-400 mb-1">
                  <span className="text-rose-400 font-semibold mr-1">Assumption:</span>
                  {p.user_assumption}
                </div>
                <div className="text-rose-200 font-medium flex items-start gap-1.5">
                  <span className="text-emerald-400 font-bold shrink-0">Reality:</span>
                  <span>{p.grounded_reality}</span>
                </div>
                {p.citations && p.citations.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {p.citations.map((c, cIdx) => (
                      <button
                        key={cIdx}
                        onClick={() => onSelectCitation(c)}
                        className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800 hover:border-rose-600 transition"
                      >
                        <span>{c}</span>
                        <ExternalLink className="w-2.5 h-2.5" />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 2. Interactive Clarification Prompt */}
      {hasClarification && response.clarification && (
        <div className="rounded-xl border border-cyan-800/80 bg-cyan-950/30 overflow-hidden shadow-md">
          <div className="px-3.5 py-2 bg-cyan-950/60 border-b border-cyan-800/60 flex items-center gap-2">
            <HelpCircle className="w-4 h-4 text-cyan-400" />
            <span className="text-xs font-bold text-cyan-300">Operational Clarification Required</span>
          </div>
          <div className="p-3 text-xs space-y-2.5">
            <p className="text-slate-200 font-medium">{response.clarification.question}</p>
            {response.clarification.reason && (
              <p className="text-[11px] text-slate-400 italic">{response.clarification.reason}</p>
            )}
            <div className="flex flex-wrap gap-2 pt-1">
              {response.clarification.options.map((opt) => (
                <button
                  key={opt.option_id}
                  onClick={() => onClarificationChoice(opt.label)}
                  className="px-3 py-1.5 rounded-lg bg-cyan-900/60 hover:bg-cyan-800 text-cyan-200 hover:text-white border border-cyan-700 hover:border-cyan-500 font-medium text-xs transition shadow-sm flex items-center gap-1.5"
                >
                  <span>{opt.label}</span>
                  {opt.description && (
                    <span className="text-[10px] text-cyan-400/80">({opt.description})</span>
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 3. Confirmed Facts (Green) */}
      {hasConfirmed && (
        <div className="rounded-xl border border-emerald-900/60 bg-emerald-950/20 overflow-hidden shadow-sm">
          <div className="px-3.5 py-2 bg-emerald-950/50 border-b border-emerald-900/40 flex items-center justify-between">
            <span className="text-xs font-bold text-emerald-400 flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              Confirmed Facts
            </span>
            <span className="text-[10px] font-mono text-emerald-400 px-2 py-0.5 rounded-full bg-emerald-950 border border-emerald-800">
              VERIFIED GROUND TRUTH
            </span>
          </div>
          <div className="p-3 space-y-2 text-xs">
            {response.confirmed_facts.map((fact, idx) => (
              <div key={idx} className="flex flex-col gap-1 border-b border-emerald-950/80 pb-2 last:border-0 last:pb-0">
                <div className="text-slate-200 flex items-start gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 mt-1.5 shrink-0" />
                  <span className="leading-relaxed">{(fact as any).statement || (fact as any).fact || String(fact)}</span>
                </div>
                {fact.citations && fact.citations.length > 0 && (
                  <div className="flex flex-wrap gap-1 pl-3.5 mt-0.5">
                    {fact.citations.map((c: any, cIdx) => {
                      const cStr = typeof c === 'string' ? c : (c.id || c.node || 'Citation');
                      return (
                        <button
                          key={cIdx}
                          onClick={() => onSelectCitation(cStr)}
                          className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-800/80 hover:bg-emerald-900 transition"
                        >
                          <span>{cStr}</span>
                          <ExternalLink className="w-2.5 h-2.5" />
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 4. Unverified Reports (Amber) */}
      {hasUnverified && (
        <div className="rounded-xl border border-amber-900/60 bg-amber-950/20 overflow-hidden shadow-sm">
          <div className="px-3.5 py-2 bg-amber-950/50 border-b border-amber-900/40 flex items-center justify-between">
            <span className="text-xs font-bold text-amber-400 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-400" />
              Unverified Reports
            </span>
            <span className="text-[10px] font-mono text-amber-400 px-2 py-0.5 rounded-full bg-amber-950 border border-amber-800">
              PENDING CORROBORATION
            </span>
          </div>
          <div className="p-3 space-y-2 text-xs">
            {response.unverified_reports.map((report, idx) => (
              <div key={idx} className="flex flex-col gap-1 border-b border-amber-950/80 pb-2 last:border-0 last:pb-0">
                <div className="text-slate-200 flex items-start gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400 mt-1.5 shrink-0" />
                  <span className="leading-relaxed">{(report as any).statement || (report as any).report || String(report)}</span>
                </div>
                <div className="flex items-center gap-2 pl-3.5 text-[11px] text-amber-300/80">
                  <span>Source: {report.source || 'Operational Report'}</span>
                  {report.citations && report.citations.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {report.citations.map((c: any, cIdx) => {
                        const cStr = typeof c === 'string' ? c : (c.id || c.node || 'Citation');
                        return (
                          <button
                            key={cIdx}
                            onClick={() => onSelectCitation(cStr)}
                            className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-800/80 hover:bg-amber-900 transition"
                          >
                            <span>{cStr}</span>
                            <ExternalLink className="w-2.5 h-2.5" />
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 5. System Inferences (Purple) */}
      {hasInferences && (
        <div className="rounded-xl border border-purple-900/60 bg-purple-950/20 overflow-hidden shadow-sm">
          <div className="px-3.5 py-2 bg-purple-950/50 border-b border-purple-900/40 flex items-center justify-between">
            <span className="text-xs font-bold text-purple-300 flex items-center gap-2">
              <Lightbulb className="w-4 h-4 text-purple-400" />
              System Inferences & Projections
            </span>
            <span className="text-[10px] font-mono text-purple-300 px-2 py-0.5 rounded-full bg-purple-950 border border-purple-800">
              CAUSAL DEDUCTIONS
            </span>
          </div>
          <div className="p-3 space-y-2 text-xs">
            {response.system_inferences.map((inf, idx) => (
              <div key={idx} className="flex flex-col gap-1 border-b border-purple-950/80 pb-2 last:border-0 last:pb-0">
                <div className="text-slate-200 flex items-start gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-purple-400 mt-1.5 shrink-0" />
                  <span className="leading-relaxed font-medium">{(inf as any).deduction || (inf as any).inference || String(inf)}</span>
                </div>
                <div className="pl-3.5 text-[11px] text-purple-300/80 flex items-center gap-2">
                  <span>Rationale: {inf.rationale}</span>
                  <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-purple-900/50 text-purple-200">
                    Confidence: {inf.confidence || 'HIGH'}
                  </span>
                </div>
                {inf.supporting_citations && inf.supporting_citations.length > 0 && (
                  <div className="flex flex-wrap gap-1 pl-3.5 mt-0.5">
                    {inf.supporting_citations.map((c: any, cIdx) => {
                      const cStr = typeof c === 'string' ? c : (c.id || c.node || 'Citation');
                      return (
                        <button
                          key={cIdx}
                          onClick={() => onSelectCitation(cStr)}
                          className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-purple-950/80 text-purple-300 border border-purple-800/80 hover:bg-purple-900 transition"
                        >
                          <span>{cStr}</span>
                          <ExternalLink className="w-2.5 h-2.5" />
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 6. Cypher Execution Audit Accordion */}
      {hasCypher && (
        <div className="rounded-xl border border-ocean-700 bg-ocean-900/80 overflow-hidden text-xs">
          <button
            onClick={() => setShowCypher(!showCypher)}
            className="w-full px-3.5 py-2 flex items-center justify-between bg-ocean-850 hover:bg-ocean-800 text-slate-300 transition"
          >
            <span className="flex items-center gap-2 font-mono text-[11px] text-cyan-400">
              <Database className="w-3.5 h-3.5" />
              Cypher Graph Queries Executed ({response.cypher_queries_executed.length})
            </span>
            {showCypher ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
          </button>
          {showCypher && (
            <div className="p-3 space-y-2 bg-ocean-950/90 font-mono text-[11px]">
              {response.cypher_queries_executed.map((q, idx) => (
                <div key={idx} className="relative group bg-ocean-900 p-2.5 rounded-lg border border-ocean-800">
                  <div className="text-cyan-300 whitespace-pre-wrap break-all pr-8">{q}</div>
                  <button
                    onClick={() => handleCopyCypher(q, idx)}
                    className="absolute top-2 right-2 text-slate-400 hover:text-white p-1 rounded hover:bg-ocean-800 transition"
                    title="Copy Cypher Query"
                  >
                    {copiedIndex === idx ? (
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

