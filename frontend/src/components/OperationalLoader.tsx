import React, { useState, useEffect } from 'react';
import { Loader2, Radio, Compass } from 'lucide-react';

export interface LoaderMessage {
  title: string;
  detail: string;
}

export const MARITIME_LOADER_MESSAGES: LoaderMessage[] = [
  {
    title: 'Traversing Maritime Knowledge Graph & validating ground truth...',
    detail: 'Executing read-only Cypher queries across vessel, voyage, and port nodes.',
  },
  {
    title: 'Cross-referencing operational noon reports & agent communications...',
    detail: 'Filtering text signals across trust tiers (T1–T4) and suppressing unverified claims.',
  },
  {
    title: 'Auditing port congestion indices & berth window schedules...',
    detail: 'Evaluating anchorage wait times, pilotage assignments, and queue depths.',
  },
  {
    title: 'Analyzing cargo exposure & container booking allocations...',
    detail: 'Scanning rolled bookings, high-risk cargo classes, and bill-of-lading impacts.',
  },
  {
    title: 'Reconciling voyage timeline disruptions & AIS telemetry...',
    detail: 'Reconstructing chronological event chains across waypoint timestamps.',
  },
  {
    title: 'Checking technical bulletin advisories & auxiliary engine logs...',
    detail: 'Parsing propulsion maintenance advisories, spare parts lead times, and class approvals.',
  },
  {
    title: 'Correlating maritime incident records & historical casualty logs...',
    detail: 'Assessing root causes, historical precedent, and spatial proximity alerts.',
  },
  {
    title: 'Validating commercial claims, demurrage risks & charterparty terms...',
    detail: 'Cross-checking laytime exceptions, notice of readiness, and off-hire clauses.',
  },
  {
    title: 'Verifying severe weather advisories & adverse sea-state alerts...',
    detail: 'Correlating tropical storm warnings and significant wave heights with speed reductions.',
  },
  {
    title: 'Evaluating pilot boarding delays & terminal crane productivity...',
    detail: 'Cross-referencing harbor master dispatches with terminal throughput metrics.',
  },
  {
    title: 'Executing epistemic segregation & deterministic citation hydration...',
    detail: 'Segregating Confirmed Facts, Unverified Reports, and Inferences against Neo4j truth.',
  },
  {
    title: 'Synthesizing multi-hop operational intelligence report...',
    detail: 'Finalizing primary citation references and assembling executive operational response.',
  },
];

interface OperationalLoaderProps {
  /** Optional custom message list override */
  messages?: LoaderMessage[];
  /** Rotation interval in milliseconds, defaults to 60000ms (1 minute) */
  rotationIntervalMs?: number;
}

export const OperationalLoader: React.FC<OperationalLoaderProps> = ({
  messages = MARITIME_LOADER_MESSAGES,
  rotationIntervalMs = 60000,
}) => {
  // Start with a random message
  const [currentIndex, setCurrentIndex] = useState<number>(() =>
    Math.floor(Math.random() * messages.length)
  );
  const [isVisible, setIsVisible] = useState<boolean>(true);

  // Interval: rotate to another random message every 1 minute
  useEffect(() => {
    if (messages.length <= 1) return;

    const interval = setInterval(() => {
      // Fade out slightly
      setIsVisible(false);

      setTimeout(() => {
        setCurrentIndex((prev) => {
          let next = Math.floor(Math.random() * messages.length);
          while (next === prev) {
            next = Math.floor(Math.random() * messages.length);
          }
          return next;
        });
        setIsVisible(true);
      }, 300);
    }, rotationIntervalMs);

    return () => clearInterval(interval);
  }, [messages, rotationIntervalMs]);

  const activeMsg = messages[currentIndex] || messages[0];

  return (
    <div className="flex gap-3 text-sm items-start animate-fadeIn">
      {/* Avatar Spinner */}
      <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-sky-50 to-teal-50 border border-sky-300 flex items-center justify-center shrink-0 text-teal-600 relative shadow-xs">
        <Loader2 className="w-4 h-4 animate-spin text-teal-600" />
        <span className="absolute -top-0.5 -right-0.5 flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-teal-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-teal-500"></span>
        </span>
      </div>

      {/* Main Loader Bubble */}
      <div className="bg-white rounded-3xl rounded-tl-xs border-2 border-sky-200/90 p-4 max-w-lg shadow-sm space-y-2.5">
        {/* Status Header */}
        <div className="flex items-center justify-between gap-2 border-b border-sky-100 pb-2">
          <div className="flex items-center gap-1.5 text-teal-700 font-mono text-[11px] font-semibold tracking-wide uppercase">
            <Radio className="w-3 h-3 text-teal-600 animate-pulse" />
            <span>Reasoning Active</span>
          </div>

          <div className="flex items-center gap-1.5 text-[11px] text-sky-800 font-mono">
            <span className="w-1.5 h-1.5 rounded-full bg-teal-500 animate-ping" />
            <span>Operational KG</span>
          </div>
        </div>

        {/* Dynamic Rotating Message with smooth transition */}
        <div
          className={`space-y-1 transition-opacity duration-300 ${
            isVisible ? 'opacity-100 translate-y-0' : 'opacity-20 translate-y-0.5'
          }`}
        >
          <div className="flex items-center gap-2 text-sky-950 text-xs font-semibold">
            <Compass className="w-3.5 h-3.5 text-teal-600 shrink-0 animate-spin [animation-duration:8s]" />
            <span className="line-clamp-2">{activeMsg.title}</span>
          </div>

          <p className="text-[11px] text-slate-600 leading-relaxed pl-5.5">
            {activeMsg.detail}
          </p>
        </div>

        {/* Epistemic assurance footer */}
        <div className="pt-1 flex items-center gap-2 text-[10px] text-slate-500 font-mono">
          <span className="w-1.5 h-1.5 rounded-full bg-teal-500 animate-pulse" />
          <span>Epistemic Guardrails: Verified ground truth enforcement enabled</span>
        </div>
      </div>
    </div>
  );
};
