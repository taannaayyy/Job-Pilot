import type { Company } from "./types";

/**
 * The organization's own LinkedIn jobs tab when its page is known (companies and
 * universities both have one), otherwise a LinkedIn job search for its name.
 */
export function linkedinJobsUrl(org: Pick<Company, "name" | "linkedin_url">): string {
  const page = org.linkedin_url?.match(/^https?:\/\/(?:[\w-]+\.)?linkedin\.com\/(?:company|school)\/[^/?#]+/i);
  if (page) return `${page[0]}/jobs/`;
  return `https://www.linkedin.com/jobs/search/?keywords=${encodeURIComponent(org.name)}`;
}

/** Checked more than this many days ago counts as due for another look. */
export const STALE_AFTER_DAYS = 14;
