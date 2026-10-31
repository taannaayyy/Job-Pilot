import type { SkillRow } from "./types";

export const UNSORTED = "unsorted";

/** A node of the skill tree on the Skill Gap map, with the postings that ask for it or anything under it. */
export interface MapNode {
  /** "s12" for a skill, "unsorted" for the skills not in the tree yet. */
  key: string;
  /** A group only organizes (and Unsorted is one); a skill is asked for, and can hold skills too. */
  kind: "group" | "skill";
  /** A skill that is a tool you can point to ("Docker"), not a concept ("Feature engineering"). */
  tool: boolean;
  name: string;
  description: string;
  children: MapNode[];
  jobs: Set<number>;
  /** Postings that name it themselves (the rest name something under it). */
  direct: number;
  /** Nodes under it, at any depth. */
  skills: number;
  /** Unset for Unsorted. */
  skill?: SkillRow;
  parent: MapNode | null;
}

/** "tree": the order the user gave the tree. */
export type MapSort = "tree" | "count" | "name";

const byOrder = (sort: MapSort) => (a: MapNode, b: MapNode) =>
  sort === "tree"
    ? (a.skill?.position ?? 0) - (b.skill?.position ?? 0)
    : (sort === "count" ? b.jobs.size - a.jobs.size : 0) || a.name.localeCompare(b.name, undefined, { sensitivity: "base" });

/** The whole tree from the gap's skills (Unsorted is apart: see waitingMap). hidden holds node keys
 *  ("s12"); a hidden node hides everything under it. onlyAsked leaves out what no posting asks for. */
export function buildMap(skills: SkillRow[], hidden: Set<string>, query: string, sort: MapSort, onlyAsked = false): MapNode[] {
  const order = byOrder(sort);

  const node = (s: SkillRow, kids: MapNode[]): MapNode => {
    const jobs = new Set(s.job_ids ?? []);
    kids.forEach((k) => k.jobs.forEach((j) => jobs.add(j)));
    return {
      key: `s${s.id}`, kind: s.is_group ? "group" : "skill", tool: s.is_tool && !s.is_group, name: s.name, description: s.description,
      children: kids.sort(order), jobs, direct: s.job_ids?.length ?? 0,
      skills: kids.reduce((n, k) => n + 1 + k.skills, 0), skill: s, parent: null,
    };
  };

  const under = (parentId: number | null): MapNode[] =>
    skills
      .filter((s) => s.placed && s.parent_id === parentId && !hidden.has(`s${s.id}`))
      .map((s) => node(s, under(s.id)));

  let roots = under(null).sort(byOrder("tree"));
  if (onlyAsked) roots = asked(roots);
  roots = filterMap(roots, query.trim().toLocaleLowerCase("tr"));
  link(roots, null);
  return roots;
}

/** The skills in Unsorted, asked for by postings and not in the tree yet; most asked first. */
export function waitingMap(skills: SkillRow[], query: string): MapNode[] {
  const q = query.trim().toLocaleLowerCase("tr");
  return skills
    .filter((s) => !s.placed && s.name.toLocaleLowerCase("tr").includes(q))
    .map((s): MapNode => ({
      key: `s${s.id}`, kind: s.is_group ? "group" : "skill", tool: s.is_tool && !s.is_group, name: s.name, description: s.description, children: [],
      jobs: new Set(s.job_ids ?? []), direct: s.job_ids?.length ?? 0, skills: 0, skill: s, parent: null,
    }))
    .sort((a, b) => b.jobs.size - a.jobs.size || a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
}

/** Unsorted as a place to drop a node on: it takes the node out of the tree. */
export const UNSORTED_TARGET: MapNode = {
  key: UNSORTED, kind: "group", tool: false, name: "Unsorted", description: "", children: [], jobs: new Set(), direct: 0, skills: 0, parent: null,
};

function asked(nodes: MapNode[]): MapNode[] {
  return nodes.filter((n) => n.jobs.size > 0).map((n) => ({ ...n, children: asked(n.children) }));
}

/** Keeps what matches the search, the nodes it sits under, and everything under a match. */
function filterMap(nodes: MapNode[], q: string): MapNode[] {
  if (!q) return nodes;
  return nodes.flatMap((n) => {
    if (n.name.toLocaleLowerCase("tr").includes(q)) return [n];
    const kids = filterMap(n.children, q);
    return kids.length ? [{ ...n, children: kids }] : [];
  });
}

function link(nodes: MapNode[], parent: MapNode | null) {
  nodes.forEach((n) => {
    n.parent = parent;
    link(n.children, n);
  });
}

export function findNode(nodes: MapNode[], key: string | null): MapNode | null {
  if (key === null) return null;
  for (const n of nodes) {
    if (n.key === key) return n;
    const hit = findNode(n.children, key);
    if (hit) return hit;
  }
  return null;
}

/** The node and the nodes above it, top first. */
export function lineage(node: MapNode | null): MapNode[] {
  const out: MapNode[] = [];
  for (let n = node; n; n = n.parent) out.unshift(n);
  return out;
}
