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
    <div className="fixed inset-y-0 right-0 w-full max-w-lg bg-ocean-900 border-l border-ocean-700 shadow-2xl z-40 flex flex-col transition-transform duration-300">
      {/* Header */}
      <div className="px-5 py-4 border-b border-ocean-700 flex items-center justify-between bg-ocean-850">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800">
            {isMessage ? <FileText className="w-4 h-4" /> : <Database className="w-4 h-4" />}
          </div>
          <div>
            <h3 className="text-sm font-bold text-white truncate max-w-xs">
              {isMessage ? msgCitation?.filename : `${entityCitation?.label}: ${entityCitation?.primary_id}`}
            </h3>
            <span className="text-[11px] text-slate-400 font-mono">
              Citation ID: {citation.citation_id}
            </span>
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-white p-1 rounded-md hover:bg-ocean-800 transition"
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
              <div className="p-2.5 rounded-lg bg-ocean-800/80 border border-ocean-700/80">
                <span className="text-slate-400 block mb-1 flex items-center gap-1">
                  <Shield className="w-3 h-3 text-cyan-400" /> Trust Tier
                </span>
                <span
                  className={`font-mono font-bold px-2 py-0.5 rounded text-xs ${
                    msgCitation.trust_tier === 'T1'
                      ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                      : msgCitation.trust_tier === 'T2'
                      ? 'bg-sky-950 text-sky-300 border border-sky-800'
                      : msgCitation.trust_tier === 'T3'
                      ? 'bg-amber-950 text-amber-300 border border-amber-800'
                      : 'bg-rose-950 text-rose-300 border border-rose-800'
                  }`}
                >
                  {msgCitation.trust_tier}
                </span>
              </div>
              <div className="p-2.5 rounded-lg bg-ocean-800/80 border border-ocean-700/80">
                <span className="text-slate-400 block mb-1 flex items-center gap-1">
                  <Mail className="w-3 h-3 text-cyan-400" /> Message Type
                </span>
                <span className="text-slate-200 font-medium truncate block">{msgCitation.message_type}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-ocean-800/80 border border-ocean-700/80 col-span-2">
                <span className="text-slate-400 block mb-1 flex items-center gap-1">
                  <Mail className="w-3 h-3 text-cyan-400" /> Sender
                </span>
                <span className="text-cyan-300 font-mono text-[11px] truncate block">{msgCitation.sender}</span>
              </div>
              {msgCitation.sent_at_utc && (
                <div className="p-2.5 rounded-lg bg-ocean-800/80 border border-ocean-700/80 col-span-2">
                  <span className="text-slate-400 block mb-1 flex items-center gap-1">
                    <Calendar className="w-3 h-3 text-cyan-400" /> Timestamp UTC
                  </span>
                  <span className="text-slate-200 font-mono text-[11px]">{msgCitation.sent_at_utc}</span>
                </div>
              )}
            </div>

            {/* Verbatim Raw Message Card */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="font-semibold text-slate-300 uppercase tracking-wider text-[11px]">
                  Verbatim Message Content
                </span>
                <button
                  onClick={() => handleCopyRaw(msgCitation.raw_message)}
                  className="text-cyan-400 hover:text-cyan-300 text-[11px] flex items-center gap-1"
                >
                  {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                  <span>{copied ? 'Copied' : 'Copy Text'}</span>
                </button>
              </div>
              <div className="bg-ocean-950 p-3.5 rounded-xl border border-ocean-800 font-mono text-[11px] text-slate-300 leading-relaxed whitespace-pre-wrap select-text">
                {msgCitation.raw_message}
              </div>
            </div>
          </div>
        )}

        {/* Entity Data Citation View */}
        {entityCitation && (
          <div className="space-y-4">
            <div className="p-3 rounded-lg bg-ocean-800/80 border border-ocean-700/80 flex items-center justify-between">
              <div>
                <span className="text-slate-400 text-[10px] uppercase tracking-wider block">Graph Entity Label</span>
                <span className="text-sm font-bold text-cyan-300">{entityCitation.label}</span>
              </div>
              <div>
                <span className="text-slate-400 text-[10px] uppercase tracking-wider block">Primary Key</span>
                <span className="text-sm font-mono font-bold text-white">{entityCitation.primary_id}</span>
              </div>
            </div>

            {/* Attributes Key-Value Table */}
            <div>
              <span className="font-semibold text-slate-300 uppercase tracking-wider text-[11px] block mb-2">
                Node Attributes
              </span>
              <div className="rounded-xl border border-ocean-800 overflow-hidden bg-ocean-950">
                <table className="w-full text-left text-[11px]">
                  <tbody>
                    {Object.entries(entityCitation.attributes || {}).map(([key, val], idx) => (
                      <tr key={idx} className="border-b border-ocean-850 last:border-0 hover:bg-ocean-900/60">
                        <td className="py-2 px-3 text-slate-400 font-mono font-medium w-1/3 bg-ocean-900/30">{key}</td>
                        <td className="py-2 px-3 text-slate-200 font-mono">
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
                <span className="font-semibold text-slate-300 uppercase tracking-wider text-[11px] block mb-2">
                  Backing Messages ({entityCitation.backing_messages.length})
                </span>
                <div className="space-y-2">
                  {entityCitation.backing_messages.map((bm, idx) => (
                    <div key={idx} className="p-3 rounded-lg bg-ocean-850 border border-ocean-750 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-cyan-400 text-[11px] font-medium">{bm.filename}</span>
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-ocean-800 text-slate-300">
                          {bm.trust_tier}
                        </span>
                      </div>
                      <div className="text-[11px] text-slate-400 italic truncate">{bm.sender}</div>
                      <div className="bg-ocean-950 p-2 rounded text-[11px] text-slate-300 font-mono whitespace-pre-wrap max-h-32 overflow-y-auto">
                        {bm.raw_message}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

