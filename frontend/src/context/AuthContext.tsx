// Stub "login": lets the user pick a role + actor id, since E8-S1's backend
// auth is a header-based stub with no real credential check (BRD sec 7.1).

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

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [actor, setActorState] = useState<ActorContext | null>(null);

  const value = useMemo<AuthContextValue>(
    () => ({
      actor,
      setActor: (role, actorId) => setActorState({ role, actorId }),
      clearActor: () => setActorState(null),
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
