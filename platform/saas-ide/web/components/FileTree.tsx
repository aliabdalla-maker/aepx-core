"use client";
import { useState } from "react";
import type { TreeNode } from "../lib/workspace";

type Props = { nodes: TreeNode[]; active: string; dirty: Set<string>; onOpen: (path: string) => void };

export default function FileTree({ nodes, active, dirty, onOpen }: Props) {
  return <ul className="tree" role="tree" aria-label="Project files">
    {nodes.map(n => <Node key={n.path} node={n} depth={0} active={active} dirty={dirty} onOpen={onOpen} />)}
  </ul>;
}

function Node({ node, depth, active, dirty, onOpen }: { node: TreeNode; depth: number } & Omit<Props, "nodes">) {
  const [open, setOpen] = useState(true);
  const pad = { paddingLeft: 8 + depth * 12 };
  if (node.children) {
    return <li role="treeitem" aria-expanded={open}>
      <button className="tree-row folder" style={pad} onClick={() => setOpen(o => !o)}>
        <span aria-hidden>{open ? "▾" : "▸"}</span> {node.name}
      </button>
      {open && <ul role="group">{node.children.map(c =>
        <Node key={c.path} node={c} depth={depth + 1} active={active} dirty={dirty} onOpen={onOpen} />)}</ul>}
    </li>;
  }
  return <li role="treeitem" aria-selected={active === node.path}>
    <button className={"tree-row" + (active === node.path ? " active" : "")} style={pad}
      onClick={() => onOpen(node.path)} title={node.path}>
      {node.name}{dirty.has(node.path) && <span className="dot" aria-label="unsaved changes"> ●</span>}
    </button>
  </li>;
}
