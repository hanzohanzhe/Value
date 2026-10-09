"use client";

import { apiFetch, apiUrl } from "../../lib/api.ts";
import { useEffect, useState } from "react";
import { useT } from "../../i18n/LocaleProvider";
import "./network-overlay-selector.css";

type Overlay = {
  pack_id: string; name: string; years: number[];
  source_manifest_sha256: string; status: "available" | "invalid"; reason: string | null;
};

export default function NetworkOverlaySelector({ value, onChange, onOpenData }: {
  value: string; onChange: (id: string) => void; onOpenData: () => void;
}) {
  const t = useT();
  const [attempt, setAttempt] = useState(0);
  const requestKey = JSON.stringify([attempt]);
  const [result, setResult] = useState<{ key: string; overlays: Overlay[]; error: string } | null>(null);
  const loading = result?.key !== requestKey;
  const overlays = loading ? [] : result.overlays;
  const error = loading ? "" : result.error;
  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const response = await apiFetch(apiUrl("data-workbench/v1/overlays"), { signal: controller.signal });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error?.message ?? data.error ?? `HTTP ${response.status}`);
        if (data.schema_version !== "value.network-overlays/v1" || !Array.isArray(data.overlays)) {
          throw new Error("value.network-overlays/v1");
        }
        if (!controller.signal.aborted) setResult({ key: requestKey, overlays: data.overlays, error: "" });
      } catch (cause) {
        if (!controller.signal.aborted) setResult({ key: requestKey, overlays: [], error: cause instanceof Error ? cause.message : String(cause) });
      }
    })();
    return () => controller.abort();
  }, [requestKey]);
  const selected = overlays.find((item) => item.pack_id === value);
  return <div className="network-overlay-selection">
    <label><span>{t("studies.overlay.label")}</span>
      <select aria-label={t("studies.overlay.select")} value={value} disabled={loading || Boolean(error)} onChange={(event) => onChange(event.target.value)}>
        <option value="">{t("studies.overlay.choose")}</option>
        {value && !selected && <option value={value}>{`${value} · ${loading ? t("studies.overlay.loading") : t("studies.overlay.unavailable")}`}</option>}
        {overlays.map((item) => <option key={item.pack_id} value={item.pack_id} disabled={item.status !== "available"}>{`${item.name} · ${item.pack_id}${item.status === "invalid" ? ` · ${t("studies.overlay.invalid")}` : ""}`}</option>)}
      </select>
      <small>{selected ? `${t("studies.overlay.years", { years: selected.years.join(", ") || t("studies.overlay.notDeclared") })} ${selected.reason ?? t("studies.overlay.recorded")}` : t("studies.overlay.hint")}</small>
    </label>
    {error && <p role="alert">{t("studies.overlay.failed", { error })} <button type="button" className="secondary" onClick={() => setAttempt((current) => current + 1)}>{t("studies.overlay.retry")}</button></p>}
    <button type="button" className="secondary" onClick={onOpenData}>{t("studies.overlay.openData")}</button>
  </div>;
}
