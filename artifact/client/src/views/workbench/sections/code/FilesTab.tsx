// The Files tab (absorption plan, steps 8-9): the ruled
// SPLIT view — tree left, peek right on desktop; on
// phone the tree is a drill-in screen and the peek opens
// over it with a back affordance. The editor mounts from
// here as the full-screen takeover and unmounts back to
// the refreshed peek.

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@workhorse/kit/components/Button";
import { api } from "../../lib/api";
import type { RepoFilesPayload, RepoPeek } from "../../lib/api-types-code";
import { useIsPhone } from "../../lib/responsive";
import { ErrorWell, SkeletonWell } from "../shared";
import { useCheckout } from "./checkoutContext";
import { FileTree } from "./FileTree";
import { PeekPane } from "./PeekPane";
import { RepoEditor } from "./RepoEditor";

export function FilesTab({ projectId }: { projectId: string }) {
  const checkout = useCheckout();
  const isPhone = useIsPhone();
  const [selected, setSelected] = useState<string | null>(null);
  const [editing, setEditing] = useState<RepoPeek | null>(null);
  // Bumped when an editor session saved: the peek remounts
  // (fresh query, no held reveal state) onto the new bytes.
  const [peekSession, setPeekSession] = useState(0);

  // The base lists only: the tree itself loads lazily,
  // one directory at a time (FileTree owns those queries).
  const query = useQuery({
    queryKey: ["code-files", projectId, checkout],
    queryFn: () => api.getCodeFiles({ projectId, checkout }),
  });
  const payload = query.data?.payload as unknown as RepoFilesPayload | null;

  if (query.isPending) return <SkeletonWell label="the file tree" />;
  if (query.isError || !payload) {
    return (
      <ErrorWell
        section="Files"
        message={query.data?.error ?? "the file tree could not be loaded."}
      />
    );
  }

  const tree = (
    <div
      style={{
        border: "1px solid var(--wb-border-default)",
        borderRadius: "var(--wb-radius-md)",
        background: "var(--wb-surface-2)",
      }}
    >
      <FileTree projectId={projectId} selected={selected} onSelect={setSelected} />
    </div>
  );

  const peek =
    selected != null ? (
      <div
        style={{
          border: "1px solid var(--wb-border-default)",
          borderRadius: "var(--wb-radius-md)",
          background: "var(--wb-surface-2)",
          minWidth: 0,
        }}
      >
        <PeekPane
          key={`${projectId}:${selected}:${peekSession}`}
          projectId={projectId}
          path={selected}
          onEdit={setEditing}
        />
      </div>
    ) : (
      <div
        style={{
          border: "1px dashed var(--wb-border-default)",
          borderRadius: "var(--wb-radius-md)",
          background: "var(--wb-surface-sunken)",
          padding: "var(--wb-panel-padding)",
          color: "var(--wb-content-secondary)",
        }}
      >
        Select a file in the tree.
      </div>
    );

  return (
    <div data-anchor="repos/files">
      {isPhone ? (
        selected == null ? (
          tree
        ) : (
          <>
            <div style={{ marginBottom: "var(--wb-space-12)" }}>
              <Button variant="ghost" onClick={() => setSelected(null)}>
                ← Back to files
              </Button>
            </div>
            {peek}
          </>
        )
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(260px, 1fr) 2fr",
            gap: "var(--wb-space-16)",
            alignItems: "start",
          }}
        >
          {tree}
          {peek}
        </div>
      )}
      {editing ? (
        <RepoEditor
          projectId={projectId}
          initialPeek={editing}
          onClose={(saved) => {
            setEditing(null);
            if (saved) setPeekSession((n) => n + 1);
          }}
        />
      ) : null}
    </div>
  );
}
