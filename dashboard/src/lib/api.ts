const API_BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '');

// --- Apollo-parity types -----------------------------------------------------

export interface SetupCheck {
  key: string;
  label: string;
  required: boolean;
  ok: boolean;
  detail: string;
  href: string | null;
}

export interface SetupMailbox {
  id: number;
  email: string;
  smtp_host: string;
  smtp_port: number;
  daily_limit: number;
  is_active: boolean;
  imap_host: string | null;
  imap_port: number;
  health_paused: boolean;
}

export interface SetupEnvKey {
  key: string;
  required: boolean;
  note: string;
}

export interface SetupRuntimeSetting {
  value: string;
  label: string;
  placeholder: string;
  restart_required: boolean;
}

export interface SetupStatus {
  ready: boolean;
  db_type: string;
  api_url: string;
  checks: SetupCheck[];
  mailboxes: SetupMailbox[];
  env_keys: SetupEnvKey[];
  ai_note: string;
  runtime_settings: Record<string, SetupRuntimeSetting>;
}

export interface ProviderPreset {
  id: string;
  label: string;
  smtp_host: string;
  smtp_port: number;
  imap_host: string;
  imap_port: number;
  howto: string;
}

// --- Apollo-parity types -----------------------------------------------------

export interface TimeSeriesPoint {
  date: string;
  sent: number;
  opened: number;
  replied: number;
  bounced: number;
}

export interface TimeSeriesResponse {
  days: TimeSeriesPoint[];
  totals: { sent: number; opened: number; replied: number; bounced: number; reply_rate: number; open_rate: number };
  period_days: number;
}

export interface TaskItem {
  key: string;
  label: string;
  count: number;
  severity: "high" | "medium" | "info";
  href: string;
}

export interface InboxItem {
  send_id: number;
  category: "interested" | "not_interested" | "opt_out" | "out_of_office" | "other";
  replied_at: string | null;
  reply_body: string | null;
  contact_name: string | null;
  contact_email: string | null;
  business_name: string | null;
  campaign_id: number;
  campaign_name: string | null;
  step_subject: string | null;
  mailbox_id: number | null;
}

export interface InboxResponse {
  items: InboxItem[];
  counts: Record<string, number>;
}

export interface StepStat {
  step_id: number;
  step_number: number;
  subject: string;
  subject_b: string | null;
  sent: number;
  replied: number;
  bounced: number;
  failed: number;
  reply_rate: number;
  variants: null | {
    a: { sent: number; replied: number; reply_rate: number };
    b: { sent: number; replied: number; reply_rate: number };
    winner: "a" | "b" | null;
  };
}

export interface LeadContactDetail {
  id: number;
  first_name: string | null;
  last_name: string | null;
  title: string | null;
  email: string | null;
  phone: string | null;
  whatsapp_link: string | null;
  social_links: Record<string, string> | null;
  is_verified: boolean;
  verification_status: string | null;
  verification_sub_status: string | null;
  verification_confidence: number | null;
  verification_detail: string | null;
  is_role_account: boolean;
  is_free_email: boolean;
  unsubscribed: boolean;
  suppressed: string | null;
  source: string | null;
}

export interface LeadTimelineEntry {
  send_id: number;
  campaign_id: number;
  campaign_name: string | null;
  step_subject: string | null;
  status: string;
  opened: boolean;
  replied: boolean;
  reply_category: string | null;
  variant_used: string | null;
  error_message: string | null;
  sent_at: string | null;
  contact_email: string | null;
}

export interface LeadDetailResponse {
  business: {
    id: number;
    name: string;
    industry: string | null;
    phone: string | null;
    website: string | null;
    address: string | null;
    rating: number | null;
    reviews_count: number | null;
    maps_url: string;
  };
  contacts: LeadContactDetail[];
  timeline: LeadTimelineEntry[];
}

export interface SavedView {
  id: number;
  name: string;
  filters: Record<string, unknown>;
  created_at: string | null;
}

