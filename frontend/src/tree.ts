import type { SkillGroupNode } from "./types";

export const SEP = " › ";

export function children(groups: SkillGroupNode[], parentId: number | null): SkillGroupNode[] {
  return groups.filter((g) => g.parent_id === parentId).sort((a, b) => a.position - b.position || a.id - b.id);
}

/** "Technologies › Cloud & infrastructure" */
export function path(groups: SkillGroupNode[], id: number | null): string {
  const byId = new Map(groups.map((g) => [g.id, g]));
  const names: string[] = [];
  for (let g = id === null ? undefined : byId.get(id); g; g = g.parent_id === null ? undefined : byId.get(g.parent_id))
    names.unshift(g.name);
  return names.join(SEP);
}

/** The group and every group under it. */
export function descendants(groups: SkillGroupNode[], id: number): number[] {
  return [id, ...children(groups, id).flatMap((c) => descendants(groups, c.id))];
}

/** Depth-first, the order the tree is shown in. */
export function flat(groups: SkillGroupNode[], parentId: number | null = null, depth = 0): { group: SkillGroupNode; depth: number }[] {
  return children(groups, parentId).flatMap((g) => [{ group: g, depth }, ...flat(groups, g.id, depth + 1)]);
}
