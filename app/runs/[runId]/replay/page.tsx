// Route /runs/[runId]/replay · market replay (?year=&period=&stage=) (P1 spec 5.1).  The page reads the workbench state kept by the
// shell in the root layout; it is rendered on the server for this URL.
import ReplayView from "./ReplayView";

export default function Page() {
  return <ReplayView />;
}
