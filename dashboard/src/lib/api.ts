/**
 * Same-origin by default. The dashboard is frequently deployed on a LAN box or
 * inside Docker where `localhost:8000` is NOT the backend — a build-time
 * absolute URL baked into the browser bundle breaks those installs (the
 * browser resolves "localhost" to whichever machine is running the browser).
 *
 * With the default `/api/v1` the browser calls the Next server, and
 * `next.config.mjs` proxies `/api/*` to the real backend (see `API_PROXY_URL`).
 * An explicit `NEXT_PUBLIC_API_URL` still wins for people who want direct
 * CORS calls — unless it points at localhost, which is exactly the value that
 * gets baked in by default and is the one that breaks remote installs.
 */
const CONFIGURED_API_URL = (process.env.NEXT_PUBLIC_API_URL || '').trim();
const IS_LOCALHOST_URL = /^https?:\/\/(localhost|127\.0\.0\.1|0\.0\.0\.0)(:|\/|$)/i.test(CONFIGURED_API_URL);
const API_BASE = (IS_LOCALHOST_URL || !CONFIGURED_API_URL ? '/api/v1' : CONFIGURED_API_URL).replace(/\/$/, '');

/** Requests are abandoned after this long so a hung socket can't wedge a page. */
const DEFAULT_TIMEOUT_MS = 30_000;
/** Extra attempts after the first one (network errors and 5xx only). */
const DEFAULT_RETRIES = 1;
const RETRY_BASE_DELAY_MS = 400;

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
  /** Leads the operator actually found. */
  real_leads?: number;
  /** The sample rows a fresh database is seeded with. */
  demo_leads?: number;
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
  /**
   * True for the sample rows a fresh database is seeded with. Without this
   * the overview reports "83 businesses in your database" when those 83 are
   * demo data the user never found.
   */
  is_demo?: boolean;
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

// --- People (the Apollo "People" view: one row per human) --------------------

export interface PersonRow {
  id: number;
  name: string;
  first_name: string | null;
  last_name: string | null;
  title: string | null;
  seniority: string;
  seniority_label: string;
  is_decision_maker: boolean;
  /**
   * Whether a real human was identified. A row where this is false is the
   * *business* as an outreach target - a phone and a WhatsApp number, but
   * no person behind it yet.
   */
  is_person: boolean;
  contact_kind: "person" | "business";
  email: string | null;
  phone: string | null;
  whatsapp_link: string | null;
  linkedin_url: string | null;
  preferred_channel: string | null;
  is_verified: boolean;
  verification_status: string | null;
  is_role_account: boolean;
  unsubscribed: boolean;
  source: string | null;
  business_id: number | null;
  business_name: string | null;
  business_website: string | null;
  business_phone: string | null;
  business_rating: number | null;
  industry: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  market_tier: string | null;
  employee_count: number | null;
  size_bucket: string | null;
  revenue: number | null;
  revenue_band: string | null;
  technologies: string[];
  lead_score: number | null;
  created_at: string | null;
}

export interface PeopleResponse {
  total: number;
  page: number;
  limit: number;
  pages: number;
  people: PersonRow[];
}

export interface PeopleStats {
  total_people: number;
  /** Businesses with a phone but no identified person behind them yet. */
  business_targets: number;
  total_contacts: number;
  named_people: number;
  with_email: number;
  verified: number;
  decision_makers: number;
  /** Share of contacts where a real human was identified. */
  coverage: number;
}

export interface PeopleFacets {
  seniority: Array<{ value: string; label: string; count: number }>;
  city: Array<{ value: string; count: number }>;
  state: Array<{ value: string; count: number }>;
  market_tier: Array<{ value: string; count: number }>;
  industry: Array<{ value: string; count: number }>;
  size_bucket: Array<{ value: string; count: number }>;
  revenue_band: Array<{ value: string; count: number }>;
}

export interface PeopleQuery {
  page?: number;
  limit?: number;
  search?: string;
  seniority?: string;
  decision_makers_only?: boolean;
  city?: string;
  state?: string;
  market_tier?: string;
  industry?: string;
  has_email?: boolean;
  verified_only?: boolean;
  size_bucket?: string;
  min_employees?: number;
  max_employees?: number;
  revenue_band?: string;
  technology?: string;
  sort?: string;
  desc?: boolean;
  include_demo?: boolean;
  person_only?: boolean;
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

/** Error carrying the HTTP status so callers can branch on 404/5xx. */
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export interface RequestOptions extends RequestInit {
  /** Abort the request after N ms (default 30s). */
  timeoutMs?: number;
  /** Extra attempts after the first one (default 1 => 2 attempts total). */
  retries?: number;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** 5xx and network-level failures are worth a second try; 4xx are not. */
const isRetryableStatus = (status: number) => status >= 500;

/**
 * The single HTTP door to the backend.
 *
 * - every request has a hard timeout, so a half-open socket can't leave a
 *   page spinning forever;
 * - transient failures (network errors, 5xx) are retried once with backoff;
 * - the caller may pass its own `signal` to cancel in-flight work, which is
 *   what the leads page uses to drop stale responses.
 */
async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, retries = DEFAULT_RETRIES, ...init } = options;
  const url = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;

