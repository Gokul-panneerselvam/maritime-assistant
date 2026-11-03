import React, { useState, useEffect, useCallback } from 'react';
import { Navbar } from './components/Navbar';
import { Sidebar } from './components/Sidebar';
import { ChatCanvas } from './components/ChatCanvas';
import { EvidenceDrawer } from './components/EvidenceDrawer';
import { AuthModal } from './components/AuthModal';
import { api } from './services/api';
import { Thread, ChatMessage, Citation, UserProfile, MaritimeAgentResponse } from './types/maritime';

export const App: React.FC = () => {
  // Authentication & User State
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isAuthOpen, setIsAuthOpen] = useState(false);

  // Connectivity State
  const [neo4jStatus, setNeo4jStatus] = useState<'connected' | 'disconnected' | 'checking'>('checking');
  const [backendConnected, setBackendConnected] = useState(true);

  // Chat & Threads State
  const [threads, setThreads] = useState<Thread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);

  // Citation Evidence State
  const [citationsMap, setCitationsMap] = useState<Record<string, Citation>>({});
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null);

  // Check Health
  const checkHealth = useCallback(async () => {
    try {
      const data = await api.checkHealth();
      setBackendConnected(true);
      setNeo4jStatus(data.neo4j === 'connected' ? 'connected' : 'disconnected');
    } catch (err) {
      setBackendConnected(false);
      setNeo4jStatus('disconnected');
    }
  }, []);

  // Verify Session
  const verifySession = useCallback(async () => {
    const token = localStorage.getItem('maritime_token');
    if (!token) {
      setIsAuthOpen(true);
      return;
    }
    try {
      const res = await api.getMe();
      setUser(res.user);
      setIsAuthOpen(false);
      await loadThreads();
    } catch {
      localStorage.removeItem('maritime_token');
      setUser(null);
      setIsAuthOpen(true);
    }
  }, []);

  // Load Threads
  const loadThreads = useCallback(async () => {
    try {
      const threadList = await api.listThreads();
      setThreads(threadList);
    } catch (e) {
      console.warn('Failed to load threads:', e);
    }
  }, []);

  // Initial Load & Polling
  useEffect(() => {
    verifySession();
    checkHealth();

    const healthInterval = setInterval(checkHealth, 15000);
    const handleUnauthorized = () => {
      setUser(null);
      setIsAuthOpen(true);
    };

    window.addEventListener('maritime:unauthorized', handleUnauthorized);
    return () => {
      clearInterval(healthInterval);
      window.removeEventListener('maritime:unauthorized', handleUnauthorized);
    };
  }, [verifySession, checkHealth]);

  // Load Thread History
  const selectThread = async (threadId: string) => {
    setActiveThreadId(threadId);
    setLoading(true);
    try {
      const history = await api.getThreadHistory(threadId);
      setMessages(history);

      // Index citations in history
      const newMap: Record<string, Citation> = {};
      history.forEach((m) => {
        if (m.structured_payload?.citations) {
          m.structured_payload.citations.forEach((c) => {
            newMap[c.citation_id] = c;
            if ('filename' in c && c.filename) newMap[c.filename] = c;
            if ('primary_id' in c && c.primary_id) newMap[c.primary_id] = c;
          });
        }
      });
      setCitationsMap((prev) => ({ ...prev, ...newMap }));
    } catch (err: any) {
      alert(`Error loading thread: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Start New Inquiry
  const handleNewThread = () => {
    setActiveThreadId(null);
    setMessages([]);
    loadThreads();
  };

  // Delete Thread
  const handleDeleteThread = async (threadId: string) => {
    if (!confirm('Archive this operational thread?')) return;
    try {
      await api.deleteThread(threadId);
      if (activeThreadId === threadId) {
        handleNewThread();
      } else {
        loadThreads();
      }
    } catch (err: any) {
      alert(`Error deleting thread: ${err.message}`);
    }
  };

  // Send Message
  const handleSendMessage = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const prompt = inputText.trim();
    if (!prompt || loading) return;

    setInputText('');
    const userMsg: ChatMessage = { role: 'user', content: prompt };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const res = await api.sendMessage(prompt, activeThreadId);
      setActiveThreadId(res.thread_id);

      // Index returned citations
      if (res.response.citations) {
        const newMap: Record<string, Citation> = {};
        res.response.citations.forEach((c) => {
          newMap[c.citation_id] = c;
          if ('filename' in c && c.filename) newMap[c.filename] = c;
          if ('primary_id' in c && c.primary_id) newMap[c.primary_id] = c;
        });
        setCitationsMap((prev) => ({ ...prev, ...newMap }));
      }

      const assistantMsg: ChatMessage = {
        role: 'assistant',
        content: res.response.executive_summary,
        structured_payload: res.response,
      };

      setMessages((prev) => [...prev, assistantMsg]);
      await loadThreads();
    } catch (err: any) {
      const errMsg: ChatMessage = {
        role: 'assistant',
        content: `**Operational Error:** ${err.message}`,
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  };

  // Submit Clarification Choice
  const handleClarificationChoice = async (choice: string) => {
    if (!activeThreadId || loading) return;

    const userMsg: ChatMessage = { role: 'user', content: `Clarification: ${choice}` };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const res = await api.submitClarification(activeThreadId, choice);

      if (res.response.citations) {
        const newMap: Record<string, Citation> = {};
        res.response.citations.forEach((c) => {
          newMap[c.citation_id] = c;
          if ('filename' in c && c.filename) newMap[c.filename] = c;
          if ('primary_id' in c && c.primary_id) newMap[c.primary_id] = c;
        });
        setCitationsMap((prev) => ({ ...prev, ...newMap }));
      }

      const assistantMsg: ChatMessage = {
        role: 'assistant',
        content: res.response.executive_summary,
        structured_payload: res.response,
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      const errMsg: ChatMessage = {
        role: 'assistant',
        content: `**Clarification Error:** ${err.message}`,
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  };

  // Open Citation in Evidence Drawer
  const handleSelectCitation = (citationId: string) => {
    const cleanId = citationId.trim();
    const citation = citationsMap[cleanId];
    if (citation) {
      setActiveCitation(citation);
    } else {
      // Fallback synthetic citation if not directly indexed
      setActiveCitation({
        citation_id: cleanId,
        label: cleanId.includes('.') ? 'Message' : 'GraphNode',
        primary_id: cleanId,
        attributes: { reference: cleanId, note: 'Traversed via Knowledge Graph' },
        backing_messages: [],
      });
    }
  };

  const handleSamplePromptClick = (prompt: string) => {
    setInputText(prompt);
  };

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-ocean-950 text-slate-100 font-sans">
      {/* Top Navbar */}
      <Navbar
        user={user}
        neo4jStatus={neo4jStatus}
        backendConnected={backendConnected}
        onLogout={() => {
          localStorage.removeItem('maritime_token');
          setUser(null);
          setIsAuthOpen(true);
        }}
        onRefreshHealth={checkHealth}
      />

      {/* Main Body */}
      <div className="flex-1 flex overflow-hidden relative">
        <Sidebar
          threads={threads}
          activeThreadId={activeThreadId}
          onSelectThread={selectThread}
          onNewThread={handleNewThread}
          onDeleteThread={handleDeleteThread}
          onRunSamplePrompt={handleSamplePromptClick}
        />

        <ChatCanvas
          messages={messages}
          loading={loading}
          inputText={inputText}
          onInputChange={setInputText}
          onSendMessage={handleSendMessage}
          onSelectCitation={handleSelectCitation}
          onClarificationChoice={handleClarificationChoice}
          onSamplePromptClick={handleSamplePromptClick}
        />

        {/* Slide-out Evidence Drawer */}
        <EvidenceDrawer
          citation={activeCitation}
          onClose={() => setActiveCitation(null)}
        />
      </div>

      {/* Auth Modal */}
      <AuthModal
        isOpen={isAuthOpen}
        onSuccess={() => verifySession()}
      />
    </div>
  );
};

export default App;

