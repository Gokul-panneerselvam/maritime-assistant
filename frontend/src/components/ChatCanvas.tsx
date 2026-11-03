import React, { useRef, useEffect } from 'react';
import { Send, Sparkles, Ship } from 'lucide-react';
import { marked } from 'marked';
import { ChatMessage } from '../types/maritime';
import { EpistemicCards } from './EpistemicCards';
import { OperationalLoader } from './OperationalLoader';

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
    <main className="flex-1 flex flex-col bg-[#e8f2fa] overflow-hidden relative">
      {/* Messages Stream */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.length === 0 ? (
          /* Welcome Banner */
          <div className="max-w-2xl mx-auto my-10 text-center p-8 rounded-3xl bg-white border border-sky-200/80 shadow-md">
            <div className="inline-flex p-3.5 rounded-2xl bg-gradient-to-tr from-sky-100 to-teal-100 border border-sky-200 text-teal-700 mb-4 shadow-xs">
              <Ship className="w-8 h-8" />
            </div>
            <h2 className="text-xl font-bold text-sky-950 mb-2">Maritime Operations Reasoning Agent</h2>
            <p className="text-xs text-slate-600 mb-6 max-w-lg mx-auto leading-relaxed">
              Autonomous fleet intelligence connected to the Maritime Knowledge Graph.
              Answers strictly enforce 3-way epistemic segregation to eliminate hallucination.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-left text-xs mb-6">
              <div className="p-3.5 rounded-2xl bg-teal-50/70 border border-teal-200/90 shadow-2xs">
                <span className="font-semibold text-teal-800 flex items-center gap-1.5 mb-1 text-xs">
                  <span className="w-2 h-2 rounded-full bg-teal-500" /> Confirmed Facts
                </span>
                <p className="text-[11px] text-teal-950/80 leading-relaxed">
                  Verified tabular data (status = 'Confirmed') & master reports.
                </p>
              </div>

              <div className="p-3.5 rounded-2xl bg-amber-50/70 border border-amber-200/90 shadow-2xs">
                <span className="font-semibold text-amber-800 flex items-center gap-1.5 mb-1 text-xs">
                  <span className="w-2 h-2 rounded-full bg-amber-500" /> Unverified Reports
                </span>
                <p className="text-[11px] text-amber-950/80 leading-relaxed">
                  Crew operational relays & pending uncorroborated alerts.
                </p>
              </div>

              <div className="p-3.5 rounded-2xl bg-sky-50/70 border border-sky-200/90 shadow-2xs">
                <span className="font-semibold text-sky-800 flex items-center gap-1.5 mb-1 text-xs">
                  <span className="w-2 h-2 rounded-full bg-sky-500" /> System Inferences
                </span>
                <p className="text-[11px] text-sky-950/80 leading-relaxed">
                  ETA projections, container miss risk, & causality models.
                </p>
              </div>
            </div>

            <div className="text-[11px] text-sky-900/70 border-t border-sky-100 pt-4 flex flex-wrap justify-center gap-2">
              <span>Try asking:</span>
              <button
                onClick={() => onSamplePromptClick('Why was Voyage VG-1042 delayed in Singapore?')}
                className="text-teal-700 hover:text-teal-800 underline underline-offset-2 font-semibold"
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
                <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-sky-600 via-teal-600 to-teal-500 border border-sky-300 flex items-center justify-center shrink-0 text-white shadow-xs">
                  <Sparkles className="w-4 h-4" />
                </div>
              )}

              <div
                className={`max-w-3xl rounded-3xl shadow-sm break-words overflow-hidden ${
                  msg.role === 'user'
                    ? 'bg-gradient-to-r from-sky-600 to-teal-700 text-white rounded-tr-xs px-5 py-3.5 max-w-2xl'
                    : 'bg-white text-slate-800 rounded-tl-xs border border-sky-200/90 w-full p-6 sm:p-7'
                }`}
              >
                {msg.role === 'user' ? (
                  <p className="text-xs leading-relaxed whitespace-pre-wrap break-words">{msg.content}</p>
                ) : (
                  <div>
                    {/* Executive Summary Markdown */}
                    <div
                      className="prose-maritime text-xs leading-relaxed max-w-none break-words"
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
                <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-sky-200 to-teal-200 border border-sky-300 flex items-center justify-center shrink-0 text-xs font-bold text-sky-900 shadow-2xs">
                  GP
                </div>
              )}
            </div>
          ))
        )}

        {/* Dynamic Maritime Operational Loader */}
        {loading && <OperationalLoader />}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Bar */}
      <div className="p-4 bg-white/95 backdrop-blur-md border-t border-sky-200/90 shrink-0 shadow-xs">
        <form onSubmit={onSendMessage} className="max-w-4xl mx-auto flex items-end gap-3">
          <div className="flex-1 relative">
            <textarea
              value={inputText}
              onChange={(e) => onInputChange(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              placeholder="Ask an operational inquiry (e.g. 'What caused the delay of MV Ocean Star on Voyage 1042?')..."
              className="w-full bg-[#f4f9fd] text-slate-900 placeholder-slate-400 text-xs rounded-2xl px-5 py-3.5 border border-sky-200 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500 focus:bg-white resize-none transition shadow-2xs leading-relaxed min-h-[56px]"
            />
          </div>
          <button
            type="submit"
            disabled={loading || !inputText.trim()}
            className="bg-gradient-to-r from-sky-600 to-teal-600 hover:from-sky-700 hover:to-teal-700 disabled:opacity-40 text-white font-medium p-3.5 rounded-2xl shadow-xs transition flex items-center justify-center shrink-0"
            title="Send Inquiry"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </main>
  );
};
