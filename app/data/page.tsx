// Route /data · data packs, mappings and the Data Workbench (P1 spec 5.1).  The page reads the workbench state kept by the
// shell in the root layout; it is rendered on the server for this URL.
import DataView from "./DataView";

export default function Page() {
  return <DataView />;
}
