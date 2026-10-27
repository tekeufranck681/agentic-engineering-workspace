"use client";
import { useEffect, useMemo } from "react";
import { Background, Controls, Handle, MarkerType, Position, ReactFlow, ReactFlowProvider, useReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { artifacts, links, type Artifact } from "./scenario";
import styles from "./trace.module.css";
const columnOf = new Map(artifacts.map(a => [a.id, a.x]));
type ArtifactNode = Node<{ artifact: Artifact; state: "selected" | "lineage" | "dim" | "idle" }, "artifact">;
function ArtifactCard({ data }: NodeProps<ArtifactNode>) {
    const { artifact: a, state } = data;
    return <div className={styles.node} data-kind={a.kind} data-tone={a.tone} data-state={state}>
  <Handle id="l" type="target" position={Position.Left} isConnectable={false}/>
  <Handle id="t" type="target" position={Position.Top} isConnectable={false}/>
  <div className={styles.nodeHead}><span>{a.label}</span><code>{a.id}</code></div>
  <strong>{a.title}</strong>
  {a.tone && <span className={styles.nodeTone}>{a.tone === "pass" ? "Pass" : a.tone === "fail" ? "Fail" : "Correction"}</span>}
  <Handle id="r" type="source" position={Position.Right} isConnectable={false}/>
  <Handle id="b" type="source" position={Position.Bottom} isConnectable={false}/>
 </div>;
}
const nodeTypes = { artifact: ArtifactCard };
// Every artifact upstream or downstream of `id`: its full lineage.
export function lineageOf(id: string) {
    const walk = (start: string, dir: 0 | 1) => {
        const seen = new Set<string>();
        const queue = [start];
        while (queue.length) {
            const cur = queue.shift()!;
            for (const l of links)
                if (l[dir] === cur && !seen.has(l[1 - dir])) {
                    seen.add(l[1 - dir]);
                    queue.push(l[1 - dir]);
                }
        }
        return seen;
    };
    return new Set([id, ...walk(id, 0), ...walk(id, 1)]);
}
function Graph({ selected, focus, onSelect }: { selected?: string; focus: string[]; onSelect: (id: string) => void }) {
    const flow = useReactFlow();
    const lineage = useMemo(() => (selected ? lineageOf(selected) : null), [selected]);
    const nodes: ArtifactNode[] = useMemo(() => artifacts.map(a => ({
        id: a.id, type: "artifact", position: { x: a.x, y: a.y }, selected: a.id === selected,
        data: { artifact: a, state: !lineage ? "idle" : a.id === selected ? "selected" : lineage.has(a.id) ? "lineage" : "dim" },
    })), [lineage, selected]);
    const edges: Edge[] = useMemo(() => links.map(([s, t]) => {
        const on = !!lineage && lineage.has(s) && lineage.has(t);
        // Links within one column leave the bottom and enter the top, so they
        // read as "then" rather than looping back across the column.
        const vertical = columnOf.get(s) === columnOf.get(t);
        return { id: `${s}->${t}`, source: s, target: t, sourceHandle: vertical ? "b" : "r", targetHandle: vertical ? "t" : "l", type: "smoothstep", className: on ? styles.edgeOn : styles.edge, markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: on ? "#2563eb" : "#c4c4cc" } };
    }), [lineage]);
    const focusKey = focus.join("|");
    useEffect(() => {
        const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const ids = focusKey ? focusKey.split("|") : [];
        const id = requestAnimationFrame(() => void flow.fitView({ nodes: ids.length ? ids.map(i => ({ id: i })) : undefined, padding: ids.length ? 0.28 : 0.12, duration: reduce ? 0 : 520, maxZoom: 1.1 }));
        return () => cancelAnimationFrame(id);
    }, [flow, focusKey]);
    return <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.12 }} minZoom={0.35} maxZoom={1.4} nodesDraggable={false} nodesConnectable={false} edgesFocusable={false} zoomOnScroll={false} preventScrolling={false} onNodeClick={(_, n) => onSelect(n.id)} proOptions={{ hideAttribution: true }}>
  <Background gap={24} size={1} color="#e4e4e7"/>
  <Controls showInteractive={false} position="bottom-right"/>
 </ReactFlow>;
}
export default function TraceExplorer(props: { selected?: string; focus: string[]; onSelect: (id: string) => void }) {
    return <div className={styles.canvas}>
  <ReactFlowProvider><Graph {...props}/></ReactFlowProvider>
 </div>;
}
