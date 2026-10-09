"use client";

// Spec 4: the interface and the local service were built for different
// contracts (for example a UI process left running across an upgrade).
// Nothing else is shown: requests could be misread.
import { useT } from "../../i18n/LocaleProvider";
import { FRONTEND_CONTRACT_VERSION } from "../../lib/api.ts";
import { Callout } from "../../ui/Callout";
import "./shell.css";

export default function ContractMismatch({ serviceContract }: { serviceContract: unknown }) {
  const t = useT();
  const actual = typeof serviceContract === "number" || typeof serviceContract === "string" ? String(serviceContract) : t("contract.mismatch.notReported");
  return <main className="contract-mismatch">
    <Callout tone="danger" title={t("contract.mismatch.title")} action={{ label: t("contract.mismatch.reload"), onClick: () => window.location.reload() }}>
      <p>{t("contract.mismatch.detail", { expected: FRONTEND_CONTRACT_VERSION, actual })}</p>
    </Callout>
  </main>;
}
