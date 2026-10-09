// Route /runs · the Run centre (P1 spec 5.1).  The page reads the workbench state kept by the
// shell in the root layout; it is rendered on the server for this URL.
import RunsView from "./RunsView";

export default function Page() {
  return <RunsView />;
}
