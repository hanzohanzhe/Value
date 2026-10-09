// Route /runs/[runId]/systems · optional-domain results (P1 spec 5.1).  The page reads the workbench state kept by the
// shell in the root layout; it is rendered on the server for this URL.
import SystemsView from "./SystemsView";

export default function Page() {
  return <SystemsView />;
}
