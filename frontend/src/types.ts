export const STATUSES = [
  "inbox",
  "saved",
  "applied",
  "screening",
  "interview",
  "awaiting",
  "offer",
  "rejected",
  "ghosted",
] as const;
export type Status = (typeof STATUSES)[number];

export const STATUS_LABELS: Record<Status, string> = {
  inbox: "Inbox",
  saved: "Saved",
  applied: "Applied",
  screening: "Screening",
  interview: "Interview",
  awaiting: "Awaiting decision",
  offer: "Offer",
  rejected: "Rejected",
  ghosted: "Ghosted",
};

export const JOB_TYPES = ["full_time", "part_time", "internship", "contract"] as const;
export type JobType = (typeof JOB_TYPES)[number];

export const JOB_TYPE_LABELS: Record<JobType, string> = {
  full_time: "Full-time",
  part_time: "Part-time",
  internship: "Internship",
  contract: "Contract",
};

/** Board column headers are narrow at small window sizes. */
export const STATUS_SHORT_LABELS: Record<Status, string> = { ...STATUS_LABELS, awaiting: "Awaiting" };

export const WORK_MODES = ["remote", "hybrid", "onsite"] as const;
export type WorkMode = (typeof WORK_MODES)[number];

export const WORK_MODE_LABELS: Record<WorkMode, string> = {
  remote: "Remote",
  hybrid: "Hybrid",
  onsite: "Onsite",
};

export interface Job {
  id: number;
  company: string;
  company_id: number;
  company_website: string | null;
  company_watching: boolean;
  logo_url: string | null;
  title: string;
  url: string | null;
  city: string | null;
  side: "anadolu" | "avrupa" | null;
  district: string | null;
  job_type: JobType | null;
  work_mode: WorkMode | null;
  source: string | null;
  status: Status;
  next_action: string | null;
  notes: string;
  date_saved: string;
  date_applied: string | null;
  /** Skill Gap: the role group this job is a target of. */
  target_group_id: number | null;
  /** Kept only to study the role; hidden from the job board. */
  study_only: boolean;
  extraction_status: ExtractionStatus | null;
}

export interface StatusEvent {
  id: number;
  from_status: Status | null;
  to_status: Status;
  timestamp: string;
}

export interface JobDetail extends Job {
  events: StatusEvent[];
  /** Job description captured from the posting by the Chrome extension, or pasted. */
  raw_text: string | null;
  extraction_error: string | null;
  extracted_at: string | null;
  extracted_with: string | null;
  requirements: Requirement[];
}

// ---- Skill Gap

export type ExtractionStatus = "pending" | "running" | "done" | "failed";
export type Importance = "must" | "nice";

export const SKILL_MARKS = ["have", "learning", "gap", "ignore"] as const;
export type SkillMark = (typeof SKILL_MARKS)[number];
export const SKILL_MARK_LABELS: Record<SkillMark, string> = {
  have: "Have",
  learning: "Learning",
  gap: "Gap",
  ignore: "Ignore",
};

export const SKILL_CATEGORY_LABELS: Record<string, string> = {
  language: "Language",
  framework: "Framework",
  tool: "Tool",
  cloud: "Cloud",
  database: "Database",
  concept: "Concept",
  practice: "Practice",
  experience: "Experience",
  education: "Education",
  spoken_language: "Spoken language",
  soft_skill: "Soft skill",
  other: "Other",
};

export interface Requirement {
  id: number;
  skill_id: number;
  name: string;
  category: string;
  importance: Importance;
  evidence: string | null;
  /** "dictionary", "model" or "user" */
  source: string;
  mark: SkillMark | null;
  min_years: number | null;
  max_years: number | null;
  /** Degrees: the accepted fields of study. */
  detail: string | null;
}

/** A node of the tree requirements are filed in. */
export interface SkillGroupNode {
  id: number;
  /** Set for groups of the starting tree. */
  key: string | null;
  name: string;
  description: string;
  parent_id: number | null;
  position: number;
  skill_count: number;
}

export interface RoleGroup {
  id: number;
  name: string;
  job_count: number;
}

export interface SkillRow {
  id: number;
  name: string;
  category: string;
  group_id: number | null;
  /** The skill it belongs to: pandas to Python. */
  parent_id: number | null;
  mark: SkillMark | null;
  plan_note: string;
  jobs: number;
  must: number;
  nice: number;
  /** Years the targets ask for: "1+", "3–5". */
  years: string[];
  /** Degrees: accepted fields of study. */
  details: string[];
}

export interface SkillGap {
  targets: number;
  extracted: number;
  pending: number;
  failed: number;
  without_text: number;
  /** 0..1; null when there is nothing to cover yet. */
  coverage: number | null;
  skills: SkillRow[];
  groups: SkillGroupNode[];
}

export interface SkillDetail {
  id: number;
  name: string;
  category: string;
  group_id: number | null;
  parent_id: number | null;
  /** The user placed it; reading postings again won't move it. */
  group_locked: boolean;
  mark: SkillMark | null;
  plan_note: string;
  jobs: {
    job_id: number;
    title: string;
    company: string;
    importance: Importance;
    evidence: string | null;
    years: string | null;
    detail: string | null;
  }[];
  history: { from_mark: SkillMark | null; to_mark: SkillMark | null; timestamp: string }[];
}

export type AIProvider = "none" | "ollama" | "openai" | "anthropic" | "claude_code";

export interface AIProviderSettings {
  base_url?: string;
  model?: string;
  /** Claude Code's program, when it isn't found by itself. */
  path?: string;
  /** Claude Code: how long the model thinks (low, medium, high, xhigh, max). */
  effort?: string;
  /** The model, not the dictionary, says whether a skill is a must or a nice to have. */
  model_decides?: boolean;
  /** Only whether a key is saved; the key itself is never sent to the page. */
  has_key?: boolean;
}

export interface AISettings {
  provider: AIProvider;
  providers: Record<string, AIProviderSettings>;
}

export type AIProviderInput = { base_url?: string; model?: string; api_key?: string; path?: string; effort?: string; model_decides?: boolean };

export interface ExtensionInfo {
  token: string;
  last_seen: string | null;
  capture_port: number;
  /** Set when another program held the extension's port and the app opened on another one. */
  port_blocked_by: string | null;
  folder_available: boolean;
}

export type JobInput = {
  company: string;
  company_website: string | null;
  title: string;
  url: string | null;
  city: string | null;
  side: "anadolu" | "avrupa" | null;
  district: string | null;
  job_type: JobType | null;
  work_mode: WorkMode | null;
  source: string | null;
  next_action: string | null;
  notes: string;
  status?: Status;
};

export const ORG_KINDS = ["company", "startup", "research", "university", "other"] as const;
export type OrgKind = (typeof ORG_KINDS)[number];

export const ORG_KIND_LABELS: Record<OrgKind, string> = {
  company: "Company",
  startup: "Startup",
  research: "Research center",
  university: "University",
  other: "Other",
};

/** Result of the last check for open positions; null means never checked. */
export type Openings = "hiring" | "none";

export interface Company {
  id: number;
  name: string;
  kind: OrgKind;
  website: string | null;
  careers_url: string | null;
  linkedin_url: string | null;
  notes: string;
  watching: boolean;
  date_watched: string | null;
  openings: Openings | null;
  last_checked_at: string | null;
  logo_url: string | null;
}

export type CompanyInput = {
  name: string;
  kind: OrgKind;
  website: string | null;
  careers_url: string | null;
  linkedin_url: string | null;
  notes: string;
};
