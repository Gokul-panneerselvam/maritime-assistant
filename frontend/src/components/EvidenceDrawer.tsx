import React, { useEffect } from 'react';
import { X, FileText, Database, Shield, Mail, Calendar, Copy, Check } from 'lucide-react';
import { Citation, MessageCitation, EntityDataCitation } from '../types/maritime';

interface EvidenceDrawerProps {
  citation: Citation | null;
  onClose: () => void;
}

export const EvidenceDrawer: React.FC<EvidenceDrawerProps> = ({ citation, onClose }) => {
  const [copied, setCopied] = React.useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  if (!citation) return null;

  const isMessage = 'filename' in citation && 'raw_message' in citation;
  const msgCitation = isMessage ? (citation as MessageCitation) : null;
  const entityCitation = !isMessage ? (citation as EntityDataCitation) : null;

  const handleCopyRaw = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-y-0 right-0 w-full max-w-lg bg-white border-l border-sky-200 shadow-2xl z-40 flex flex-col transition-transform duration-300">
      {/* Header */}
      <div className="px-5 py-4 border-b border-sky-200 flex items-center justify-between bg-[#edf5fb]">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-xl bg-gradient-to-tr from-sky-100 to-teal-100 text-teal-700 border border-sky-300 shadow-2xs">
            {isMessage ? <FileText className="w-4 h-4" /> : <Database className="w-4 h-4" />}
          </div>
          <div>
            <h3 className="text-sm font-bold text-sky-950 truncate max-w-xs">
              {isMessage ? msgCitation?.filename : `${entityCitation?.label}: ${entityCitation?.primary_id}`}
            </h3>
            <span className="text-[11px] text-sky-800 font-mono">
              Citation ID: {citation.citation_id}
            </span>
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-slate-700 p-1.5 rounded-lg hover:bg-sky-100 transition"
          title="Close Inspector"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-5 space-y-4 text-xs">
        {/* Message Citation View */}
        {msgCitation && (
          <div className="space-y-4">
            {/* Metadata Pills */}
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div className="p-2.5 rounded-xl bg-[#f4f9fd] border border-sky-200/80">
                <span className="text-slate-500 block mb-1 flex items-center gap-1 font-medium">
                  <Shield className="w-3 h-3 text-teal-600" /> Trust Tier
                </span>
                <span
                  className={`font-mono font-bold px-2 py-0.5 rounded text-xs ${
                    msgCitation.trust_tier === 'T1'
                      ? 'bg-teal-100 text-teal-800 border border-teal-300'
                      : msgCitation.trust_tier === 'T2'
                      ? 'bg-sky-100 text-sky-800 border border-sky-300'
                      : msgCitation.trust_tier === 'T3'
                      ? 'bg-amber-100 text-amber-800 border border-amber-300'
                      : 'bg-rose-100 text-rose-800 border border-rose-300'
                  }`}
                >
                  {msgCitation.trust_tier}
                </span>
              </div>
              <div className="p-2.5 rounded-xl bg-[#f4f9fd] border border-sky-200/80">
                <span className="text-slate-500 block mb-1 flex items-center gap-1 font-medium">
                  <Mail className="w-3 h-3 text-teal-600" /> Message Type
                </span>
                <span className="text-slate-900 font-medium truncate block">{msgCitation.message_type}</span>
              </div>
              <div className="p-2.5 rounded-xl bg-[#f4f9fd] border border-sky-200/80 col-span-2">
                <span className="text-slate-500 block mb-1 flex items-center gap-1 font-medium">
                  <Mail className="w-3 h-3 text-teal-600" /> Sender
                </span>
                <span className="text-sky-900 font-mono text-[11px] truncate block font-medium">{msgCitation.sender}</span>
              </div>
              {msgCitation.sent_at_utc && (
                <div className="p-2.5 rounded-xl bg-[#f4f9fd] border border-sky-200/80 col-span-2">
                  <span className="text-slate-500 block mb-1 flex items-center gap-1 font-medium">
                    <Calendar className="w-3 h-3 text-teal-600" /> Timestamp UTC
                  </span>
                  <span className="text-slate-800 font-mono text-[11px]">{msgCitation.sent_at_utc}</span>
                </div>
              )}
            </div>

            {/* Verbatim Raw Message Card */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="font-semibold text-sky-950 uppercase tracking-wider text-[11px]">
                  Verbatim Message Content
                </span>
                <button
                  onClick={() => handleCopyRaw(msgCitation.raw_message)}
                  className="text-teal-700 hover:text-teal-800 text-[11px] flex items-center gap-1 font-medium"
                >
                  {copied ? <Check className="w-3 h-3 text-teal-600" /> : <Copy className="w-3 h-3" />}
                  <span>{copied ? 'Copied' : 'Copy Text'}</span>
                </button>
              </div>
              <div className="bg-[#f4f9fd] p-3.5 rounded-2xl border border-sky-200 font-mono text-[11px] text-slate-800 leading-relaxed whitespace-pre-wrap select-text">
                {msgCitation.raw_message || 'No verbatim content recorded.'}
              </div>
            </div>
          </div>
        )}

        {/* Entity Data Citation View */}
        {entityCitation && (
          <div className="space-y-4">
            <div className="p-3.5 rounded-2xl bg-gradient-to-r from-sky-50 to-teal-50 border border-sky-200 flex items-center justify-between">
              <div>
                <span className="text-slate-500 text-[10px] uppercase tracking-wider block font-medium">Graph Entity Label</span>
                <span className="text-sm font-bold text-teal-800">{entityCitation.label}</span>
              </div>
              <div>
                <span className="text-slate-500 text-[10px] uppercase tracking-wider block font-medium">Primary Key</span>
                <span className="text-sm font-mono font-bold text-sky-950">{entityCitation.primary_id}</span>
              </div>
            </div>

            {/* Attributes Key-Value Table */}
            <div>
              <span className="font-semibold text-sky-950 uppercase tracking-wider text-[11px] block mb-2">
                Node Attributes
              </span>
              <div className="rounded-2xl border border-sky-200 overflow-hidden bg-white shadow-2xs">
                <table className="w-full text-left text-[11px]">
                  <tbody>
                    {Object.entries(entityCitation.attributes || {}).map(([key, val], idx) => (
                      <tr key={idx} className="border-b border-sky-100 last:border-0 hover:bg-sky-50/60">
                        <td className="py-2 px-3 text-slate-600 font-mono font-medium w-1/3 bg-[#f4f9fd]">{key}</td>
                        <td className="py-2 px-3 text-slate-900 font-mono">
                          {val === null || val === undefined
                            ? '<null>'
                            : typeof val === 'object'
                            ? JSON.stringify(val)
                            : String(val)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Backing Messages Traversed */}
            {entityCitation.backing_messages && entityCitation.backing_messages.length > 0 && (
              <div>
                <span className="font-semibold text-sky-950 uppercase tracking-wider text-[11px] block mb-2">
                  Backing Messages ({entityCitation.backing_messages.length})
                </span>
                <div className="space-y-2">
                  {entityCitation.backing_messages.map((bm, idx) => {
                    const messageContent =
                      bm.raw_message ||
                      (bm as any).cleaned_body ||
                      (bm as any).snippet ||
                      '';
                    return (
                      <div key={idx} className="p-3 rounded-2xl bg-[#f4f9fd] border border-sky-200 space-y-1.5 shadow-2xs">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-teal-800 text-[11px] font-semibold">{bm.filename}</span>
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white border border-sky-200 text-slate-700 font-medium">
                            {bm.trust_tier}
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-500 italic truncate">{bm.sender}</div>
                        {messageContent ? (
                          <div className="bg-white p-2 rounded-xl border border-sky-200 text-[11px] text-slate-800 font-mono whitespace-pre-wrap max-h-32 overflow-y-auto">
                            {messageContent}
                          </div>
                        ) : (
                          <div className="bg-white/60 p-2 rounded-xl border border-dashed border-sky-200 text-[10px] text-slate-400 font-mono italic">
                            No verbatim content recorded
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
