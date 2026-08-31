/**
 * The bundled "opencode" provider ships under its upstream name (OpenCode
 * Zen); this product brands its agent runtime as Qoder, so all provider
 * surfaces (settings list, connected summary, model filters) show Qoder.
 */
export function qoderDisplayName(id: string, name: string): string {
  return id === "opencode" ? "Qoder" : name;
}

export function normalizeProviderNames<T extends { id: string; name: string }>(list: T[]): T[] {
  return list.map((p) => (p.id === "opencode" ? { ...p, name: "Qoder" } : p));
}
