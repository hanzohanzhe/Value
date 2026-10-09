// Test-only wrappers (P1 W5): views translated in W5 rendered inside the
// interface-language provider, so a render test can read them in Chinese.
import { LocaleProvider } from "../../../app/i18n/LocaleProvider";
import type { Locale } from "../../../app/i18n/index.ts";
import TraceCoverageNotice from "../../../app/features/market/TraceCoverageNotice";
import NetworkZoneMap from "../../../app/features/network/NetworkZoneMap";
import { BoundaryUseTable } from "../../../app/features/network/NetworkRedispatchView";
import Pager from "../../../app/features/shared/Pager";
import RunErrorBox from "../../../app/features/runs/RunErrorBox";
import { ReadMePanel } from "../../../app/features/workspace/ReadMePanel";
import OpenFromLauncher from "../../../app/features/shared/OpenFromLauncher";
import DomainReadinessPanel from "../../../app/features/runs/DomainReadinessPanel";
import type { DomainReadiness } from "../../../app/features/runs/types";

const noop = () => undefined;

export function W5ViewsIn({ locale }: { locale: Locale }) {
  return <LocaleProvider initialLocale={locale}>
    <TraceCoverageNotice traceLevel="summary" bidReplayAvailable={false} onCreateFullReplayRevision={noop} />
    <NetworkZoneMap zones={[{ zone_id: "Z1", demand_mwh: 10, net_position_mwh: -2, load_shedding_mwh: 0 }]} boundaries={[{ boundary_id: "B6", transfer_mwh: -1.5, utilisation_fraction: 0.4 }]} />
    <BoundaryUseTable rows={[{ boundary_id: "B6", transfer_mwh: 10, forward_capacity_mwh: 5, reverse_capacity_mwh: null, utilisation_fraction: 0.5, boundary_shadow_value_gbp_per_mwh: null }]} />
    <Pager page={{ total: 30, limit: 10, offset: 10, items: [] }} onPage={noop} />
    <OpenFromLauncher />
  </LocaleProvider>;
}

export function RunErrorIn({ locale, code, error }: { locale: Locale; code: string; error: string }) {
  return <LocaleProvider initialLocale={locale}><RunErrorBox run={{ error_code: code, error }} /></LocaleProvider>;
}

export function ReadMeIn({ locale }: { locale: Locale }) {
  return <LocaleProvider initialLocale={locale}><ReadMePanel open={false} onClose={noop} /></LocaleProvider>;
}

export function DomainReadinessIn({ locale, readiness }: { locale: Locale; readiness: DomainReadiness }) {
  return <LocaleProvider initialLocale={locale}><DomainReadinessPanel readiness={readiness} onNavigate={noop} runBlocked /></LocaleProvider>;
}
