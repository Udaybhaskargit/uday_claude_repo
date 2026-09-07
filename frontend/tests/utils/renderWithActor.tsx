// Shared test helper: renders `children` inside a real AuthProvider with the
// actor already set, so page components under test can call `useAuth()`
// exactly as they do in the app. Setting the actor via an effect (rather
// than reaching into AuthContext internals, which aren't exported) means the
// tree re-renders once actor flips from null -> set, matching how routing
// after RoleSelectPage really behaves.

import { useEffect, type ReactNode } from "react";

import { AuthProvider, useAuth } from "../../src/context/AuthContext";
import type { Role } from "../../src/types/enums";

function ActorSetter({ role, actorId }: { role: Role; actorId: string }) {
  const { setActor } = useAuth();
  // Deliberately run once on mount only: AuthProvider's `value` (and so
  // `setActor`'s identity) is recreated every time `actor` changes, so
  // including `setActor` here would re-fire this effect after every call,
  // looping forever (setActor always creates a brand-new state object, so
  // React never bails the update out via Object.is).
  useEffect(() => {
    setActor(role, actorId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return null;
}

export function renderWithActor(
  role: Role,
  actorId: string,
  children: ReactNode,
): ReactNode {
  return (
    <AuthProvider>
      <ActorSetter role={role} actorId={actorId} />
      {children}
    </AuthProvider>
  );
}
