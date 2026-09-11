const API_BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '');

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
  sent_count: number;
  opened_count: number;
  open_rate: number;
  replied_count: number;
  reply_rate: number;
  created_at: string | null;
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
  createCampaign: (data: { name: string; steps: Array<{ subject: string; body_text: string; body_html?: string; delay_days?: number }> }) =>
    request('/campaigns', { method: 'POST', body: JSON.stringify(data) }),
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
};