export interface SuppressionEntry {
  id: number;
  identifier: string;
  reason: string;
  detail: string | null;
  is_domain: boolean;
  active: boolean;
  expires_at: string | null;
  created_at: string | null;
}

export interface DashboardStats {
  total_leads: number;
  total_contacts: number;
  verified_contacts: number;
  emails_sent: number;
  emails_opened: number;
  open_rate: number;
  active_campaigns: number;
  recent_leads: Array<{
    id: number;
    name: string;
    industry: string;
    phone: string | null;
    email: string | null;
    is_verified: boolean;
    rating: number | null;
    maps_url?: string;
    created_at: string | null;
  }>;
  recent_jobs: Array<{
    id: number;
    query: string;
    status: string;
    total_found: number;
    leads_saved: number;
    created_at: string | null;
  }>;
}

export interface LeadItem {
  id: number;
  name: string;
  website: string | null;
  phone: string | null;
  address: string | null;
  maps_url?: string;
  rating: number | null;
  reviews_count: number | null;
  industry: string | null;
  latitude?: number | null;
  longitude?: number | null;
  is_claimed?: boolean;
  operational_status?: string;
  price_tier?: string | null;
  lead_score?: number;
  lead_tier?: "HOT" | "WARM" | "COLD";
  lead_badges?: string[];
  source?: string | null;
  source_trust?: number | null;
  trust_note?: string | null;
  trust_modifier?: number;
  primary_contact?: {
    id: number;
    first_name: string | null;
    last_name: string | null;
    email: string | null;
    phone: string | null;
    whatsapp_link: string | null;
    is_verified: boolean;
    verification_status: string;
  };
  contacts: Array<{
    id: number;
    first_name: string | null;
    last_name: string | null;
    email: string | null;
    phone: string | null;
    whatsapp_link: string | null;
    is_verified: boolean;
    verification_status: string;
  }>;
  created_at: string | null;
}

export interface ScrapeJob {
  id: number;
  query: string;
  status: string;
  total_found: number;
  leads_saved: number;
  error: string | null;
  created_at: string | null;
  finished_at: string | null;
}

export interface CampaignItem {
  id: number;
  name: string;
  status: string;
  total_targets: number;
  contacts_selected?: number;
  step_count?: number;
  sent_count: number;
  opened_count: number;
  open_rate: number;
  replied_count: number;
  reply_rate: number;
  created_at: string | null;
}

export interface CampaignTargetItem {
  contact_id: number;
  name: string | null;
  email: string | null;
  business_name: string | null;
  is_verified: boolean;
}

export interface MailboxItem {
  id: number;
  email: string;
  smtp_host: string;
  smtp_port: number;
  first_name: string | null;
  last_name: string | null;
  daily_limit: number;
  sent_today: number;
  is_active: boolean;
  imap_host?: string | null;
  imap_port?: number;
  health_score?: number | null;
  health_paused?: boolean | null;
  created_at?: string | null;
}

// --- India readiness (advisory: operator decides, nothing gates a send) ---

export interface IndiaAdvisorReport {
  quiet_hours_now: boolean;
  festival: {
    festival: string | null;
    key: string | null;
    emoji: string;
    subject_hook: string | null;
    hinglish_line: string | null;
  };
  auth: {
    domain: string;
    spf_ok: boolean;
    dkim_ok: boolean;
    dmarc_ok: boolean;
    ok: boolean;
    warnings: string[];
  } | null;
}

export interface IndiaCopyKit {
  festival: IndiaAdvisorReport["festival"];
  hinglish_closers: Array<{ english: string; hinglish: string }>;
  culture_checklist: { do: string[]; dont: string[] };
}

export interface WarmHandoffCandidate {
  contact_id: number;
  name: string | null;
  whatsapp_link: string | null;
  engagement: { sent: number; opened: number; clicked: number; replied: number; bounced: number };
  reason: string;
}

export interface WarmHandoffResponse {
  campaign_id: number;
  candidates: WarmHandoffCandidate[];
  note: string;
}