  let lastError: unknown = new Error(`Request failed: ${path}`);

  for (let attempt = 0; attempt <= retries; attempt++) {
    const controller = new AbortController();
    let timedOut = false;

    // The caller may cancel us mid-flight (e.g. a newer search superseded an
    // older one). Never swallow that — it must surface as an abort error.
    const externalSignal = init.signal ?? null;
    const forwardAbort = () => controller.abort();
    if (externalSignal) {
      if (externalSignal.aborted) controller.abort();
      else externalSignal.addEventListener('abort', forwardAbort);
    }

    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);

    try {
      const headers = new Headers(init.headers as HeadersInit | undefined);
      if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json');

      const res = await fetch(url, {
        ...init,
        signal: controller.signal,
        headers,
      });

      if (!res.ok) {
        const errText = await res.text();
        let msg = `HTTP error ${res.status}`;
        try {
          const parsed = JSON.parse(errText);
          msg = parsed.detail || parsed.message || msg;
        } catch {}
        const apiErr = new ApiError(msg, res.status);
        if (isRetryableStatus(res.status) && attempt < retries) {
          lastError = apiErr;
        } else {
          throw apiErr;
        }
      } else {
        return (await res.json()) as T;
      }
    } catch (err: any) {
      if (timedOut) {
        lastError = new ApiError(`Request timed out after ${timeoutMs}ms`, 408);
      } else if (err instanceof ApiError) {
        // Already classified above (non-retryable status) — let it through.
        throw err;
      } else if (err?.name === 'AbortError' && externalSignal?.aborted) {
        // Deliberate cancellation — propagate without retrying.
        throw err;
      } else {
        // Network-level failure (DNS, refused connection, socket reset).
        lastError = err instanceof Error ? err : new Error(String(err));
        console.error(`API network error on ${path}:`, lastError);
      }
      if (attempt >= retries) throw lastError;
    } finally {
      // Always clear the timer, even on the retry path.
      clearTimeout(timer);
      if (externalSignal) externalSignal.removeEventListener('abort', forwardAbort);
    }

    // Backoff before the next attempt.
    await sleep(RETRY_BASE_DELAY_MS * (attempt + 1));
  }

  throw lastError;
}

export interface LeadsResponse {
  total: number;
  page: number;
  limit: number;
  leads: LeadItem[];
}

export interface CreateLeadResponse {
  id: number;
  name?: string;
  status?: string;
  [key: string]: unknown;
}

export interface CreateMailboxResponse {
  id: number;
  email: string;
  status: string;
}

export interface CampaignActionResponse {
  status: string;
  message: string;
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
    return request<LeadsResponse>(`/leads?${q.toString()}`);
  },
  createLead: (data: { name: string; phone?: string; email?: string; website?: string; address?: string; industry?: string }) =>
    request<CreateLeadResponse>('/leads', { method: 'POST', body: JSON.stringify(data) }),
  deleteLead: (id: number) => request<{ status?: string; id?: number }>(`/leads/${id}`, { method: 'DELETE' }),
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

  // People (one row per human)
  getPeople: (params: PeopleQuery = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v === undefined || v === null || v === "") return;
      q.set(k, String(v));
    });
    return request<PeopleResponse>(`/contacts?${q.toString()}`);
  },
  getPeopleStats: () => request<PeopleStats>("/contacts/stats"),
  getPeopleFacets: () => request<PeopleFacets>("/contacts/facets"),

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
  launchCampaign: (id: number) => request<CampaignActionResponse>(`/campaigns/${id}/launch`, { method: 'POST' }),
  pauseCampaign: (id: number) => request<CampaignActionResponse>(`/campaigns/${id}/pause`, { method: 'POST' }),
  previewTemplate: (subject: string, body: string) =>
    request<{ sample_variables_used: any; rendered_subject: string; rendered_body: string }>('/campaigns/preview', {
      method: 'POST',
      body: JSON.stringify({ subject, body }),
    }),

  // Mailboxes
  getMailboxes: () => request<MailboxItem[]>('/mailboxes'),
  createMailbox: (data: { email: string; password: string; smtp_host: string; smtp_port?: number; first_name?: string; last_name?: string; daily_limit?: number }) =>
    request<CreateMailboxResponse>('/mailboxes', { method: 'POST', body: JSON.stringify(data) }),
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
