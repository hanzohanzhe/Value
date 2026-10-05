// Pure view logic of Market replay (P0-9 S3/S4; spec 3). No React here, so
// node --test checks it against the generated UI contract fixtures.
import { formatPrice, type FormattedPrice } from "../shared/format.ts";
import type { DispatchBucket, DispatchTimeline } from "./marketTypes.ts";

/** Price of one bucket, labelled by the ledger's price basis (Q6). A multi-period bucket is a demand-weighted mean. */
export function bucketPrice(bucket: Pick<DispatchBucket, "price_gbp_per_mwh" | "period_count">, timeline: Pick<DispatchTimeline, "price_basis">): FormattedPrice {
  return formatPrice(bucket.price_gbp_per_mwh, timeline.price_basis, { aggregated: bucket.period_count > 1 });
}
