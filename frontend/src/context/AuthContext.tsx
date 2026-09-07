// Stub "login": lets the user pick a role + actor id, since E8-S1's backend
// auth is a header-based stub with no real credential check (BRD sec 7.1).
// Persisted to sessionStorage (tab-scoped, cleared when the tab closes) so a
// page reload or a direct URL navigation to a protected route doesn't drop
// the picked actor -- without this, RoleGuard would show "Access denied" on
// every refresh even for a role that was already selected.

import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { Role } from "../types/enums";
import type { ActorContext } from "../types/models";

interface AuthContextValue {
  actor: ActorContext | null;
  setActor: (role: Role, actorId: string) => void;
  clearActor: () => void;
}

const STORAGE_KEY = "claimflow.actor";

function readStoredActor(): ActorContext | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as ActorContext) : null;
  } catch {
    return null;
  }
}

function writeStoredActor(actor: ActorContext | null): void {
  try {
    if (actor) {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(actor));
    } else {
      sessionStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // Private-browsing/storage-blocked contexts: fall back to in-memory-only.
  }
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [actor, setActorState] = useState<ActorContext | null>(readStoredActor);

  const value = useMemo<AuthContextValue>(
    () => ({
      actor,
      setActor: (role, actorId) => {
        const next = { role, actorId };
        writeStoredActor(next);
        setActorState(next);
      },
      clearActor: () => {
        writeStoredActor(null);
        setActorState(null);
      },
    }),
    [actor],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
