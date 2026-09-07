import type { ReactNode } from "react";

import { useAuth } from "../context/AuthContext";
import type { Role } from "../types/enums";

interface RoleGuardProps {
  allow: Role[];
  children: ReactNode;
}

export function RoleGuard({ allow, children }: RoleGuardProps) {
  const { actor } = useAuth();

  if (!actor || !allow.includes(actor.role)) {
    return (
      <div
        role="alert"
        className="rounded-md border border-slate-300 bg-white p-6 text-slate-700"
      >
        <p className="font-semibold text-navy-950">Access denied</p>
        <p className="mt-1 text-sm">
          This page requires one of: {allow.join(", ")}.
        </p>
      </div>
    );
  }

  return <>{children}</>;
}
