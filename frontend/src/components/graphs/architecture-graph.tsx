"use client";
import { useMemo } from "react";
import { Background, Controls, Handle, MarkerType, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Boxes } from "lucide-react";
import type { ArchitectureComponent } from "@/lib/api/architecture-contract";
type ComponentNode = Node<{
    component: ArchitectureComponent;
}, "component">;
function ComponentCard({ data, selected }: NodeProps<ComponentNode>) {
    const { component } = data;
    return <div className="arch-node" data-selected={selected || undefined}>
  <Handle type="target" position={Position.Left} isConnectable={false}/>
  <div className="arch-node-title"><Boxes size={14} aria-hidden="true"/><strong>{component.name}</strong></div>
  <p>{component.responsibility}</p>
  <span className="arch-node-meta">{component.requirement_ids.length} requirement{component.requirement_ids.length === 1 ? "" : "s"} · {component.depends_on.length} dependenc{component.depends_on.length === 1 ? "y" : "ies"}</span>
  <Handle type="source" position={Position.Right} isConnectable={false}/>
 </div>;
}
const nodeTypes = { component: ComponentCard };
// Layered layout: a component sits one column left of everything it depends on,
// so dependency edges always point rightwards. Cycles are cut at the revisit.
export function layoutComponents(components: ArchitectureComponent[]) {
    const byName = new Map(components.map(c => [c.name, c]));
    const level = new Map<string, number>();
    const visiting = new Set<string>();
    const depth = (name: string): number => {
        const known = level.get(name);
        if (known !== undefined)
            return known;
        if (visiting.has(name))
            return 0;
        visiting.add(name);
        const deps = byName.get(name)?.depends_on.filter(d => byName.has(d)) ?? [];
        const value = deps.length ? 1 + Math.max(...deps.map(depth)) : 0;
        visiting.delete(name);
        level.set(name, value);
        return value;
    };
    components.forEach(c => depth(c.name));
    const max = Math.max(0, ...level.values());
    const rows = new Map<number, number>();
    const nodes: ComponentNode[] = components.map(c => {
        const column = max - (level.get(c.name) ?? 0);
        const row = rows.get(column) ?? 0;
        rows.set(column, row + 1);
        return { id: c.name, type: "component", position: { x: column * 250, y: row * 130 }, data: { component: c } };
    });
    const edges: Edge[] = components.flatMap(c => c.depends_on.filter(d => byName.has(d) && d !== c.name).map(d => ({ id: `${c.name}->${d}`, source: c.name, target: d, markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 }, className: "arch-edge" })));
    return { nodes, edges };
}
export function ArchitectureGraph({ components, selected, onSelect }: {
    components: ArchitectureComponent[];
    selected?: string;
    onSelect: (name: string) => void;
}) {
    const layout = useMemo(() => layoutComponents(components), [components]);
    const nodes = useMemo(() => layout.nodes.map(n => ({ ...n, selected: n.id === selected })), [layout, selected]);
    const edges = useMemo(() => layout.edges.map(e => ({ ...e, animated: e.source === selected || e.target === selected })), [layout, selected]);
    return <div className="arch-canvas" aria-label="Architecture component graph. Use the component list for keyboard navigation.">
  <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.2 }} minZoom={0.3} maxZoom={1.75} nodesDraggable={false} nodesConnectable={false} edgesFocusable={false} onNodeClick={(_, node) => onSelect(node.id)} proOptions={{ hideAttribution: true }}>
   <Background gap={20} size={1}/>
   <Controls showInteractive={false} position="bottom-left"/>
  </ReactFlow>
 </div>;
}
