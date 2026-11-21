// Seed messages + annotations + threads: the inbox
// rows, the plan-anchored annotation threads, and
// the message threads.

import type {
  AnnotationThread,
  InboxMessage,
  MessageThread,
} from "../types";


export function buildMessages(): InboxMessage[] {
  const messages: InboxMessage[] = [
    {
      id: "m-1", kind: "mockup", title: "Superapp storyboard — launcher",
      project: "fennelwick", arrivedLabel: "arrived 12 min ago",
      disposition: null, target: { section: "mockups", entryId: "e-launcher" },
    },
    {
      id: "m-2", kind: "mockup", title: "Operator chat view — storyboard rebuild",
      project: "sablebrook", arrivedLabel: "arrived 1 h ago",
      disposition: null, target: { section: "mockups", entryId: "e-operator-chat" },
    },
    {
      id: "m-3", kind: "doctor", title: "Doctor digest — 2 findings changed",
      project: "workbench doctor", arrivedLabel: "arrived 2 h ago",
      disposition: null, target: { section: "overview" },
    },
    {
      id: "m-4", kind: "plan", title: "AGENTS.md rule layers — plan adopted",
      project: "fennelwick", arrivedLabel: "yesterday",
      disposition: "filed", target: { section: "plans", bundle: "2026-11-08-agents-rule-layers" },
    },
  ];
  return messages;
}

export function buildAnnotations(): AnnotationThread[] {
  const annotations: AnnotationThread[] = [
    {
      id: "ann-1",
      bundle: "2026-11-12-superapp-storyboards",
      project: "fennelwick",
      anchorQuote: "an approved mockup is an exact spec",
      anchorContext:
        "> Ruling (2026-11-12): an approved mockup is an exact spec — what the owner sees in the storyboard is what gets implemented, with no explanatory prose in the mock itself.",
      status: "anchored",
      resolved: false,
      messages: [
        {
          id: "ann-1-m1",
          author: "critic",
          body: "This is the line the whole storyboard programme hangs on — the frames either are the spec or they are decoration.",
          when: "Nov 12",
        },
        {
          id: "ann-1-m2",
          author: "spec-starter",
          body: "Agreed; the critic pass checks every frame against it before the owner pick.",
          when: "Nov 12",
        },
      ],
    },
    {
      id: "ann-2",
      bundle: "2026-11-12-superapp-storyboards",
      project: "fennelwick",
      anchorQuote: "the storyboard is inspiration, not a spec",
      status: "orphaned",
      resolved: false,
      messages: [
        {
          id: "ann-2-m1",
          author: "critic",
          body: "This phrasing was struck from the plan when the ruling landed — the anchor no longer exists in the text.",
          when: "Nov 12",
        },
      ],
    },
    {
      id: "ann-3",
      bundle: "2026-11-11-document-parsing-successor",
      project: "aldercrest",
      anchorQuote: "Genre defect — ruling-line cure",
      anchorContext: "3. Genre defect — ruling-line cure",
      status: "anchored",
      resolved: true,
      messages: [
        {
          id: "ann-3-m1",
          author: "aldercrest-data",
          body: "The cure is a ruling line, not a build — noted here so the segment lanes do not start against the impostor classes.",
          when: "Nov 11",
        },
      ],
    },
    {
      id: "ann-4",
      bundle: "2026-11-11-document-parsing-successor",
      project: "aldercrest",
      anchorQuote: "Population audit",
      anchorContext: "5. Population audit — specimen standing transfers to the draw",
      status: "relocated",
      resolved: false,
      messages: [
        {
          id: "ann-4-m1",
          author: "aldercrest-data",
          body: "The step line was edited after this annotation was anchored — the quote survives, its line does not.",
          when: "Nov 12",
        },
      ],
    },
  ];
  return annotations;
}

export function buildThreads(): MessageThread[] {
  const threads: MessageThread[] = [
    {
      id: "th-1",
      project: "fennelwick",
      title: "Superapp storyboard — launcher",
      state: "sent",
      messages: [
        {
          id: "th-1-m1",
          author: "spec-starter",
          body: "The launcher storyboard is in triage. It renders the programme's entries as frames; the owner pick makes it the exact spec for the launcher build.",
          when: "12 min ago",
        },
      ],
    },
    {
      id: "th-2",
      project: "sablebrook",
      title: "Operator chat view — storyboard rebuild",
      state: "acknowledged",
      messages: [
        {
          id: "th-2-m1",
          author: "sablebrook-cust",
          body: "Rebuilt storyboard for the operator chat view; two change requests are open on the entry itself.",
          when: "1 h ago",
        },
        {
          id: "th-2-m2",
          author: "owner",
          body: "Seen — the changes ride the entry's review, not this thread.",
          when: "44 min ago",
        },
      ],
    },
    {
      id: "th-3",
      project: "workbench doctor",
      title: "Doctor digest — 2 findings changed",
      state: "sent",
      messages: [
        {
          id: "th-3-m1",
          author: "workbench doctor",
          body: "Two findings changed since the last digest: the missing doctor runner (now ported) and a stale link probe state.",
          when: "2 h ago",
        },
      ],
    },
    {
      id: "th-4",
      project: "fennelwick",
      title: "Draft — storyboard close-out note",
      state: "draft",
      messages: [
        {
          id: "th-4-m1",
          author: "owner",
          body: "Draft: when the critic pass clears, the close report goes to main with the frame inventory attached.",
          when: "draft",
        },
      ],
    },
  ];
  return threads;
}
