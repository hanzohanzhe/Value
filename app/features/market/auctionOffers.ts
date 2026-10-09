// Merit-order table, Accepted column (spec 3.4; four-role M-D1 UI). Pure logic.
// The backend fills accepted_mwh per offer: exactly from the clearing outcome
// for a single-offer asset, or from the storage offer ledger (storage_orders,
// acceptance_granularity "storage_offer_ledger") for each tranche of a
// battery. Only when neither exists does the table fall back to the asset
// total; the frontend never splits an asset total across offers.
import type { AuctionOffer } from "./marketTypes.ts";
import { tr } from "../../i18n/index.ts";

export const STORAGE_LEDGER_GRANULARITY = "storage_offer_ledger";

export type AcceptedCell = {
  /** MWh to print, or null for "Not separately recorded". */
  mwh: number | null;
  /** " (asset total)" when only the asset's total is recorded. */
  suffix: string;
  /** Hover text: the storage ledger's status and reason for a storage offer. */
  title?: string;
};

function words(value: string | null | undefined): string {
  return String(value ?? "").replaceAll("_", " ");
}

export function acceptedCell(offer: AuctionOffer): AcceptedCell {
  if (offer.accepted_mwh != null) {
    if (offer.acceptance_granularity === STORAGE_LEDGER_GRANULARITY && offer.offer_status) {
      const title = offer.offer_reason_code
        ? tr("auction.storageLedgerReason", { status: words(offer.offer_status), reason: words(offer.offer_reason_code) })
        : tr("auction.storageLedger", { status: words(offer.offer_status) });
      return { mwh: offer.accepted_mwh, suffix: "", title };
    }
    return { mwh: offer.accepted_mwh, suffix: "" };
  }
  if (offer.asset_accepted_mwh != null) return { mwh: offer.asset_accepted_mwh, suffix: tr("auction.assetTotal") };
  return { mwh: null, suffix: "" };
}

/** The note under the table when any storage offer carries its own ledger acceptance. */
export function storageLedgerNote(offers: readonly AuctionOffer[]): string | null {
  if (!offers.some((offer) => offer.acceptance_granularity === STORAGE_LEDGER_GRANULARITY)) return null;
  return tr("auction.storageNote");
}