export interface ICPDraft {
  name: string;
  niche: string;
  area: string | null;
  keywords: string[];
  exclude_keywords: string[];
  min_score: number;
  preset: "outreach_quality" | "agency_opportunity";
  signal_weights: Record<string, number> | null;
  preferred_sources: string[] | null;
}

export interface ICPProfile extends ICPDraft {
  id: number;
  source_stats: Record<string, { leads: number; avg_score: number }>;
  created_at: string | null;
  updated_at: string | null;
}

export interface RankedContact {
  id: number;
  first_name: string | null;
  last_name: string | null;
  title: string | null;
  email: string | null;
  phone: string | null;
  whatsapp_link: string | null;
  social_links: Record<string, string> | null;
  is_verified: boolean;
  verification_status: string;
}

export interface RankedLead {
  business_id: number;
  name: string;
  industry: string | null;
  address: string | null;
  phone: string | null;
  website: string | null;
  rating: number | null;
  reviews_count: number | null;
  latitude: number | null;
  longitude: number | null;
  source: string | null;
  source_trust?: number | null;
  trust_modifier?: number;
  contacts: RankedContact[];
  score: number;
  tier: "HOT" | "WARM" | "COLD";
  badges: string[];
  signal_breakdown: Record<string, number>;
  signals: Record<string, unknown>;
}

export interface DiscoveryResult {
  niche: string;
  area: string | null;
  query: string;
  icp_profile_id: number;
  min_score: number;
  preset: string;
  ranked_leads: RankedLead[];
}

export interface DiscoveryJob {
  id: number;
  query: string;
  status: string;
  total_found: number;
  leads_saved: number;
  error: string | null;
  icp_profile_id: number | null;
  result: DiscoveryResult | null;
  created_at: string | null;
  finished_at: string | null;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
    });
    if (!res.ok) {
      const errText = await res.text();
      let msg = `HTTP error ${res.status}`;
      try {
        const parsed = JSON.parse(errText);
        msg = parsed.detail || parsed.message || msg;
      } catch {}
      throw new Error(msg);
    }
    return res.json();
  } catch (err: any) {
    console.error(`API Error on ${path}:`, err);
    throw err;
  }
}

