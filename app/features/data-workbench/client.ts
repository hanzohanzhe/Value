import { apiUrl } from "../shared/api";
import type {
  CandidateReview,
  CandidateSummary,
  DataJob,
  DataSourceDefinition,
  InstalledBundle,
  SignedBundleReceipt,
  SourceRevision,
  ValidationReport,
} from "./types";

const jobStatuses = new Set([
  "queued", "running", "cancel_requested", "cancelled", "failed", "completed",
]);

export class DataWorkbenchClient {
  readonly base = apiUrl("data-workbench/v1");

  private async request<T>(path: string, init?: RequestInit, schema?: string): Promise<T> {
    const response = await fetch(`${this.base}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
    const payload = await response.json() as Record<string, unknown>;
    if (!response.ok) {
      const message = payload.error_code
        ? `${String(payload.error_code)}: ${String(payload.error ?? "request failed")}`
        : String(payload.error ?? "Data Workbench request failed");
      throw new Error(message);
    }
    if (schema && payload.schema_version !== schema) {
      throw new Error(`Unexpected Data Workbench schema: expected ${schema}`);
    }
    return payload as T;
  }

  private async jobResponse(path: string, init?: RequestInit): Promise<{ job: DataJob }> {
    const payload = await this.request<{ job: DataJob }>(path, init);
    if (!payload.job || payload.job.schema_version !== "value.data-job/v1") {
      throw new Error("Unexpected Data Workbench schema: expected value.data-job/v1");
    }
    if (!jobStatuses.has(payload.job.status)) {
      throw new Error(`Unknown Data Workbench job status: ${payload.job.status}`);
    }
    return payload;
  }

  sources() {
    return this.request<{ schema_version: string; sources: DataSourceDefinition[] }>(
      "/sources", undefined, "value.data-sources/v1",
    );
  }

  revisions() {
    return this.request<{ schema_version: string; revisions: SourceRevision[] }>(
      "/revisions", undefined, "value.data-revisions/v1",
    );
  }

  candidates() {
    return this.request<{ schema_version: string; candidates: CandidateSummary[] }>(
      "/candidates", undefined, "value.data-candidates/v1",
    );
  }

  bundles() {
    return this.request<{ schema_version: string; bundles: InstalledBundle[] }>(
      "/bundles", undefined, "value.data-installed-bundles/v1",
    );
  }

  job(jobId: string) {
    return this.jobResponse(`/jobs/${encodeURIComponent(jobId)}`);
  }

  startJob(operation: "discover" | "fetch" | "compile" | "validate", declaredInput: Record<string, unknown>) {
    return this.jobResponse("/jobs", {
      method: "POST",
      body: JSON.stringify({
        schema_version: "value.data-job-request/v1",
        operation,
        declared_input: declaredInput,
        start: true,
      }),
    });
  }

  cancelJob(jobId: string) {
    return this.jobResponse(`/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST",
      body: "{}",
    });
  }

  validate(candidateId: string) {
    return this.request<ValidationReport>(
      `/candidates/${encodeURIComponent(candidateId)}/validate`,
      {
        method: "POST",
        body: JSON.stringify({ schema_version: "value.data-validation-request/v1" }),
      },
      "value.data-validation-report/v1",
    );
  }

  review(candidateId: string) {
    return this.request<CandidateReview>(
      `/reports/${encodeURIComponent(candidateId)}`,
      undefined,
      "value.data-candidate-review/v1",
    );
  }

  promote(candidateId: string, version: string, reviewer: string, accepted_waivers: string[]) {
    return this.request<SignedBundleReceipt>(
      `/candidates/${encodeURIComponent(candidateId)}/promote`,
      {
        method: "POST",
        body: JSON.stringify({
          schema_version: "value.data-promotion-request/v1",
          candidate_id: candidateId,
          version,
          reviewer,
          accepted_waivers,
        }),
      },
      "value.data-signed-bundle-receipt/v1",
    );
  }
}
