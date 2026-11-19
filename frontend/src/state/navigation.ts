import { useCallback, useEffect, useRef, useState } from "react";

export type Route = { page: "dashboard" } | { page: "editor"; id: string };

export function parseHash(hash: string): Route {
  const m = /^#\/p\/([^/]+)$/.exec(hash);
  if (m?.[1]) return { page: "editor", id: decodeURIComponent(m[1]) };
  return { page: "dashboard" };
}

export function hashFor(route: Route): string {
  return route.page === "editor" ? `#/p/${encodeURIComponent(route.id)}` : "#/";
}

/** Registered by the editor while a project is open, so leaving can be confirmed. */
export interface LeaveGuard {
  title: string;
  isDirty: () => boolean;
  /** Resolves true if the working copy is now safely stored. */
  save: () => Promise<boolean>;
}

let guard: LeaveGuard | null = null;
export function setLeaveGuard(next: LeaveGuard | null): void {
  guard = next;
}

export interface RouterState {
  route: Route;
  navigate: (to: Route) => void;
  /** Set while the user is being asked what to do with unsaved changes. */
  pendingLeave: { target: Route; title: string } | null;
  saveAndLeave: () => Promise<void>;
  discardAndLeave: () => void;
  stay: () => void;
}

export function useRoute(): RouterState {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  const routeRef = useRef(route);
  const [pendingLeave, setPendingLeave] = useState<RouterState["pendingLeave"]>(null);

  const go = useCallback((next: Route) => {
    routeRef.current = next;
    setRoute(next);
  }, []);

  useEffect(() => {
    const onHash = () => {
      const next = parseHash(window.location.hash);
      const current = routeRef.current;
      if (hashFor(next) === hashFor(current)) return;
      if (guard?.isDirty()) {
        window.history.replaceState(null, "", hashFor(current)); // undo the address-bar change
        setPendingLeave({ target: next, title: guard.title });
        return;
      }
      go(next);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [go]);

  const navigate = useCallback((to: Route) => {
    window.location.hash = hashFor(to);
  }, []);

  const leave = useCallback(
    (target: Route) => {
      setPendingLeave(null);
      setLeaveGuard(null);
      window.history.replaceState(null, "", hashFor(target));
      go(target);
    },
    [go],
  );

  return {
    route,
    navigate,
    pendingLeave,
    saveAndLeave: async () => {
      if (!pendingLeave) return;
      if (await guard?.save()) leave(pendingLeave.target);
      else setPendingLeave(null); // save failed or conflicted: stay; the editor shows why
    },
    discardAndLeave: () => {
      if (pendingLeave) leave(pendingLeave.target);
    },
    stay: () => setPendingLeave(null),
  };
}
