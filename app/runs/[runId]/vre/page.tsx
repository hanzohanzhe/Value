// Route /runs/[runId]/vre · VRE and curtailment (P1 spec 5.1).  The page reads the workbench state kept by the
// shell in the root layout; it is rendered on the server for this URL.
import VreView from "./VreView";

export default function Page() {
  return <VreView />;
}
