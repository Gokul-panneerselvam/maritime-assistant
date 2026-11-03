import React, { useState } from 'react';
import { Ship, Radio, LogOut, CheckCircle2, AlertTriangle, Settings, RefreshCw } from 'lucide-react';
import { UserProfile } from '../types/maritime';
import { getApiBaseUrl } from '../services/api';

interface NavbarProps {
  user: UserProfile | null;
  neo4jStatus: 'connected' | 'disconnected' | 'checking';
  backendConnected: boolean;
  onLogout: () => void;
  onRefreshHealth: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  user,
  neo4jStatus,
  backendConnected,
  onLogout,
  onRefreshHealth,
}) => {
  const [showConfig, setShowConfig] = useState(false);
  const [customApiUrl, setCustomApiUrl] = useState(getApiBaseUrl());

  const handleSaveApiUrl = () => {
    localStorage.setItem('maritime_api_url', customApiUrl.trim());
    setShowConfig(false);
    window.location.reload();
  };

  const handleResetApiUrl = () => {
    localStorage.removeItem('maritime_api_url');
    setCustomApiUrl(getApiBaseUrl());
    setShowConfig(false);
    window.location.reload();
  };

  return (
    <header className="bg-ocean-900 border-b border-ocean-700/60 px-5 py-3 flex items-center justify-between shrink-0 z-20">
      {/* Brand & Subtitle */}
      <div className="flex items-center gap-3">
        <div className="bg-gradient-to-tr from-cyan-600 to-sky-400 p-2 rounded-lg shadow-lg shadow-sky-500/20 text-white">
          <Ship className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-sm font-bold tracking-wide text-white flex items-center gap-2">
            MARITIME OPS INTELLIGENCE
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800 font-mono">
              v2.0 • React + FastMCP
            </span>
          </h1>
          <p className="text-[11px] text-slate-400">Strict 3-Way Epistemic Separation & Knowledge Graph Grounding</p>
        </div>
      </div>

      {/* Status Indicators & Profile */}
      <div className="flex items-center gap-3 text-xs">
        {/* Backend Connectivity Status */}
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-[11px] transition ${
            backendConnected
              ? 'bg-ocean-800/80 border-ocean-700 text-slate-300'
              : 'bg-rose-950/50 border-rose-800/80 text-rose-300 animate-pulse'
          }`}
          title={backendConnected ? `Connected to ${getApiBaseUrl() || 'Backend'}` : 'Backend connection lost'}
        >
          <span
            className={`w-2 h-2 rounded-full ${
              backendConnected ? 'bg-emerald-400 shadow-sm shadow-emerald-400/50' : 'bg-rose-500'
            }`}
          />
          <span>{backendConnected ? 'API Online' : 'API Offline'}</span>
          <button
            onClick={onRefreshHealth}
            className="hover:text-cyan-300 ml-1 p-0.5"
            title="Refresh connection status"
          >
            <RefreshCw className="w-3 h-3" />
          </button>
        </div>

        {/* Neo4j Status */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-ocean-800 border border-ocean-700 text-slate-300 text-[11px]">
          <span
            className={`w-2 h-2 rounded-full ${
              neo4jStatus === 'connected'
                ? 'bg-cyan-400 animate-pulse'
                : neo4jStatus === 'checking'
                ? 'bg-amber-400'
                : 'bg-rose-500'
            }`}
          />
          <span>
            Neo4j: {neo4jStatus === 'connected' ? 'Connected' : neo4jStatus === 'checking' ? 'Pinging...' : 'Offline'}
          </span>
        </div>

        {/* Settings button */}
        <button
          onClick={() => setShowConfig(true)}
          className="p-1.5 rounded-md hover:bg-ocean-800 text-slate-400 hover:text-cyan-300 transition"
          title="Configure API Endpoint"
        >
          <Settings className="w-4 h-4" />
        </button>

        <div className="h-4 w-[1px] bg-ocean-700 mx-1" />

        {/* Operator Profile */}
        {user ? (
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-cyan-900 border border-cyan-500 flex items-center justify-center font-bold text-cyan-300 text-[11px]">
              {user.full_name
                .split(' ')
                .map((n) => n[0])
                .join('')
                .slice(0, 2)
                .toUpperCase() || 'OP'}
            </div>
            <div className="text-left hidden sm:block">
              <div className="font-semibold text-slate-200 text-xs">{user.full_name}</div>
              <div className="text-[10px] text-cyan-400 uppercase tracking-wider">{user.role.replace('_', ' ')}</div>
            </div>
            <button
              onClick={onLogout}
              className="ml-2 text-slate-400 hover:text-rose-400 p-1 rounded hover:bg-ocean-800 transition"
              title="Logout"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        ) : null}
      </div>

      {/* Backend URL Config Modal */}
      {showConfig && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-ocean-900 border border-ocean-700 rounded-xl p-5 max-w-md w-full shadow-2xl">
            <h3 className="text-sm font-bold text-white mb-2 flex items-center gap-2">
              <Settings className="w-4 h-4 text-cyan-400" /> Backend API Endpoint Configuration
            </h3>
            <p className="text-xs text-slate-300 mb-4">
              If your FastAPI server runs on a specific host or port, configure the base URL below.
            </p>
            <div className="mb-4">
              <label className="block text-[11px] font-medium text-slate-400 mb-1">Backend Base URL</label>
              <input
                type="text"
                value={customApiUrl}
                onChange={(e) => setCustomApiUrl(e.target.value)}
                placeholder="http://127.0.0.1:8080"
                className="w-full bg-ocean-800 border border-ocean-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500"
              />
            </div>
            <div className="flex justify-end gap-2 text-xs">
              <button
                onClick={handleResetApiUrl}
                className="px-3 py-1.5 rounded-lg border border-ocean-700 text-slate-300 hover:bg-ocean-800"
              >
                Reset Default
              </button>
              <button
                onClick={() => setShowConfig(false)}
                className="px-3 py-1.5 rounded-lg border border-ocean-700 text-slate-300 hover:bg-ocean-800"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveApiUrl}
                className="px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-medium"
              >
                Save & Reconnect
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
};

