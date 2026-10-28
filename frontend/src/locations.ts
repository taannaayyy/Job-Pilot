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

export const SIDE_SHORT: Record<Side, string> = { anadolu: "Anadolu", avrupa: "Avrupa" };

/** "Kadıköy (Anadolu)", "Anadolu Yakası", "Istanbul", "Ankara", or null. */
export function locationLabel(job: Pick<Job, "city" | "side" | "district">): string | null {
  if (job.city === ISTANBUL) {
    const side = job.side ?? sideOf(job.district);
    if (job.district) return side ? `${job.district} (${SIDE_SHORT[side]})` : job.district;
    if (side) return SIDE_LABELS[side];
  }
  return job.city;
}

/** Case- and accent-insensitive key, so "kadikoy" finds "Kadıköy". */
export function fold(text: string): string {
  return text
    .toLocaleLowerCase("tr")
    .replace(/ı/g, "i")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
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
      return job.city === ISTANBUL && (job.side ?? sideOf(job.district)) === filter;
  }
}
