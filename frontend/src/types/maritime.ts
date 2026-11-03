export type TrustTier = 'T1' | 'T2' | 'T3' | 'T4';

export interface MessageCitation {
  citation_id: string;
  filename: string;
  message_type: string;
  trust_tier: TrustTier;
  sender: string;
  sent_at_utc?: string;
  raw_message: string;
}

export interface EntityDataCitation {
  citation_id: string;
  label: string;
  primary_id: string;
  attributes: Record<string, any>;
  backing_messages: MessageCitation[];
}

export type Citation = MessageCitation | EntityDataCitation;

export interface ConfirmedFact {
  statement: string;
  citations: string[];
}

export interface UnverifiedReport {
  statement: string;
  source: string;
  citations: string[];
}

export interface SystemInference {
  deduction: string;
  rationale: string;
  confidence: 'HIGH' | 'MEDIUM' | 'LOW';
  supporting_citations: string[];
}

export interface PremiseCorrection {
  user_assumption: string;
  grounded_reality: string;
  citations: string[];
}

export interface ClarificationOption {
  option_id: string;
  label: string;
  description: string;
}

export interface ClarificationPrompt {
  question: string;
  reason: string;
  options: ClarificationOption[];
}

export interface MaritimeAgentResponse {
  status: 'SUCCESS' | 'DATA_UNAVAILABLE' | 'FALSE_PREMISE' | 'CLARIFICATION_NEEDED' | 'BLOCKED_GUARDRAIL';
  executive_summary: string;
  confirmed_facts: ConfirmedFact[];
  unverified_reports: UnverifiedReport[];
  system_inferences: SystemInference[];
  false_premises_detected: PremiseCorrection[];
  clarification?: ClarificationPrompt | null;
  citations: Citation[];
  cypher_queries_executed: string[];
}

export interface Thread {
  thread_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  structured_payload?: MaritimeAgentResponse | null;
  timestamp?: string;
}

export interface UserProfile {
  user_id: string;
  username: string;
  full_name: string;
  email: string;
  role: string;
}

