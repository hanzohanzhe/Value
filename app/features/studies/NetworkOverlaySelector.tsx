"use client";

import { apiUrl } from "../shared/api";
import { useEffect, useState } from "react";
import "./network-overlay-selector.css";

type Overlay = {
  pack_id: string; name: string; years: number[];
  source_manifest_sha256: string; status: "available" | "invalid"; reason: string | null;
};

export default function NetworkOverlaySelector({ value, onChange, onOpenData }: {
  value: string; onChange: (id: string) => void; onOpenData: () => void;
}) {
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
        const response = await fetch(apiUrl("data-workbench/v1/overlays"), { signal: controller.signal });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error?.message ?? data.error ?? "Cannot load network overlays.");
        if (data.schema_version !== "value.network-overlays/v1" || !Array.isArray(data.overlays)) {
          throw new Error("Unexpected network overlay response.");
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
    <label><span>Network overlay</span>
      <select aria-label="Study network overlay" value={value} disabled={loading || Boolean(error)} onChange={(event) => onChange(event.target.value)}>
        <option value="">Select an installed network overlay</option>
        {value && !selected && <option value={value}>{value} · {loading ? "loading" : "unavailable"}</option>}
        {overlays.map((item) => <option key={item.pack_id} value={item.pack_id} disabled={item.status !== "available"}>{item.name} · {item.pack_id}{item.status === "invalid" ? " · invalid" : ""}</option>)}
      </select>
      <small>{selected ? `Available years: ${selected.years.join(", ") || "not declared"}. ${selected.reason ?? "The saved Study records this separate network product."}` : "Create and validate an independent overlay in the data workbench, then select its installed ID here."}</small>
    </label>
    {error && <p role="alert">{error} <button type="button" className="secondary" onClick={() => setAttempt((current) => current + 1)}>Retry</button></p>}
    <button type="button" className="secondary" onClick={onOpenData}>Open network data workbench</button>
  </div>;
}
