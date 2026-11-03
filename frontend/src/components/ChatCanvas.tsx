import React, { useRef, useEffect } from 'react';
import { Send, Shield, AlertTriangle, Lightbulb, Loader2, Sparkles, Ship } from 'lucide-react';
import { marked } from 'marked';
import { ChatMessage, MaritimeAgentResponse } from '../types/maritime';
import { EpistemicCards } from './EpistemicCards';

interface ChatCanvasProps {
  messages: ChatMessage[];
  loading: boolean;
  inputText: string;
  onInputChange: (val: string) => void;
  onSendMessage: (e?: React.FormEvent) => void;
  onSelectCitation: (citationId: string) => void;
  onClarificationChoice: (choice: string) => void;
  onSamplePromptClick: (prompt: string) => void;
}

export const ChatCanvas: React.FC<ChatCanvasProps> = ({
  messages,
  loading,
  inputText,
  onInputChange,
  onSendMessage,
  onSelectCitation,
  onClarificationChoice,
  onSamplePromptClick,
}) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSendMessage();
    }
  };

  return (
    <main className="flex-1 flex flex-col bg-ocean-950 overflow-hidden relative">
      {/* Messages Stream */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.length === 0 ? (
          /* Welcome Banner */
          <div className="max-w-2xl mx-auto my-10 text-center p-8 rounded-2xl bg-ocean-900/60 border border-ocean-700/80 shadow-2xl">
            <div className="inline-flex p-3 rounded-2xl bg-cyan-950 border border-cyan-800 text-cyan-400 mb-4 shadow-lg shadow-cyan-950/50">
              <Ship className="w-8 h-8" />
            </div>
            <h2 className="text-xl font-bold text-white mb-2">Maritime Operations Reasoning Agent</h2>
            <p className="text-xs text-slate-300 mb-6 max-w-lg mx-auto leading-relaxed">
              Autonomous fleet intelligence connected to the Maritime Knowledge Graph via FastMCP.
              Answers strictly enforce 3-way epistemic segregation to eliminate hallucination.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-left text-xs mb-6">
              <div className="p-3 rounded-lg bg-ocean-800/60 border border-ocean-700/80">
                <span className="font-semibold text-emerald-400 flex items-center gap-1.5 mb-1">
                  <span className="w-2 h-2 rounded-full bg-emerald-400" /> Confirmed Facts
                </span>
                <p className="text-[11px] text-slate-400">
                  Verified tabular data (status = 'Confirmed') & T1/T2 master reports.
                </p>
              </div>

              <div className="p-3 rounded-lg bg-ocean-800/60 border border-ocean-700/80">
                <span className="font-semibold text-amber-400 flex items-center gap-1.5 mb-1">
                  <span className="w-2 h-2 rounded-full bg-amber-400" /> Unverified Reports
                </span>
                <p className="text-[11px] text-slate-400">
                  Crew WhatsApp relays (T3/T4) & pending uncorroborated alerts.
                </p>
              </div>

              <div className="p-3 rounded-lg bg-ocean-800/60 border border-ocean-700/80">
                <span className="font-semibold text-purple-400 flex items-center gap-1.5 mb-1">
                  <span className="w-2 h-2 rounded-full bg-purple-400" /> System Inferences
                </span>
                <p className="text-[11px] text-slate-400">
                  ETA projections, container miss risk, & causality deduction models.
                </p>
              </div>
            </div>

            <div className="text-[11px] text-slate-400 border-t border-ocean-800 pt-4 flex flex-wrap justify-center gap-2">
              <span className="text-slate-400">Try asking:</span>
              <button
                onClick={() => onSamplePromptClick('Why was Voyage VG-1042 delayed in Singapore?')}
                className="text-cyan-400 hover:text-cyan-300 underline underline-offset-2"
              >
                Why was Voyage VG-1042 delayed in Singapore?
              </button>
            </div>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex gap-3 text-sm ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {msg.role === 'assistant' && (
                <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-cyan-600 to-sky-400 border border-sky-400 flex items-center justify-center shrink-0 text-white shadow-md shadow-cyan-900/40">
                  <Sparkles className="w-4 h-4" />
                </div>
              )}

              <div
                className={`max-w-3xl rounded-2xl p-4 shadow-md ${
                  msg.role === 'user'
                    ? 'bg-ocean-800 text-slate-100 rounded-tr-sm border border-ocean-700'
                    : 'bg-ocean-900/90 text-slate-200 rounded-tl-sm border border-ocean-700/80 w-full'
                }`}
              >
                {msg.role === 'user' ? (
                  <p className="text-xs leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                ) : (
                  <div>
                    {/* Executive Summary Markdown */}
                    <div
                      className="prose-maritime text-xs leading-relaxed"
                      dangerouslySetInnerHTML={{
                        __html: marked.parse(msg.content || ''),
                      }}
                    />

                    {/* Structured Epistemic Cards */}
                    {msg.structured_payload && (
                      <EpistemicCards
                        response={msg.structured_payload}
                        onSelectCitation={onSelectCitation}
                        onClarificationChoice={onClarificationChoice}
                      />
                    )}
                  </div>
                )}
              </div>

              {msg.role === 'user' && (
                <div className="w-8 h-8 rounded-full bg-slate-700 border border-slate-600 flex items-center justify-center shrink-0 text-xs font-bold text-slate-300">
                  U
                </div>
              )}
            </div>
          ))
        )}

        {/* Loading Indicator */}
        {loading && (
          <div className="flex gap-3 text-sm items-start">
            <div className="w-8 h-8 rounded-full bg-cyan-950 border border-cyan-800 flex items-center justify-center shrink-0 text-cyan-400">
              <Loader2 className="w-4 h-4 animate-spin" />
            </div>
            <div className="bg-ocean-900/90 rounded-2xl rounded-tl-sm border border-ocean-700 p-4 max-w-lg shadow-md space-y-2">
              <div className="flex items-center gap-2 text-cyan-300 text-xs font-medium">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Traversing Maritime Knowledge Graph & validating ground truth...</span>
              </div>
              <p className="text-[11px] text-slate-400">
                Executing read-only Cypher queries over FastMCP stdio transport and applying 5-layer epistemic guardrails.
              </p>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Bar */}
      <div className="p-4 bg-ocean-900/95 border-t border-ocean-700/60 shrink-0">
        <form onSubmit={onSendMessage} className="max-w-4xl mx-auto flex items-end gap-3">
          <div className="flex-1 relative">
            <textarea
              value={inputText}
              onChange={(e) => onInputChange(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              placeholder="Ask an operational question (e.g. 'What caused the delay of MV Ocean Star on Voyage 1042?')..."
              className="w-full bg-ocean-800/90 text-slate-100 placeholder-slate-400 text-xs rounded-xl px-4 py-2.5 border border-ocean-700 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 resize-none"
            />
          </div>
          <button
            type="submit"
            disabled={loading || !inputText.trim()}
            className="bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white font-medium p-3 rounded-xl shadow-lg shadow-cyan-900/40 transition flex items-center justify-center shrink-0"
            title="Send Inquiry"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </main>
  );
};

