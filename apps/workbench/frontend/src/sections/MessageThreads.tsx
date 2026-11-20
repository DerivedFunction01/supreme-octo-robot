import { useState } from "react";
import { ArmConfirm } from "@kit/components/ArmConfirm";
import { Button } from "@kit/components/Button";
import { Sheet } from "@kit/components/Sheet";
import { useAdapter, useStoreVersion } from "../lib/store";
import type { MessageThread } from "../lib/types";
import {
  ActionRow,
  Group,
  GroupLabel,
  Lab,
  Row,
  Sub,
} from "../components/ui";

// Message compose + thread verbs (W10) — mounted under
// the Inbox (the Inbox section itself is the row-fix
// lane's file; composition happens in App.tsx). The
// message store's own surface: threads with their state,
// compose as draft-or-send-now, reply, edit your own
// message bodies, and the send / done / archive verbs —
// every control wired to the seam (POST /api/messages,
// POST /api/messages/{id}/{verb} at the shell).

const STATE_LABEL: Record<MessageThread["state"], string> = {
  draft: "Draft",
  sent: "Sent",
  acknowledged: "Acknowledged",
  done: "Done",
  archived: "Archived",
};

const inputStyle: React.CSSProperties = {
  backgroundColor: "var(--wb-surface-sunken)",
  color: "var(--wb-content-primary)",
  borderRadius: 9,
  padding: "6px 10px",
  fontSize: 13.5,
};

function ThreadView({ thread }: { thread: MessageThread }) {
  const a = useAdapter();
  const [reply, setReply] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editBody, setEditBody] = useState("");

  return (
    <div className="mt-3">
      {thread.anchorText ? (
        <p className="mb-3 text-[13px] [overflow-wrap:anywhere]" style={{ color: "var(--wb-content-secondary)" }}>
          Anchored to: "{thread.anchorText}"
        </p>
      ) : null}
      <div className="flex flex-col gap-2.5">
        {thread.messages.map((m) => (
          <div
            key={m.id}
            className="p-[10px_14px]"
            style={{
              backgroundColor: "var(--wb-surface-2)",
              border: "1px solid var(--wb-border-default)",
              borderRadius: "var(--wb-radius-md)",
            }}
          >
            <div className="mb-1 flex items-center gap-2 text-xs" style={{ color: "var(--wb-content-secondary)" }}>
              <span className="font-bold">{m.author}</span>
              <span>{m.when}</span>
              {m.author === "owner" && thread.state !== "archived" ? (
                <button
                  type="button"
                  className="ml-auto font-semibold"
                  style={{ color: "var(--wb-accent)" }}
                  onClick={() => {
                    setEditingId(m.id);
                    setEditBody(m.body);
                  }}
                >
                  Edit
                </button>
              ) : null}
            </div>
            {editingId === m.id ? (
              <div>
                <textarea
                  aria-label="Edit message"
                  value={editBody}
                  onChange={(e) => setEditBody(e.target.value)}
                  rows={3}
                  className="w-full"
                  style={{ ...inputStyle, resize: "vertical" }}
                />
                <div className="mt-2 flex gap-2">
                  <Button
                    onClick={() => {
                      void a.editThreadMessage(thread.id, m.id, editBody);
                      setEditingId(null);
                    }}
                    disabled={!editBody.trim()}
                  >
                    Save edit
                  </Button>
                  <Button variant="secondary" onClick={() => setEditingId(null)}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <p className="m-0 text-[13.5px] leading-[1.55] whitespace-pre-wrap [overflow-wrap:anywhere]">{m.body}</p>
            )}
          </div>
        ))}
      </div>

      {thread.state !== "archived" && thread.state !== "done" ? (
        <div className="mt-3 flex items-start gap-2">
          <textarea
            aria-label="Reply"
            value={reply}
            onChange={(e) => setReply(e.target.value)}
            placeholder="Reply…"
            rows={2}
            className="min-w-0 flex-1"
            style={{ ...inputStyle, resize: "vertical" }}
          />
          <Button
            onClick={() => {
              void a.replyThread(thread.id, reply);
              setReply("");
            }}
            disabled={!reply.trim()}
          >
            Reply
          </Button>
        </div>
      ) : null}

      <div className="mt-3.5">
        <Group>
          {thread.state === "draft" ? (
            <ActionRow label="Send now" onClick={() => void a.setThreadState(thread.id, "sent")} />
          ) : null}
          {thread.state === "sent" || thread.state === "acknowledged" ? (
            <ActionRow label="Mark done" onClick={() => void a.setThreadState(thread.id, "done")} />
          ) : null}
          {thread.state !== "archived" ? (
            <Row last>
              <Lab>Archive thread</Lab>
              <span className="ml-auto">
                <ArmConfirm
                  label="Archive"
                  confirmLabel="Confirm archive"
                  statement={`Archive "${thread.title}" — it leaves the active threads; the messages stay in the store.`}
                  variant="danger"
                  disarmKey={`${thread.id}|archive|${thread.messages.length}`}
                  onConfirm={() => void a.setThreadState(thread.id, "archived")}
                />
              </span>
            </Row>
          ) : (
            <Row last>
              <Lab>Archived</Lab>
            </Row>
          )}
        </Group>
      </div>
    </div>
  );
}

