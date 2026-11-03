import { MaritimeAgentResponse, Thread, ChatMessage, UserProfile } from '../types/maritime';

export function getApiBaseUrl(): string {
  const custom = localStorage.getItem('maritime_api_url');
  if (custom) return custom.replace(/\/$/, '');

  const envUrl = import.meta.env.VITE_API_URL;
  if (envUrl) return envUrl.replace(/\/$/, '');

  if (typeof window !== 'undefined') {
    // If opened directly from file system
    if (window.location.protocol === 'file:' || !window.location.origin || window.location.origin === 'null') {
      return 'http://127.0.0.1:8080';
    }
    // If running on Vite dev server (port 5173), proxy works with relative path or fallback to 8080
    if (window.location.port === '5173') {
      return '';
    }
    // Otherwise use current host
    return window.location.origin;
  }
  return 'http://127.0.0.1:8080';
}

function getAuthHeader(): Record<string, string> {
  const token = localStorage.getItem('maritime_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(endpoint: string, options: RequestInit = {}, timeoutMs = 1800000): Promise<T> {
  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...getAuthHeader(),
    ...(options.headers as Record<string, string> || {}),
  };

  try {
    const res = await fetch(url, {
      ...options,
      headers,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (res.status === 401) {
      localStorage.removeItem('maritime_token');
      window.dispatchEvent(new CustomEvent('maritime:unauthorized'));
      throw new Error('Session expired. Please log in again.');
    }

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      const errorMsg = data.detail || data.message || `Request failed with status ${res.status}`;
      throw new Error(errorMsg);
    }

    return data as T;
  } catch (err: any) {
    clearTimeout(timeoutId);
    if (err.name === 'AbortError') {
      throw new Error('Request timed out. The operational query took longer than 30 minutes to complete.');
    }
    if (err.message && (err.message.includes('Failed to fetch') || err.message.includes('NetworkError'))) {
      throw new Error(
        `Cannot connect to backend operations server at ${baseUrl || 'current host'}. Make sure the backend server is running.`
      );
    }
    throw err;
  }
}

export const api = {
  async checkHealth(): Promise<{ status: string; neo4j: string; database: string }> {
    return request<{ status: string; neo4j: string; database: string }>('/api/system/health', {}, 10000);
  },

  async login(username_or_email: string, password: string): Promise<{ access_token: string; token_type: string }> {
    const data = await request<{ access_token: string; token_type: string }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username_or_email, password }),
    });
    if (data.access_token) {
      localStorage.setItem('maritime_token', data.access_token);
    }
    return data;
  },

  async getMe(): Promise<{ user: UserProfile }> {
    return request<{ user: UserProfile }>('/api/auth/me');
  },

  async listThreads(): Promise<Thread[]> {
    const res = await request<{ threads: Thread[] }>('/api/chat/threads');
    return res.threads || [];
  },

  async getThreadHistory(threadId: string): Promise<ChatMessage[]> {
    const res = await request<{ messages: any[] }>(`/api/chat/threads/${threadId}/history`);
    return (res.messages || []).map((m: any) => ({
      id: m.message_id,
      role: m.role,
      content: m.content,
      structured_payload: m.structured_payload,
      timestamp: m.created_at,
    }));
  },

  async deleteThread(threadId: string): Promise<void> {
    await request(`/api/chat/threads/${threadId}`, { method: 'DELETE' });
  },

  async sendMessage(
    message: string,
    threadId: string | null = null
  ): Promise<{ thread_id: string; response: MaritimeAgentResponse; is_interrupted: boolean }> {
    return request<{ thread_id: string; response: MaritimeAgentResponse; is_interrupted: boolean }>(
      '/api/chat',
      {
        method: 'POST',
        body: JSON.stringify({ thread_id: threadId, message }),
      },
      1800000
    );
  },

  async submitClarification(
    threadId: string,
    choice: string
  ): Promise<{ thread_id: string; response: MaritimeAgentResponse; is_interrupted: boolean }> {
    return api.sendMessage(choice, threadId);
  },
};

