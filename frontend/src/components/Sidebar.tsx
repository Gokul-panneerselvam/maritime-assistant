import React from 'react';
import { Plus, MessageSquare, Trash2, Clock, Anchor, AlertCircle, Package, Wrench } from 'lucide-react';
import { Thread } from '../types/maritime';

interface SidebarProps {
  threads: Thread[];
  activeThreadId: string | null;
  onSelectThread: (threadId: string) => void;
  onNewThread: () => void;
  onDeleteThread: (threadId: string) => void;
  onRunSamplePrompt: (promptText: string) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  threads,
  activeThreadId,
  onSelectThread,
  onNewThread,
  onDeleteThread,
  onRunSamplePrompt,
}) => {
  return (
    <aside className="w-80 bg-ocean-900/90 border-r border-ocean-700/60 flex flex-col shrink-0 overflow-hidden">
      {/* New Inquiry Action */}
      <div className="p-3 border-b border-ocean-700/60">
        <button
          onClick={onNewThread}
          className="w-full bg-cyan-600 hover:bg-cyan-500 text-white font-medium py-2 px-3 rounded-lg flex items-center justify-center gap-2 shadow-md shadow-cyan-900/30 transition text-xs"
        >
          <Plus className="w-4 h-4" />
          New Operations Inquiry
        </button>
      </div>

      {/* Operational Anchor Banner */}
      <div className="px-3 py-2 bg-ocean-950/60 border-b border-ocean-800 text-[11px] text-slate-400 flex items-center gap-2 font-mono">
        <Clock className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
        <span className="truncate">Anchor: 2026-10-26 12:00 UTC</span>
      </div>

      {/* Inquiry Threads History */}
      <div className="flex-1 overflow-y-auto p-3 space-y-1">
        <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider px-2 py-1 flex items-center justify-between">
          <span>Inquiry Threads</span>
          <span className="text-cyan-400 font-mono text-[10px]">{threads.length}</span>
        </div>

        {threads.length === 0 ? (
          <div className="text-center py-8 text-xs text-slate-400">
            No inquiries yet. Start one above or pick a sample below.
          </div>
        ) : (
          threads.map((t) => {
            const isActive = t.thread_id === activeThreadId;
            return (
              <div
                key={t.thread_id}
                onClick={() => onSelectThread(t.thread_id)}
                className={`group flex items-center justify-between p-2 rounded-lg cursor-pointer text-xs transition border ${
                  isActive
                    ? 'bg-cyan-950/80 text-cyan-300 border-cyan-800 font-medium'
                    : 'text-slate-300 hover:bg-ocean-800 border-transparent'
                }`}
              >
                <div className="truncate flex items-center gap-2 pr-1">
                  <MessageSquare className="w-3.5 h-3.5 shrink-0 opacity-70 text-cyan-400" />
                  <span className="truncate">{t.title || 'Untitled Inquiry'}</span>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteThread(t.thread_id);
                  }}
                  className="opacity-0 group-hover:opacity-100 hover:text-rose-400 p-1 rounded transition"
                  title="Archive Thread"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            );
          })
        )}
      </div>

      {/* Quick Operational Prompts */}
      <div className="p-3 border-t border-ocean-700/60 bg-ocean-850/50 shrink-0">
        <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2 flex items-center justify-between">
          <span>Operational Queries</span>
          <Anchor className="w-3 h-3 text-cyan-400" />
        </div>
        <div className="space-y-1.5 text-xs">
          <button
            onClick={() => onRunSamplePrompt('Why was Voyage VG-1042 delayed in Singapore?')}
            className="w-full text-left p-2 rounded bg-ocean-800/90 hover:bg-ocean-750 text-slate-300 hover:text-white transition truncate border border-ocean-700/50 flex items-center gap-2"
          >
            <AlertCircle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
            <span className="truncate">Voyage 1042 Singapore Delay</span>
          </button>
          <button
            onClick={() => onRunSamplePrompt('Check port congestion and waiting times at Rotterdam and Antwerp')}
            className="w-full text-left p-2 rounded bg-ocean-800/90 hover:bg-ocean-750 text-slate-300 hover:text-white transition truncate border border-ocean-700/50 flex items-center gap-2"
          >
            <Anchor className="w-3.5 h-3.5 text-sky-400 shrink-0" />
            <span className="truncate">Rotterdam & Antwerp Congestion</span>
          </button>
          <button
            onClick={() => onRunSamplePrompt('Find all rolled customer bookings and their root causes')}
            className="w-full text-left p-2 rounded bg-ocean-800/90 hover:bg-ocean-750 text-slate-300 hover:text-white transition truncate border border-ocean-700/50 flex items-center gap-2"
          >
            <Package className="w-3.5 h-3.5 text-rose-400 shrink-0" />
            <span className="truncate">Rolled Bookings & Shippers</span>
          </button>
          <button
            onClick={() => onRunSamplePrompt('Investigate engine cooling fault on MV Ocean Star and related sister ships')}
            className="w-full text-left p-2 rounded bg-ocean-800/90 hover:bg-ocean-750 text-slate-300 hover:text-white transition truncate border border-ocean-700/50 flex items-center gap-2"
          >
            <Wrench className="w-3.5 h-3.5 text-purple-400 shrink-0" />
            <span className="truncate">Engine Fault on Ocean Star</span>
          </button>
        </div>
      </div>
    </aside>
  );
};

