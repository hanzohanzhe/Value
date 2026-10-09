// Route /runs/[runId] · one Run's annual results, ?year= (P1 spec 5.1, 6.5).  The page reads the workbench
// state kept by the shell in the root layout; it is rendered on the server for this URL.
import RunResultsView from "./RunResultsView";

export default function Page() {
  return <RunResultsView />;
}
