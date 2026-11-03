import React, { useState } from 'react';
import { Ship, Lock, User, AlertCircle, ArrowRight } from 'lucide-react';
import { api } from '../services/api';

interface AuthModalProps {
  isOpen: boolean;
  onSuccess: () => void;
}

export const AuthModal: React.FC<AuthModalProps> = ({ isOpen, onSuccess }) => {
  const [username, setUsername] = useState('maritime_lead');
  const [password, setPassword] = useState('MaritimeOps2026!');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await api.login(username.trim(), password);
      onSuccess();
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please check credentials.');
    } finally {
      setLoading(false);
    }
  };

  const handleUseDemo = () => {
    setUsername('maritime_lead');
    setPassword('MaritimeOps2026!');
  };

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-4">
      <div className="bg-ocean-900 border border-ocean-700/80 rounded-2xl max-w-md w-full p-6 shadow-2xl relative">
        <div className="text-center mb-6">
          <div className="inline-flex p-3 rounded-2xl bg-cyan-950 border border-cyan-800 text-cyan-400 mb-3 shadow-lg shadow-cyan-900/30">
            <Ship className="w-8 h-8" />
          </div>
          <h2 className="text-lg font-bold text-white tracking-wide">Maritime Operations Portal</h2>
          <p className="text-xs text-slate-400 mt-1">Authenticate to access the Maritime Knowledge Graph & Agent</p>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-rose-950/60 border border-rose-800/80 rounded-lg text-rose-300 text-xs flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
            <span className="leading-relaxed">{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          <div>
            <label className="block text-slate-300 font-medium mb-1 flex items-center gap-1.5">
              <User className="w-3.5 h-3.5 text-cyan-400" /> Username / Email
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-ocean-800 border border-ocean-700 rounded-lg px-3 py-2 text-slate-100 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500"
              required
            />
          </div>

          <div>
            <label className="block text-slate-300 font-medium mb-1 flex items-center gap-1.5">
              <Lock className="w-3.5 h-3.5 text-cyan-400" /> Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-ocean-800 border border-ocean-700 rounded-lg px-3 py-2 text-slate-100 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500"
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white font-medium py-2.5 rounded-lg transition shadow-lg shadow-cyan-900/40 text-xs flex items-center justify-center gap-2"
          >
            {loading ? (
              <span>Authenticating...</span>
            ) : (
              <>
                <span>Sign In to Maritime Portal</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>

        <div className="mt-5 pt-4 border-t border-ocean-800 flex items-center justify-between text-[11px] text-slate-400">
          <span>Demo Account: <strong className="text-cyan-300">maritime_lead</strong></span>
          <button
            onClick={handleUseDemo}
            className="text-cyan-400 hover:text-cyan-300 underline underline-offset-2"
          >
            Auto-fill
          </button>
        </div>
      </div>
    </div>
  );
};

