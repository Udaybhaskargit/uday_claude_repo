import { Navigate, Route, Routes } from "react-router-dom";

import { RoleGuard } from "./components/RoleGuard";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { AdminDashboardPage } from "./pages/AdminDashboardPage";
import { CustomerFnolPage } from "./pages/CustomerFnolPage";
import { CustomerTrackerPage } from "./pages/CustomerTrackerPage";
import { DocumentQueuePage } from "./pages/DocumentQueuePage";
import { FraudQueuePage } from "./pages/FraudQueuePage";
import { RoleSelectPage } from "./pages/RoleSelectPage";
import { WorkbenchPage } from "./pages/WorkbenchPage";
import { Role } from "./types/enums";

function AppShell() {
  const { actor } = useAuth();

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="border-b-4 border-amber-500 bg-navy-950 px-6 py-4">
        <span className="font-serif text-lg tracking-wide text-slate-100">
          Claim<span className="text-amber-400">Flow</span>
        </span>
        {actor && (
          <span className="ml-4 font-mono text-xs text-slate-300">
            {actor.role} · {actor.actorId}
          </span>
        )}
      </header>
      <main>
        <Routes>
          <Route path="/" element={<RoleSelectPage />} />
          <Route
            path="/claims/new"
            element={
              <RoleGuard allow={[Role.CUSTOMER]}>
                <CustomerFnolPage />
              </RoleGuard>
            }
          />
          <Route
            path="/claims/:claimId"
            element={
              <RoleGuard allow={[Role.CUSTOMER]}>
                <CustomerTrackerPage />
              </RoleGuard>
            }
          />
          <Route
            path="/documents/pending"
            element={
              <RoleGuard allow={[Role.ASSESSOR]}>
                <DocumentQueuePage />
              </RoleGuard>
            }
          />
          <Route
            path="/fraud-alerts"
            element={
              <RoleGuard allow={[Role.ASSESSOR, Role.ADMIN]}>
                <FraudQueuePage />
              </RoleGuard>
            }
          />
          <Route
            path="/workbench/:claimId"
            element={
              <RoleGuard allow={[Role.ASSESSOR]}>
                <WorkbenchPage />
              </RoleGuard>
            }
          />
          <Route
            path="/admin"
            element={
              <RoleGuard allow={[Role.ADMIN]}>
                <AdminDashboardPage />
              </RoleGuard>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}
