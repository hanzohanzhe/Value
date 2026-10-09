// Route /studies/[studyId] · the composer opened on one saved Study (P1 spec 5.1).  The page reads the workbench state kept by the
// shell in the root layout; it is rendered on the server for this URL.
import StudiesView from "../StudiesView";

export default function Page() {
  return <StudiesView />;
}
