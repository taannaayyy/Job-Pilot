export const STATUSES = [
  "inbox",
  "saved",
  "applied",
  "screening",
  "interview",
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
  offer: "Offer",
  rejected: "Rejected",
  ghosted: "Ghosted",
};

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
  logo_url: string | null;
  title: string;
  url: string | null;
  city: string | null;
  side: "anadolu" | "avrupa" | null;
  district: string | null;
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
  work_mode: WorkMode | null;
  source: string | null;
  next_action: string | null;
  notes: string;
  status?: Status;
};