export function MessageThreads() {
  useStoreVersion();
  const a = useAdapter();
  const threads = a.messageThreads();
  const projects = a.projects();
  const [openId, setOpenId] = useState<string | null>(threads[0]?.id ?? null);
  const [composeOpen, setComposeOpen] = useState(false);
  const [project, setProject] = useState(projects[0]?.slug ?? "");
  const [body, setBody] = useState("");
  const [anchor, setAnchor] = useState("");
  const open = threads.find((t) => t.id === openId) ?? threads[0];

  return (
    <div className="px-[26px] pb-[22px]">
      <GroupLabel>Message threads · {threads.length}</GroupLabel>
      <Group>
        <ActionRow
          label="Compose message…"
          last={threads.length === 0}
          onClick={() => setComposeOpen(true)}
        />
        {threads.map((t, i) => (
          <Row
            key={t.id}
            last={i === threads.length - 1}
            selected={open?.id === t.id}
            onClick={() => setOpenId(t.id)}
          >
            <span className="min-w-0">
              <span className="block truncate text-[14.5px] font-medium">{t.title}</span>
              <Sub>
                {t.project || "no project"} · {t.messages.length} message{t.messages.length === 1 ? "" : "s"}
              </Sub>
            </span>
            <span
              className="ml-auto inline-flex shrink-0 rounded-full px-2.5 py-[2.5px] text-xs font-semibold"
              style={{
                backgroundColor: "var(--wb-surface-sunken)",
                color: "var(--wb-content-secondary)",
              }}
            >
              {STATE_LABEL[t.state]}
            </span>
          </Row>
        ))}
      </Group>

      {open ? <ThreadView key={open.id} thread={open} /> : null}

      <Sheet
        open={composeOpen}
        title="Compose message"
        onClose={() => setComposeOpen(false)}
        footer={
          <>
            <Button
              variant="secondary"
              disabled={!body.trim()}
              onClick={() => {
                void a.composeThread({ project, body, anchorText: anchor, sendNow: false });
                setComposeOpen(false);
                setBody("");
                setAnchor("");
              }}
            >
              Save draft
            </Button>
            <Button
              disabled={!body.trim()}
              onClick={() => {
                void a
                  .composeThread({ project, body, anchorText: anchor, sendNow: true })
                  .then((t) => setOpenId(t.id));
                setComposeOpen(false);
                setBody("");
                setAnchor("");
              }}
            >
              Send now
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] font-semibold">Project</span>
            <select
              aria-label="Project"
              value={project}
              onChange={(e) => setProject(e.target.value)}
              style={inputStyle}
            >
              <option value="">No project</option>
              {projects.map((p) => (
                <option key={p.slug} value={p.slug}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] font-semibold">Anchor text (optional)</span>
            <input
              aria-label="Anchor text"
              value={anchor}
              onChange={(e) => setAnchor(e.target.value)}
              placeholder="The passage this message hangs on"
              style={inputStyle}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] font-semibold">Message</span>
            <textarea
              aria-label="Message body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={5}
              style={{ ...inputStyle, resize: "vertical" }}
            />
          </label>
        </div>
      </Sheet>
    </div>
  );
}
