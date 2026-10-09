// Route / (Home) and the forwarder for old links (P1 spec 5.1, W3).
//
// Until W3 the whole workbench was this one client component with a ?view=
// parameter; it now lives in features/shell (state and shell) and in one route
// per page.  An old /?view=<id>&study=&run=… link is redirected on the server
// to its route with the other parameters kept, so the page renders directly
// (no Home first, F1-09).
import { redirect } from "next/navigation";
import { legacyRedirect, searchFromRecord } from "./features/shell/routes.ts";
import HomeView from "./HomeView";

export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const target = legacyRedirect(searchFromRecord(await searchParams));
  if (target) redirect(target);
  return <HomeView />;
}
