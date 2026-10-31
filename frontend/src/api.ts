import type {
  AIProvider,
  AIProviderInput,
  AISettings,
  Company,
  CompanyInput,
  ExtensionInfo,
  Importance,
  Job,
  JobDetail,
  JobInput,
  Openings,
  RoleGroup,
  SkillDetail,
  SkillRow,
  SkillGap,
  SkillMark,
} from "./types";

export type JobChanges = Partial<JobInput> & { target_group_id?: number | null; study_only?: boolean; raw_text?: string | null };
type AIBody = { provider: AIProvider; providers?: Record<string, AIProviderInput> };
const groupQuery = (groupId: number | null) => (groupId === null ? "" : `?group_id=${groupId}`);

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail))
        message = body.detail.map((d: { loc: string[]; msg: string }) => `${d.loc.at(-1)}: ${d.msg}`).join("; ");
    } catch {
      // keep the status text
    }
    throw new Error(message);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const api = {
  listJobs: () => request<Job[]>("/jobs"),
  getJob: (id: number) => request<JobDetail>(`/jobs/${id}`),
  createJob: (body: JobInput) => request<JobDetail>("/jobs", { method: "POST", body: JSON.stringify(body) }),
  updateJob: (id: number, body: JobChanges) =>
    request<JobDetail>(`/jobs/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteJob: (id: number) => request<void>(`/jobs/${id}`, { method: "DELETE" }),
  listCompanies: () => request<Company[]>("/companies"),
  createCompany: (body: CompanyInput & { watching?: boolean }) => request<Company>("/companies", { method: "POST", body: JSON.stringify(body) }),
  updateCompany: (
    id: number,
    body: Partial<CompanyInput> & { watching?: boolean; openings?: Openings | null },
  ) => request<Company>(`/companies/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteCompany: (id: number) => request<void>(`/companies/${id}`, { method: "DELETE" }),
  getExtension: () => request<ExtensionInfo>("/extension"),
  newExtensionKey: () => request<ExtensionInfo>("/extension/token", { method: "POST", body: "{}" }),
  installExtension: () => request<{ folder: string }>("/extension/install", { method: "POST", body: "{}" }),
  revealExtension: () => request<void>("/extension/reveal", { method: "POST", body: "{}" }),

  listGroups: () => request<RoleGroup[]>("/role-groups"),
  createGroup: (name: string) => request<RoleGroup>("/role-groups", { method: "POST", body: JSON.stringify({ name }) }),
  renameGroup: (id: number, name: string) =>
    request<RoleGroup>(`/role-groups/${id}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  deleteGroup: (id: number) => request<void>(`/role-groups/${id}`, { method: "DELETE" }),
  skillGap: (groupId: number | null) => request<SkillGap>(`/skill-gap${groupQuery(groupId)}`),
  getSkill: (id: number, groupId: number | null) => request<SkillDetail>(`/skills/${id}${groupQuery(groupId)}`),
  updateSkill: (
    id: number,
    body: {
      name?: string;
      description?: string;
      mark?: SkillMark | null;
      plan_note?: string;
      /** Moving it: under parent_id (null: the top level), at index among its new siblings. */
      parent_id?: number | null;
      index?: number;
      /** false: out of the tree, to Unsorted. */
      placed?: boolean;
    },
    groupId: number | null,
  ) =>
    request<SkillDetail>(`/skills/${id}${groupQuery(groupId)}`, { method: "PATCH", body: JSON.stringify(body) }),
  /** evidence: the words in the description it was picked from; they stay highlighted there. */
  addRequirement: (jobId: number, name: string, importance: Importance, evidence = "") =>
    request<JobDetail>(`/jobs/${jobId}/requirements`, { method: "POST", body: JSON.stringify({ name, importance, evidence }) }),
  setRequirementImportance: (jobId: number, id: number, importance: Importance) =>
    request<JobDetail>(`/jobs/${jobId}/requirements/${id}`, { method: "PATCH", body: JSON.stringify({ importance }) }),
  removeRequirement: (jobId: number, id: number) =>
    request<JobDetail>(`/jobs/${jobId}/requirements/${id}`, { method: "DELETE" }),
  listSkills: () => request<SkillRow[]>("/skills"),
  createSkill: (body: { name: string; parent_id: number | null; index?: number; is_group?: boolean; description?: string }) =>
    request<SkillRow[]>("/skills", { method: "POST", body: JSON.stringify(body) }),
  deleteSkill: (id: number) => request<SkillRow[]>(`/skills/${id}`, { method: "DELETE" }),
  chat: (messages: { role: "user" | "assistant"; content: string }[], provider?: AIProvider) =>
    request<{ reply: string; used: string }>("/ai/chat", { method: "POST", body: JSON.stringify({ messages, provider }) }),
  /** The user says this posting asks for this skill; evidence: the line in the posting. */
  connectJob: (skillId: number, jobId: number, evidence: string, groupId: number | null) =>
    request<SkillDetail>(`/skills/${skillId}/jobs${groupQuery(groupId)}`, { method: "POST", body: JSON.stringify({ job_id: jobId, evidence }) }),
  updateConnection: (skillId: number, jobId: number, body: { evidence?: string; importance?: Importance }, groupId: number | null) =>
    request<SkillDetail>(`/skills/${skillId}/jobs/${jobId}${groupQuery(groupId)}`, { method: "PATCH", body: JSON.stringify(body) }),
  disconnectJob: (skillId: number, jobId: number, groupId: number | null) =>
    request<SkillDetail>(`/skills/${skillId}/jobs/${jobId}${groupQuery(groupId)}`, { method: "DELETE" }),

  getAISettings: () => request<AISettings>("/ai/settings"),
  saveAISettings: (body: AIBody) => request<AISettings>("/ai/settings", { method: "PUT", body: JSON.stringify(body) }),
  listModels: (body: AIBody) => request<{ models: string[] }>("/ai/models", { method: "POST", body: JSON.stringify(body) }),
  testAI: (body: AIBody) =>
    request<{ used: string; seconds: number; reply: string }>("/ai/test", { method: "POST", body: JSON.stringify(body) }),
};
