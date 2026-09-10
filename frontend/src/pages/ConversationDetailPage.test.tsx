import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

import type { AuthState, AuthUser } from "../auth/context";
import { AuthContext } from "../auth/context";
import type { Conversation, Participant } from "../api/conversations";
import * as conversationsApi from "../api/conversations";
import type { OrganizationMemberUser } from "../api/organizations";
import { ConversationDetailPage } from "./ConversationDetailPage";

vi.mock("../api/conversations", async (importOriginal) => {
  const actual = await importOriginal<typeof conversationsApi>();
  return { ...actual, addParticipant: vi.fn().mockResolvedValue({}) };
});

const CONVERSATION_ID = "fixture-conversation";
const ORG_ID = "fixture-org";

const conversationFixture: Conversation = {
  id: CONVERSATION_ID,
  organization_id: ORG_ID,
  created_by_user_id: "fixture-owner",
  title: "Testgespräch",
  description: null,
  conversation_type: "general",
  status: "ready",
  started_at: null,
  ended_at: null,
  duration_ms: null,
  external_reference: null,
  external_reference_type: null,
  privacy_mode: "standard",
  retention_policy_id: null,
  processing_profile_id: null,
  group_id: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

// Dana is already linked to a participant below -- she must NOT reappear
// in the "Registrierte Person" picker. Erik is still pickable.
const orgUsersFixture: OrganizationMemberUser[] = [
  {
    id: "user-dana",
    username: "dana",
    display_name: "Dana",
    first_name: null,
    last_name: null,
    avatar_asset_key: null,
  },
  {
    id: "user-erik",
    username: "erik",
    display_name: "Erik",
    first_name: null,
    last_name: null,
    avatar_asset_key: null,
  },
];

const participantsFixture: Participant[] = [
  {
    id: "participant-dana",
    conversation_id: CONVERSATION_ID,
    display_name: "Dana",
    participant_type: "staff",
    external_reference: null,
    notes: null,
    known_speaker_id: null,
    user_id: "user-dana",
    created_at: "2026-01-01T00:00:00Z",
  },
];

function makeUser(permissions: string[]): AuthUser {
  return {
    userId: "fixture-user",
    username: "alice",
    displayName: "Alice",
    email: null,
    permissions,
    groups: [],
    firstName: null,
    lastName: null,
    gender: null,
    avatarAssetKey: null,
  };
}

function renderPage(permissions: string[]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  client.setQueryData(["conversation", CONVERSATION_ID], conversationFixture);
  client.setQueryData(["conversation-media", CONVERSATION_ID], []);
  client.setQueryData(["conversation-participants", CONVERSATION_ID], participantsFixture);
  client.setQueryData(["conversation-markers", CONVERSATION_ID], []);
  client.setQueryData(["conversation-notes", CONVERSATION_ID], []);
  client.setQueryData(["processing-status", CONVERSATION_ID], { conversation_id: CONVERSATION_ID, jobs: [] });
  client.setQueryData(["transcript", CONVERSATION_ID], undefined);
  client.setQueryData(["document", CONVERSATION_ID], null);
  client.setQueryData(["speakers", CONVERSATION_ID], []);
  client.setQueryData(["organization-member-users", ORG_ID], orgUsersFixture);
  client.setQueryData(["known-speakers", ORG_ID], []);

  const authValue: AuthState = {
    user: makeUser(permissions),
    csrfToken: "fixture-csrf",
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
    hasPermission: (code: string) => permissions.includes(code),
    refreshUser: vi.fn(),
  };

  render(
    <QueryClientProvider client={client}>
      <AuthContext.Provider value={authValue}>
        <MemoryRouter initialEntries={[`/app/conversations/${CONVERSATION_ID}`]}>
          <Routes>
            <Route path="/app/conversations/:id" element={<ConversationDetailPage />} />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>
    </QueryClientProvider>
  );
}

function openAddParticipantDisclosure() {
  fireEvent.click(screen.getByText("Teilnehmer hinzufügen"));
}

describe("ConversationDetailPage — participants from the user directory", () => {
  it("adds a participant linked to a registered user, excluding already-linked ones", async () => {
    renderPage(["conversation:manage-participants", "user:read-directory"]);
    openAddParticipantDisclosure();

    const sourceSelect = screen.getByRole("combobox", { name: "Quelle" });
    fireEvent.change(sourceSelect, { target: { value: "user" } });

    const userSelect = screen.getByRole("combobox", { name: "Registrierte Person auswählen" });
    // Dana is already a participant (user_id: "user-dana") -- must not be offered again.
    expect(within(userSelect).queryByText(/Dana/)).not.toBeInTheDocument();
    expect(within(userSelect).getByText("Erik (@erik)")).toBeInTheDocument();

    fireEvent.change(userSelect, { target: { value: "user-erik" } });

    // Selecting a registered user pre-fills the (still editable) name field.
    const nameInput = screen.getByRole("textbox", { name: "Teilnehmername" }) as HTMLInputElement;
    expect(nameInput.value).toBe("Erik");

    fireEvent.click(screen.getByRole("button", { name: "Hinzufügen" }));

    await waitFor(() =>
      expect(conversationsApi.addParticipant).toHaveBeenCalledWith(
        CONVERSATION_ID,
        expect.objectContaining({ user_id: "user-erik", display_name: "Erik" }),
        "fixture-csrf"
      )
    );
  });

  it("does not offer the registered-user source without user:read-directory", () => {
    renderPage(["conversation:manage-participants"]);
    openAddParticipantDisclosure();

    expect(screen.queryByRole("combobox", { name: "Quelle" })).not.toBeInTheDocument();
    // Falls back to the pre-existing free-text flow.
    expect(screen.getByRole("textbox", { name: "Teilnehmername" })).toBeInTheDocument();
  });
});
