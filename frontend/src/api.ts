import type { Company, CompanyInput, Job, JobDetail, JobInput, Openings } from "./types";

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
  updateJob: (id: number, body: Partial<JobInput>) =>
    request<JobDetail>(`/jobs/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteJob: (id: number) => request<void>(`/jobs/${id}`, { method: "DELETE" }),
  listWatchlist: () => request<Company[]>("/companies?watching=true"),
  createCompany: (body: CompanyInput) => request<Company>("/companies", { method: "POST", body: JSON.stringify(body) }),
  updateCompany: (
    id: number,
    body: Partial<CompanyInput> & { watching?: boolean; openings?: Openings | null },
  ) => request<Company>(`/companies/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteCompany: (id: number) => request<void>(`/companies/${id}`, { method: "DELETE" }),
};
