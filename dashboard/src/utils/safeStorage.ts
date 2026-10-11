/**
 * safeStorage — crash-safe wrapper around localStorage / sessionStorage.
 *
 * In private/incognito mode (or when cookies are blocked), ANY access to
 * localStorage/sessionStorage can throw a SecurityError or
 * QuotaExceededError — even a plain `getItem`. An unguarded call inside
 * `getAuthToken()` would take down the entire auth flow instead of just
 * behaving like "not logged in".
 *
 * Every helper here degrades gracefully and NEVER throws:
 *  - get()    → returns the stored value, or null when unavailable/missing
 *  - set()    → always records into an in-memory map, then tries the real
 *               store; if the real store throws, the app keeps working for
 *               the lifetime of the page (auth token survives the session)
 *  - remove() → clears both the real store (when available) and the map
 *
 * In normal mode the native store is the source of truth, so behaviour is
 * identical to direct localStorage/sessionStorage access.
 */

export type StoreKind = "local" | "session";

/** In-memory fallback used when the native store throws (private mode). */
const memoryFallback = new Map<string, string>();

function mapKey(kind: StoreKind, key: string): string {
  return `${kind}:${key}`;
}

/** Returns the native Storage object, or null when it is inaccessible. */
function getNativeStore(kind: StoreKind): Storage | null {
  try {
    if (typeof window === "undefined") return null;
    return kind === "local" ? window.localStorage : window.sessionStorage;
  } catch {
    // Accessing window.localStorage itself can throw in locked-down contexts.
    return null;
  }
}

export const safeStorage = {
  /** Read a value. Returns null when missing or when storage is unavailable. */
  get(kind: StoreKind, key: string): string | null {
    const store = getNativeStore(kind);
    if (store) {
      try {
        const value = store.getItem(key);
        // Keep the memory map in sync while the native store is healthy.
        if (value === null) {
          memoryFallback.delete(mapKey(kind, key));
        } else {
          memoryFallback.set(mapKey(kind, key), value);
        }
        return value;
      } catch {
        // Native store threw — fall through to the in-memory fallback.
      }
    }
    return memoryFallback.get(mapKey(kind, key)) ?? null;
  },

  /** Write a value. Never throws; falls back to memory when needed. */
  set(kind: StoreKind, key: string, value: string): void {
    memoryFallback.set(mapKey(kind, key), value);
    const store = getNativeStore(kind);
    if (!store) return;
    try {
      store.setItem(key, value);
    } catch {
      // Storage unavailable (private mode / quota) — memory map already
      // holds the value, so the session keeps working.
    }
  },

  /** Remove a value. Never throws. */
  remove(kind: StoreKind, key: string): void {
    memoryFallback.delete(mapKey(kind, key));
    const store = getNativeStore(kind);
    if (!store) return;
    try {
      store.removeItem(key);
    } catch {
      // Ignore — the in-memory copy is already gone.
    }
  },
};
