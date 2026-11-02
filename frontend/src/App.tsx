import { useEffect } from "react";
import { Dashboard } from "./components/Dashboard";
import { EditorScreen } from "./components/EditorScreen";
import { ConfirmDialog } from "./components/ui";
import { useRoute } from "./state/navigation";

export function App() {
  const { route, navigate, pendingLeave, saveAndLeave, discardAndLeave, stay } = useRoute();

  useEffect(() => {
    document.title = route.page === "dashboard" ? "MCDA Studio" : "MCDA Studio · editor";
  }, [route]);

  return (
    <>
      {route.page === "dashboard" ? (
        <>
          <header className="appbar">
            <span className="brand">
              <svg className="brand-mark" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M4 19V11M10 19V5M16 19v-6M22 19H2" />
              </svg>
              MCDA Studio
            </span>
            <span className="spacer" />
            <span className="appbar-note">Runs locally · your files stay on this computer</span>
          </header>
          <Dashboard onOpen={(id) => navigate({ page: "editor", id })} />
        </>
      ) : (
        <EditorScreen
          key={route.id}
          projectId={route.id}
          onClose={() => navigate({ page: "dashboard" })}
          onOpenOther={(id) => navigate({ page: "editor", id })}
        />
      )}
      {pendingLeave && (
        <ConfirmDialog
          title="Unsaved changes"
          message={
            <>
              <strong>{pendingLeave.title}</strong> has changes that have not been saved.
            </>
          }
          confirmLabel="Save and leave"
          cancelLabel="Keep editing"
          onCancel={stay}
          onConfirm={() => void saveAndLeave()}
          extra={
            <button type="button" className="danger" onClick={discardAndLeave}>
              Discard changes
            </button>
          }
        />
      )}
    </>
  );
}
