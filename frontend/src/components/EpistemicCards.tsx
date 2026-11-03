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
    <div className="space-y-3.5 mt-4">
      {/* 0. Data Unavailable Status Banner */}
      {response.status === 'DATA_UNAVAILABLE' && (
        <div className="rounded-2xl border border-sky-300 bg-sky-50/80 p-4 text-xs text-sky-900 flex items-center gap-2.5 shadow-xs">
          <Database className="w-4 h-4 text-teal-600 shrink-0" />
          <span className="leading-relaxed">
            <strong className="text-sky-950 mr-1 font-semibold">No Matching Graph Records:</strong>
            Epistemically declared unavailable without guessing or hallucinating data.
          </span>
        </div>
      )}

      {/* 1. False Premises Banner */}
      {hasFalsePremises && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50/60 overflow-hidden shadow-xs">
          <div className="px-4 py-2.5 bg-rose-100/80 border-b border-rose-200 flex items-center justify-between">
            <span className="text-xs font-bold text-rose-800 flex items-center gap-2">
              <XCircle className="w-4 h-4 text-rose-600" />
              Premise Discrepancy Corrected
            </span>
            <span className="text-[10px] font-mono text-rose-800 px-2 py-0.5 rounded-full bg-rose-200/90 border border-rose-300 font-semibold">
              GROUNDED REALITY
            </span>
          </div>
          <div className="p-4 space-y-2.5 text-xs">
            {response.false_premises_detected.map((p, idx) => (
              <div key={idx} className="bg-white p-3.5 rounded-xl border border-rose-200 shadow-2xs space-y-1.5">
                <div className="text-slate-500 line-through decoration-rose-500 leading-relaxed">
                  <span className="text-rose-700 font-semibold mr-1">Assumption:</span>
                  {p.user_assumption}
                </div>
                <div className="text-slate-900 font-medium flex items-start gap-1.5 leading-relaxed">
                  <span className="text-teal-700 font-bold shrink-0">Reality:</span>
                  <span>{p.grounded_reality}</span>
                </div>
                {p.citations && p.citations.length > 0 && (
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {p.citations.map((c, cIdx) => (
                      <button
                        key={cIdx}
                        onClick={() => onSelectCitation(c)}
                        className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-lg bg-rose-50 text-rose-800 border border-rose-300 hover:bg-rose-100 transition shadow-2xs"
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
        <div className="rounded-2xl border border-sky-300 bg-gradient-to-r from-sky-50 to-teal-50 overflow-hidden shadow-xs">
          <div className="px-4 py-2.5 bg-sky-100/90 border-b border-sky-200 flex items-center gap-2">
            <HelpCircle className="w-4 h-4 text-teal-600" />
            <span className="text-xs font-bold text-sky-950">Operational Clarification Required</span>
          </div>
          <div className="p-4 text-xs space-y-3">
            <p className="text-slate-900 font-semibold leading-relaxed">{response.clarification.question}</p>
            {response.clarification.reason && (
              <p className="text-[11px] text-slate-600 italic leading-relaxed">{response.clarification.reason}</p>
            )}
            <div className="flex flex-wrap gap-2 pt-1">
              {response.clarification.options.map((opt) => (
                <button
                  key={opt.option_id}
                  onClick={() => onClarificationChoice(opt.label)}
                  className="px-3.5 py-2 rounded-xl bg-white hover:bg-sky-50 text-sky-950 hover:text-sky-900 border border-sky-300 font-medium text-xs transition shadow-2xs flex items-center gap-1.5"
                >
                  <span>{opt.label}</span>
                  {opt.description && (
                    <span className="text-[10px] text-teal-700">({opt.description})</span>
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 3. Confirmed Facts (Soft Teal) */}
      {hasConfirmed && (
        <div className="rounded-2xl border border-teal-200/90 bg-teal-50/60 overflow-hidden shadow-xs">
          <div className="px-4 py-2.5 bg-teal-100/70 border-b border-teal-200 flex items-center justify-between">
            <span className="text-xs font-bold text-teal-900 flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-teal-600" />
              Confirmed Facts
            </span>
            <span className="text-[10px] font-mono text-teal-900 px-2 py-0.5 rounded-full bg-teal-200/80 border border-teal-300 font-semibold">
              VERIFIED GROUND TRUTH
            </span>
          </div>
          <div className="p-4 space-y-2.5 text-xs">
            {response.confirmed_facts.map((fact, idx) => (
              <div key={idx} className="flex flex-col gap-1.5 border-b border-teal-100/80 pb-2.5 last:border-0 last:pb-0">
                <div className="text-slate-800 flex items-start gap-2 leading-relaxed">
                  <span className="w-1.5 h-1.5 rounded-full bg-teal-500 mt-1.5 shrink-0" />
                  <span className="leading-relaxed">{(fact as any).statement || (fact as any).fact || String(fact)}</span>
                </div>
                {fact.citations && fact.citations.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pl-3.5 mt-0.5">
                    {fact.citations.map((c: any, cIdx) => {
                      const cStr = typeof c === 'string' ? c : (c.id || c.node || 'Citation');
                      return (
                        <button
                          key={cIdx}
                          onClick={() => onSelectCitation(cStr)}
                          className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-lg bg-white text-teal-800 border border-teal-300 hover:bg-teal-50 transition shadow-2xs"
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

      {/* 4. Unverified Reports (Soft Amber) */}
      {hasUnverified && (
        <div className="rounded-2xl border border-amber-200/90 bg-amber-50/60 overflow-hidden shadow-xs">
          <div className="px-4 py-2.5 bg-amber-100/70 border-b border-amber-200 flex items-center justify-between">
            <span className="text-xs font-bold text-amber-900 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600" />
              Unverified Reports
            </span>
            <span className="text-[10px] font-mono text-amber-900 px-2 py-0.5 rounded-full bg-amber-200/80 border border-amber-300 font-semibold">
              PENDING CORROBORATION
            </span>
          </div>
          <div className="p-4 space-y-2.5 text-xs">
            {response.unverified_reports.map((report, idx) => (
              <div key={idx} className="flex flex-col gap-1.5 border-b border-amber-100/80 pb-2.5 last:border-0 last:pb-0">
                <div className="text-slate-800 flex items-start gap-2 leading-relaxed">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-500 mt-1.5 shrink-0" />
                  <span className="leading-relaxed">{(report as any).statement || (report as any).report || String(report)}</span>
                </div>
                <div className="flex items-center gap-2 pl-3.5 text-[11px] text-amber-900">
                  <span>Source: {report.source || 'Operational Report'}</span>
                  {report.citations && report.citations.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {report.citations.map((c: any, cIdx) => {
                        const cStr = typeof c === 'string' ? c : (c.id || c.node || 'Citation');
                        return (
                          <button
                            key={cIdx}
                            onClick={() => onSelectCitation(cStr)}
                            className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-lg bg-white text-amber-900 border border-amber-300 hover:bg-amber-50 transition shadow-2xs"
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

      {/* 5. System Inferences (Pastel Sky Blue) */}
      {hasInferences && (
        <div className="rounded-2xl border border-sky-200/90 bg-sky-50/60 overflow-hidden shadow-xs">
          <div className="px-4 py-2.5 bg-sky-100/70 border-b border-sky-200 flex items-center justify-between">
            <span className="text-xs font-bold text-sky-950 flex items-center gap-2">
              <Lightbulb className="w-4 h-4 text-sky-600" />
              System Inferences & Projections
            </span>
            <span className="text-[10px] font-mono text-sky-900 px-2 py-0.5 rounded-full bg-sky-200/80 border border-sky-300 font-semibold">
              CAUSAL DEDUCTIONS
            </span>
          </div>
          <div className="p-4 space-y-2.5 text-xs">
            {response.system_inferences.map((inf, idx) => (
              <div key={idx} className="flex flex-col gap-1.5 border-b border-sky-100/80 pb-2.5 last:border-0 last:pb-0">
                <div className="text-slate-800 flex items-start gap-2 leading-relaxed">
                  <span className="w-1.5 h-1.5 rounded-full bg-sky-500 mt-1.5 shrink-0" />
                  <span className="leading-relaxed font-medium">{(inf as any).deduction || (inf as any).inference || String(inf)}</span>
                </div>
                <div className="pl-3.5 text-[11px] text-sky-900 flex items-center gap-2">
                  <span>Rationale: {inf.rationale}</span>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-sky-200/70 text-sky-950 border border-sky-300">
                    Confidence: {inf.confidence || 'HIGH'}
                  </span>
                </div>
                {inf.supporting_citations && inf.supporting_citations.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pl-3.5 mt-0.5">
                    {inf.supporting_citations.map((c: any, cIdx) => {
                      const cStr = typeof c === 'string' ? c : (c.id || c.node || 'Citation');
                      return (
                        <button
                          key={cIdx}
                          onClick={() => onSelectCitation(cStr)}
                          className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-lg bg-white text-sky-900 border border-sky-300 hover:bg-sky-50 transition shadow-2xs"
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
        <div className="rounded-2xl border border-sky-200 bg-white overflow-hidden text-xs shadow-xs">
          <button
            onClick={() => setShowCypher(!showCypher)}
            className="w-full px-4 py-2.5 flex items-center justify-between bg-sky-50/70 hover:bg-sky-100/70 text-sky-950 transition"
          >
            <span className="flex items-center gap-2 font-mono text-[11px] text-sky-950 font-medium">
              <Database className="w-3.5 h-3.5 text-teal-600" />
              Cypher Graph Queries Executed ({response.cypher_queries_executed.length})
            </span>
            {showCypher ? <ChevronDown className="w-3.5 h-3.5 text-slate-500" /> : <ChevronRight className="w-3.5 h-3.5 text-slate-500" />}
          </button>
          {showCypher && (
            <div className="p-4 space-y-2.5 bg-[#0c1f38] font-mono text-[11px] text-slate-100">
              {response.cypher_queries_executed.map((q, idx) => (
                <div key={idx} className="relative group bg-[#081527] p-3 rounded-xl border border-sky-900/60">
                  <div className="text-teal-300 whitespace-pre-wrap break-all pr-8 leading-relaxed">{q}</div>
                  <button
                    onClick={() => handleCopyCypher(q, idx)}
                    className="absolute top-2 right-2 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-sky-900/60 transition"
                    title="Copy Cypher Query"
                  >
                    {copiedIndex === idx ? (
                      <Check className="w-3.5 h-3.5 text-teal-400" />
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
