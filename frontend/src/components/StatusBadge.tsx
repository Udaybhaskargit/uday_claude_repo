import { ClaimStatus } from "../types/enums";

const STYLES: Record<ClaimStatus, string> = {
  [ClaimStatus.INTAKE]: "bg-slate-100 text-slate-700",
  [ClaimStatus.DOCS_PENDING]: "bg-amber-500/20 text-amber-500",
  [ClaimStatus.FRAUD_SCREENING]: "bg-amber-500/20 text-amber-500",
  [ClaimStatus.ASSESSMENT]: "bg-slate-100 text-slate-700",
  [ClaimStatus.AUTO_APPROVED]: "bg-green-100 text-green-700",
  [ClaimStatus.MANUAL_REVIEW]: "bg-amber-500/30 text-amber-500",
  [ClaimStatus.REJECTED]: "bg-red-100 text-red-700",
  [ClaimStatus.SETTLED]: "bg-green-100 text-green-700",
  [ClaimStatus.REOPENED]: "bg-slate-100 text-slate-700",
  [ClaimStatus.PROCESSING_FAILED]: "bg-red-100 text-red-700",
};

export function StatusBadge({ status }: { status: ClaimStatus }) {
  return (
    <span
      className={`inline-block rounded-full px-3 py-1 text-xs font-medium ${STYLES[status]}`}
    >
      {status.replaceAll("_", " ")}
    </span>
  );
}
