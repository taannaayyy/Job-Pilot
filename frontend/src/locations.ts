import type { Job } from "./types";

export const ISTANBUL = "Istanbul";

export type Side = "anadolu" | "avrupa";

export const SIDE_LABELS: Record<Side, string> = {
  anadolu: "Anadolu Yakası",
  avrupa: "Avrupa Yakası",
};

export const DISTRICTS: Record<Side, string[]> = {
  anadolu: [
    "Adalar", "Ataşehir", "Beykoz", "Çekmeköy", "Kadıköy", "Kartal", "Maltepe",
    "Pendik", "Sancaktepe", "Sultanbeyli", "Şile", "Tuzla", "Ümraniye", "Üsküdar",
  ],
  avrupa: [
    "Arnavutköy", "Avcılar", "Bağcılar", "Bahçelievler", "Bakırköy", "Başakşehir", "Bayrampaşa",
    "Beşiktaş", "Beylikdüzü", "Beyoğlu", "Büyükçekmece", "Çatalca", "Esenler", "Esenyurt",
    "Eyüpsultan", "Fatih", "Gaziosmanpaşa", "Güngören", "Kağıthane", "Küçükçekmece", "Sarıyer",
    "Silivri", "Sultangazi", "Şişli", "Zeytinburnu",
  ],
};

const SIDE_OF = new Map<string, Side>(
  (Object.keys(DISTRICTS) as Side[]).flatMap((side) => DISTRICTS[side].map((d) => [d, side] as const)),
);

export const sideOf = (district: string | null): Side | null => (district ? SIDE_OF.get(district) ?? null : null);

/** "Kadıköy (Anadolu)", "Istanbul", "Ankara", or null. */
export function locationLabel(job: Pick<Job, "city" | "district">): string | null {
  if (job.city === ISTANBUL && job.district) {
    const side = sideOf(job.district);
    return side ? `${job.district} (${side === "anadolu" ? "Anadolu" : "Avrupa"})` : job.district;
  }
  return job.city;
}

export type LocationFilter = "" | Side | "istanbul" | "other";

export function matchesLocation(job: Job, filter: LocationFilter): boolean {
  switch (filter) {
    case "":
      return true;
    case "istanbul":
      return job.city === ISTANBUL;
    case "other":
      return !!job.city && job.city !== ISTANBUL;
    default:
      return job.city === ISTANBUL && sideOf(job.district) === filter;
  }
}
