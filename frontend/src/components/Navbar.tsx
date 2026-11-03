import React, { useState } from 'react';
import { Ship, LogOut, Settings, RefreshCw } from 'lucide-react';
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
    <header className="bg-white/95 backdrop-blur-md border-b border-sky-200/90 px-5 py-3 flex items-center justify-between shrink-0 z-20 shadow-xs">
      {/* Brand & Subtitle */}
      <div className="flex items-center gap-3">
        <div className="bg-gradient-to-tr from-teal-600 via-sky-600 to-sky-500 p-2 rounded-xl shadow-md shadow-sky-500/20 text-white">
          <Ship className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-sm font-bold tracking-wide text-sky-950 flex items-center gap-2 font-sans">
            MARITIME OPS INTELLIGENCE
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-teal-50 text-teal-700 border border-teal-200 font-mono font-medium">
              v2.0 • Fleet Operations Control
            </span>
          </h1>
          <p className="text-[11px] text-sky-800/80 font-medium">Strict 3-Way Epistemic Separation & Grounded Knowledge Graph</p>
        </div>
      </div>

      {/* Status Indicators & Profile */}
      <div className="flex items-center gap-3 text-xs">
        {/* Backend Connectivity Status */}
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-[11px] transition ${
            backendConnected
              ? 'bg-teal-50 border-teal-200 text-teal-800 font-medium'
              : 'bg-rose-50 border-rose-200 text-rose-700 animate-pulse'
          }`}
          title={backendConnected ? `Connected to ${getApiBaseUrl() || 'Backend Operations'}` : 'Backend connection lost'}
        >
          <span
            className={`w-2 h-2 rounded-full ${
              backendConnected ? 'bg-teal-500 shadow-xs shadow-teal-400/50' : 'bg-rose-500'
            }`}
          />
          <span>{backendConnected ? 'API Online' : 'API Offline'}</span>
          <button
            onClick={onRefreshHealth}
            className="hover:text-teal-950 ml-1 p-0.5"
            title="Refresh connection status"
          >
            <RefreshCw className="w-3 h-3" />
          </button>
        </div>

        {/* Neo4j Status */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-sky-50 border border-sky-200 text-sky-800 text-[11px] font-medium">
          <span
            className={`w-2 h-2 rounded-full ${
              neo4jStatus === 'connected'
                ? 'bg-sky-500 animate-pulse'
                : neo4jStatus === 'checking'
                ? 'bg-amber-500'
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
          className="p-1.5 rounded-lg hover:bg-sky-50 text-slate-500 hover:text-sky-700 transition border border-transparent hover:border-sky-200"
          title="Configure API Endpoint"
        >
          <Settings className="w-4 h-4" />
        </button>

        <div className="h-4 w-[1px] bg-sky-200 mx-1" />

        {/* Operator Profile */}
        {user ? (
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-gradient-to-tr from-sky-100 to-teal-100 border border-sky-300 flex items-center justify-center font-bold text-sky-900 text-[11px] shadow-2xs">
              {user.full_name
                .split(' ')
                .map((n) => n[0])
                .join('')
                .slice(0, 2)
                .toUpperCase() || 'GP'}
            </div>
            <div className="text-left hidden sm:block">
              <div className="font-semibold text-slate-900 text-xs">{user.full_name}</div>
              <div className="text-[10px] text-teal-700 font-semibold uppercase tracking-wider">{user.role.replace(/_/g, ' ')}</div>
            </div>
            <button
              onClick={onLogout}
              className="ml-2 text-slate-400 hover:text-rose-600 p-1 rounded-lg hover:bg-rose-50 transition"
              title="Logout"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        ) : null}
      </div>

      {/* Backend URL Config Modal */}
      {showConfig && (
        <div className="fixed inset-0 bg-sky-950/40 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-sky-200 rounded-2xl p-5 max-w-md w-full shadow-2xl">
            <h3 className="text-sm font-bold text-sky-950 mb-2 flex items-center gap-2">
              <Settings className="w-4 h-4 text-teal-600" /> Backend API Endpoint Configuration
            </h3>
            <p className="text-xs text-slate-600 mb-4">
              If your operations backend server runs on a specific host or port, configure the base URL below.
            </p>
            <div className="mb-4">
              <label className="block text-[11px] font-medium text-slate-600 mb-1">Backend Base URL</label>
              <input
                type="text"
                value={customApiUrl}
                onChange={(e) => setCustomApiUrl(e.target.value)}
                placeholder="http://127.0.0.1:8080"
                className="w-full bg-[#f4f9fd] border border-sky-200 rounded-lg px-3 py-2 text-xs text-slate-900 focus:outline-none focus:border-teal-500 focus:bg-white"
              />
            </div>
            <div className="flex justify-end gap-2 text-xs">
              <button
                onClick={handleResetApiUrl}
                className="px-3 py-1.5 rounded-lg border border-sky-200 text-slate-700 hover:bg-sky-50"
              >
                Reset Default
              </button>
              <button
                onClick={() => setShowConfig(false)}
                className="px-3 py-1.5 rounded-lg border border-sky-200 text-slate-700 hover:bg-sky-50"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveApiUrl}
                className="px-3 py-1.5 rounded-lg bg-gradient-to-r from-sky-600 to-teal-600 hover:from-sky-700 hover:to-teal-700 text-white font-medium shadow-xs"
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
