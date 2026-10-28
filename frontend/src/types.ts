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
}

export interface StatusEvent {
  id: number;
  from_status: Status | null;
  to_status: Status;
  timestamp: string;
}

export interface JobDetail extends Job {
  events: StatusEvent[];
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
