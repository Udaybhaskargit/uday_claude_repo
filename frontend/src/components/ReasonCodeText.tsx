import { ReasonCode } from "../types/enums";

const COPY: Record<ReasonCode, string> = {
  [ReasonCode.POLICY_INACTIVE]: "The policy was not active on the incident date.",
  [ReasonCode.ZERO_PAYABLE_AMOUNT]: "The assessed payable amount was zero.",
  [ReasonCode.FRAUD_FLAG]: "This claim was flagged by fraud screening for manual review.",
  [ReasonCode.AUTO_APPROVED_LOW_RISK]: "Automatically approved as low risk.",
  [ReasonCode.HIGH_VALUE_REVIEW]: "Sent for manual review due to the claim's high value.",
  [ReasonCode.DOCS_INCOMPLETE]: "Required documents are still outstanding.",
};

export function ReasonCodeText({ code }: { code: ReasonCode }) {
  return <span>{COPY[code]}</span>;
}
