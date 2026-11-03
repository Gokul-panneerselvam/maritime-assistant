import React, { useState } from 'react';
import { Ship, Lock, User, AlertCircle, ArrowRight } from 'lucide-react';
import { api } from '../services/api';

interface AuthModalProps {
  isOpen: boolean;
  onSuccess: () => void;
}

export const AuthModal: React.FC<AuthModalProps> = ({ isOpen, onSuccess }) => {
  const [username, setUsername] = useState('gokul');
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
    setUsername('gokul');
    setPassword('MaritimeOps2026!');
  };

  return (
    <div className="fixed inset-0 bg-sky-950/40 backdrop-blur-xs z-50 flex items-center justify-center p-4">
      <div className="bg-white border border-sky-200 rounded-3xl max-w-md w-full p-6 shadow-2xl relative">
        <div className="text-center mb-6">
          <div className="inline-flex p-3.5 rounded-2xl bg-gradient-to-tr from-sky-50 to-teal-50 border border-sky-200 text-teal-600 mb-3 shadow-xs">
            <Ship className="w-8 h-8" />
          </div>
          <h2 className="text-lg font-bold text-sky-950 tracking-wide">Maritime Operations Portal</h2>
          <p className="text-xs text-slate-500 mt-1">Authenticate to access Fleet Operations Control & Intelligence</p>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
            <span className="leading-relaxed">{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          <div>
            <label className="block text-slate-700 font-medium mb-1 flex items-center gap-1.5">
              <User className="w-3.5 h-3.5 text-teal-600" /> Username / Email
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-[#f4f9fd] border border-sky-200 rounded-xl px-3 py-2 text-slate-900 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500 focus:bg-white"
              required
            />
          </div>

          <div>
            <label className="block text-slate-700 font-medium mb-1 flex items-center gap-1.5">
              <Lock className="w-3.5 h-3.5 text-teal-600" /> Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-[#f4f9fd] border border-sky-200 rounded-xl px-3 py-2 text-slate-900 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500 focus:bg-white"
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-gradient-to-r from-sky-600 to-teal-600 hover:from-sky-700 hover:to-teal-700 disabled:opacity-50 text-white font-medium py-2.5 rounded-xl transition shadow-xs text-xs flex items-center justify-center gap-2"
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

        <div className="mt-5 pt-4 border-t border-sky-100 flex items-center justify-between text-[11px] text-slate-500">
          <span>Demo Operator: <strong className="text-teal-800 font-semibold">Gokul Panneer Selvam (gokul)</strong></span>
          <button
            onClick={handleUseDemo}
            className="text-teal-700 hover:text-teal-800 underline underline-offset-2 font-semibold"
          >
            Auto-fill
          </button>
        </div>
      </div>
    </div>
  );
};
