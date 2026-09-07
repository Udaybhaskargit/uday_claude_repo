import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { Role } from "../types/enums";

const ROLE_HOME: Record<Role, string> = {
  [Role.CUSTOMER]: "/claims/new",
  [Role.ASSESSOR]: "/documents/pending",
  [Role.ADMIN]: "/admin",
};

export function RoleSelectPage() {
  const { setActor } = useAuth();
  const navigate = useNavigate();
  const [role, setRole] = useState<Role>(Role.CUSTOMER);
  const [actorId, setActorId] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!actorId.trim()) {
      return;
    }
    setActor(role, actorId.trim());
    navigate(ROLE_HOME[role]);
  }

  return (
    <div className="mx-auto max-w-sm p-8">
      <h1 className="text-xl font-semibold text-navy-950">ClaimFlow</h1>
      <p className="mt-1 text-sm text-slate-700">
        Select a role to continue (stub auth per E8-S1 -- not a real login).
      </p>
      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <label className="block text-sm font-medium text-navy-950">
          Role
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as Role)}
            className="mt-1 block w-full rounded-md border border-slate-300 p-2"
          >
            {Object.values(Role).map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm font-medium text-navy-950">
          Actor ID
          <input
            value={actorId}
            onChange={(e) => setActorId(e.target.value)}
            placeholder="e.g. cust-1001"
            className="mt-1 block w-full rounded-md border border-slate-300 p-2"
          />
        </label>
        <button
          type="submit"
          className="w-full rounded-md bg-navy-950 px-4 py-2 text-sm font-medium text-white hover:bg-navy-900"
        >
          Continue
        </button>
      </form>
    </div>
  );
}