export const api = {
  // Stats
  getStats: () => request<DashboardStats>('/analytics/stats'),

  // Leads
  getLeads: (params: { page?: number; limit?: number; search?: string; industry?: string; has_email?: boolean } = {}) => {
    const q = new URLSearchParams();
    if (params.page) q.set('page', String(params.page));
    if (params.limit) q.set('limit', String(params.limit));
    if (params.search) q.set('search', params.search);
    if (params.industry) q.set('industry', params.industry);
    if (params.has_email !== undefined) q.set('has_email', String(params.has_email));
    return request<{ total: number; page: number; limit: number; leads: LeadItem[] }>(`/leads?${q.toString()}`);
  },
  createLead: (data: { name: string; phone?: string; email?: string; website?: string; address?: string; industry?: string }) =>
    request('/leads', { method: 'POST', body: JSON.stringify(data) }),
  deleteLead: (id: number) => request(`/leads/${id}`, { method: 'DELETE' }),
  exportCsvUrl: `${API_BASE}/leads/export/csv`,
  exportTwentyCrmUrl: `${API_BASE}/leads/export/twenty-crm`,
  exportTwentyCrm: (webhook_url?: string) =>
    request<any>('/leads/export/twenty-crm', {
      method: 'POST',
      body: JSON.stringify({ webhook_url }),
    }),
  importCsv: (csv_content: string) =>
    request<{ status: string; imported: number; skipped: number; total_rows_processed: number }>('/leads/import/csv', {
      method: 'POST',
      body: JSON.stringify({ csv_content }),
    }),
  getIcebreaker: (business_id: number) =>
    request<any>(`/leads/${business_id}/icebreaker`),
  checkSpam: (subject: string, body: string) =>
    request<{
      score: number;
      tier: string;
      is_safe: boolean;
      high_risk_words: string[];
      moderate_risk_words: string[];
      warnings: string[];
      recommendations: string[];
    }>('/campaigns/check-spam', {
      method: 'POST',
      body: JSON.stringify({ subject, body }),
    }),

  // Scraper
  startScrape: (query: string, max_results: number = 20) =>
    request<{ job_id: number; status: string; message: string }>('/scraper/start', {
      method: 'POST',
      body: JSON.stringify({ query, max_results }),
    }),
  getJobs: () => request<ScrapeJob[]>('/scraper/jobs'),
  getJob: (id: number) => request<ScrapeJob>(`/scraper/jobs/${id}`),

  // Enricher
  enrichLead: (business_id: number) =>
    request(`/enricher/enrich-lead/${business_id}`, { method: 'POST' }),
  enrichAll: (limit: number = 25) =>
    request<{ status: string; message: string }>('/enricher/enrich-all', {
      method: 'POST',
      body: JSON.stringify({ limit }),
    }),

  // Campaigns
  getCampaigns: () => request<CampaignItem[]>('/campaigns'),
  getCampaign: (id: number) => request<any>(`/campaigns/${id}`),
  createCampaign: (data: { name: string; steps: Array<{ subject: string; body_text: string; body_html?: string; delay_days?: number }>; contact_ids?: number[] }) =>
    request('/campaigns', { method: 'POST', body: JSON.stringify(data) }),
  addCampaignTargets: (campaignId: number, contact_ids: number[]) =>
    request<{ campaign_id: number; added: number; total_targets: number }>(
      `/campaigns/${campaignId}/targets`,
      { method: 'POST', body: JSON.stringify({ contact_ids }) },
    ),
  getCampaignTargets: (campaignId: number) =>
    request<{ campaign_id: number; targets: CampaignTargetItem[] }>(
      `/campaigns/${campaignId}/targets`,
    ),
  removeCampaignTarget: (campaignId: number, contactId: number) =>
    request(`/campaigns/${campaignId}/targets/${contactId}`, { method: 'DELETE' }),
  launchCampaign: (id: number) => request(`/campaigns/${id}/launch`, { method: 'POST' }),
  pauseCampaign: (id: number) => request(`/campaigns/${id}/pause`, { method: 'POST' }),
  previewTemplate: (subject: string, body: string) =>
    request<{ sample_variables_used: any; rendered_subject: string; rendered_body: string }>('/campaigns/preview', {
      method: 'POST',
      body: JSON.stringify({ subject, body }),
    }),

  // Mailboxes
  getMailboxes: () => request<MailboxItem[]>('/mailboxes'),
  createMailbox: (data: { email: string; password: string; smtp_host: string; smtp_port?: number; first_name?: string; last_name?: string; daily_limit?: number }) =>
    request('/mailboxes', { method: 'POST', body: JSON.stringify(data) }),
  testMailbox: (id: number) =>
    request<{ success: boolean; message: string }>(`/mailboxes/${id}/test`, { method: 'POST' }),
  deleteMailbox: (id: number) => request(`/mailboxes/${id}`, { method: 'DELETE' }),

  // ICP & Discovery
  parseIcp: (text: string) =>
    request<ICPDraft>('/icp/parse', { method: 'POST', body: JSON.stringify({ text }) }),
  createIcp: (data: ICPDraft) =>
    request<ICPProfile>('/icp', { method: 'POST', body: JSON.stringify(data) }),
  listIcps: () => request<ICPProfile[]>('/icp'),
  getIcp: (id: number) => request<ICPProfile>(`/icp/${id}`),
  updateIcp: (id: number, data: Partial<ICPDraft>) =>
    request<ICPProfile>(`/icp/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteIcp: (id: number) => request(`/icp/${id}`, { method: 'DELETE' }),
  rankLeads: (id: number, limit = 50) =>
    request<{ icp_profile_id: number; min_score: number; total: number; ranked_leads: RankedLead[] }>(
      `/icp/${id}/rank?limit=${limit}`
    ),
  startDiscovery: (data: { niche: string; area?: string | null; icp_profile_id: number; max_results?: number }) =>
    request<{ job_id: number; status: string; message: string }>('/icp/discover', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getDiscoveryJob: (id: number) => request<DiscoveryJob>(`/icp/discover/${id}`),

  // India readiness (advisory endpoints: operator decides, nothing gates)
  getIndiaAdvisor: (domain?: string) =>
    request<IndiaAdvisorReport>(`/campaigns/india/advisor${domain ? `?domain=${encodeURIComponent(domain)}` : ""}`),
  getIndiaCopy: () => request<IndiaCopyKit>("/campaigns/india/copy"),
  getWarmHandoff: (campaignId: number) =>
    request<WarmHandoffResponse>(`/campaigns/india/handoff/${campaignId}`),
  postDltChecklist: (numbers: string[]) =>
    request<{ numbers: Array<{ number: string | null; is_mobile: boolean; is_landline: boolean; dnd_scrubbed: boolean; sms_allowed: boolean }>; quiet_hours_now: boolean; warnings: string[] }>("/campaigns/india/dlt-checklist", {
      method: "POST",
      body: JSON.stringify({ numbers }),
    }),

  // --- Apollo parity: analytics, tasks, inbox, saved lists, suppression ----
  getTimeseries: (days = 30) =>
    request<TimeSeriesResponse>(`/analytics/timeseries?days=${days}`),
  getTasks: () => request<{ tasks: TaskItem[] }>("/analytics/tasks"),
  listInbox: (category?: string) =>
    request<InboxResponse>(`/inbox${category ? `?category=${encodeURIComponent(category)}` : ""}`),
  setReplyCategory: (sendId: number, category: string) =>
    request<{ send_id: number; category: string }>(`/inbox/${sendId}/category`, {
      method: "POST",
      body: JSON.stringify({ category }),
    }),
  getStepStats: (campaignId: number) =>
    request<{ campaign_id: number; steps: StepStat[] }>(`/campaigns/${campaignId}/step-stats`),
  getLeadDetail: (businessId: number) => request<LeadDetailResponse>(`/leads/${businessId}/detail`),
  suppressLead: (businessId: number) =>
    request<{ business_id: number; suppressed: number }>(`/leads/${businessId}/suppress`, { method: "POST" }),
  listSavedViews: () => request<SavedView[]>(`/lists`),
  saveView: (name: string, filters: Record<string, unknown>) =>
    request<SavedView>("/lists", { method: "POST", body: JSON.stringify({ name, filters }) }),
  deleteSavedView: (id: number) =>
    request<{ deleted: boolean; id: number }>(`/lists/${id}`, { method: "DELETE" }),
  listSuppression: (activeOnly = false) =>
    request<{ items: SuppressionEntry[]; total: number }>(`/suppression${activeOnly ? "?active_only=true" : ""}`),
  addSuppression: (data: { identifier: string; reason?: string; detail?: string; domain_wide?: boolean }) =>
    request<{ added: boolean; identifier: string; reason: string }>("/suppression", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateMailboxImap: (id: number, imap_host: string | null, imap_port?: number) =>
    request<{ id: number; imap_host: string | null; imap_port: number }>(`/mailboxes/${id}/imap`, {
      method: "POST",
      body: JSON.stringify({ imap_host, imap_port }),
    }),
  pollReplies: (mailboxId: number) =>
    request<{ mailbox_id: number; seen?: number; matched?: number; replies?: number; opt_outs?: number; error?: string }>(
      `/mailboxes/${mailboxId}/poll-replies`,
      { method: "POST" },
    ),
  getSetupStatus: () => request<SetupStatus>("/setup/status"),
  getProviderPresets: () => request<{ providers: ProviderPreset[] }>("/setup/providers"),
  updateSetupSetting: (key: string, value: string) =>
    request<{ key: string; value: string; persisted: boolean; restart_required: boolean; label: string }>(
      "/setup/settings",
      { method: "PUT", body: JSON.stringify({ key, value }) },
    ),
};
