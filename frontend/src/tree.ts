import type { SkillRow } from "./types";

export const SEP = " › ";

/** The nodes directly under parentId (null: the top level), in the user's order. */
export function children(nodes: SkillRow[], parentId: number | null): SkillRow[] {
  return nodes
    .filter((n) => n.placed && n.parent_id === parentId)
    .sort((a, b) => a.position - b.position || a.id - b.id);
}

/** The node and every node under it. */
export function descendants(nodes: SkillRow[], id: number): number[] {
  return [id, ...children(nodes, id).flatMap((c) => descendants(nodes, c.id))];
}

/** Depth-first, the order the tree is shown in. */
export function flat(nodes: SkillRow[], parentId: number | null = null, depth = 0): { node: SkillRow; depth: number }[] {
  return children(nodes, parentId).flatMap((n) => [{ node: n, depth }, ...flat(nodes, n.id, depth + 1)]);
}

/** The tree with one node moved, before the server answers, so the drop shows at once. */
export function moved(nodes: SkillRow[], id: number, parent: number | null, index: number): SkillRow[] {
  const node = nodes.find((n) => n.id === id)!;
  const position = new Map<number, number>();
  // The ones it leaves close the gap.
  if (node.placed) children(nodes, node.parent_id).filter((n) => n.id !== id).forEach((n, i) => position.set(n.id, i));
  const siblings = children(nodes, parent).filter((n) => n.id !== id);
  siblings.splice(index, 0, node);
  siblings.forEach((n, i) => position.set(n.id, i));
  return nodes.map((n) =>
    n.id === id
      ? { ...n, parent_id: parent, placed: true, position: position.get(id)! }
      : position.has(n.id)
        ? { ...n, position: position.get(n.id)! }
        : n,
  );
}
