// localStorage can throw (private mode, blocked storage); the app must still work without it.
// The copy of the app embedded on the website keeps its session in memory, so trying the app there
// never signs the visitor in to the site itself.
const embedded = typeof window !== "undefined" && window.self !== window.top;
const memory = new Map<string, string>();

export function load(key: string): string | null {
  if (embedded) return memory.get(key) ?? null;
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
export function save(key: string, value: string | null) {
  if (embedded) {
    if (value === null) memory.delete(key);
    else memory.set(key, value);
    return;
  }
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* ignore */
  }
}
