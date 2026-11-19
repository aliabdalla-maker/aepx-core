"use client";
import { useState } from "react";
import type { TreeNode } from "../lib/workspace";

type Props = {
  nodes: TreeNode[]; active: string; dirty: Set<string>; onOpen: (path: string) => void;
  /** Optional folder actions; shown only when provided (hidden for read-only roles). */
  onRenameFolder?: (path: string) => void; onDeleteFolder?: (path: string) => void;
};

export default function FileTree({ nodes, ...rest }: Props) {
  return <ul className="tree" role="tree" aria-label="Project files">
    {nodes.map(n => <Node key={n.path} node={n} depth={0} {...rest} />)}
  </ul>;
}

function Node({ node, depth, active, dirty, onOpen, onRenameFolder, onDeleteFolder }: { node: TreeNode; depth: number } & Omit<Props, "nodes">) {
  const [open, setOpen] = useState(true);
  const pad = { paddingLeft: 8 + depth * 12 };
  if (node.children) {
    return <li role="treeitem" aria-expanded={open}>
      <div className="tree-folder-row">
        <button className="tree-row folder" style={pad} onClick={() => setOpen(o => !o)}>
          <span aria-hidden>{open ? "▾" : "▸"}</span> {node.name}
        </button>
        {onRenameFolder && <button className="icon tree-action" title={`Rename or move folder ${node.path}`}
          aria-label={`Rename folder ${node.path}`} onClick={() => onRenameFolder(node.path)}>✎</button>}
        {onDeleteFolder && <button className="icon tree-action" title={`Delete folder ${node.path}`}
          aria-label={`Delete folder ${node.path}`} onClick={() => onDeleteFolder(node.path)}>🗑</button>}
      </div>
      {open && <ul role="group">{node.children.map(c =>
        <Node key={c.path} node={c} depth={depth + 1} active={active} dirty={dirty} onOpen={onOpen}
          onRenameFolder={onRenameFolder} onDeleteFolder={onDeleteFolder} />)}</ul>}
    </li>;
  }
  return <li role="treeitem" aria-selected={active === node.path}>
    <button className={"tree-row" + (active === node.path ? " active" : "")} style={pad}
      onClick={() => onOpen(node.path)} title={node.path}>
      {node.name}{dirty.has(node.path) && <span className="dot" aria-label="unsaved changes"> ●</span>}
    </button>
  </li>;
}
