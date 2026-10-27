// Remembers the last artifact IDs opened per project in this browser, so a
// workspace can reopen them from the backend after a reload. Only IDs are
// stored; the content is always fetched again. Storage may be unavailable.
type Kind = "rset" | "arch" | "vplan";
const key = (projectId: string, kind: Kind) => `aew:last:${projectId}:${kind}`;
export function rememberArtifact(projectId: string, kind: Kind, id: string) {
    try {
        window.localStorage.setItem(key(projectId, kind), id);
    }
    catch { /* storage unavailable: nothing to remember */ }
}
export function recallArtifact(projectId: string, kind: Kind): string | null {
    try {
        const id = window.localStorage.getItem(key(projectId, kind));
        return id && /^[A-Z]{2,5}-\d+$/.test(id) ? id : null;
    }
    catch {
        return null;
    }
}
