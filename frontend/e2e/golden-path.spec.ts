import { expect, test, type Page, type Route } from "@playwright/test";

const NOW = "2026-09-10T10:00:00Z";
const CONVERSATION_ID = "conversation-golden-path";
const SEGMENT_ID = "segment-evidence-source";
const FACT_TEXT = "This statement is grounded in the transcript.";

const operatorPermissions = [
  "conversation:create",
  "conversation:read",
  "conversation:update",
  "conversation:delete",
  "conversation:upload",
  "conversation:manage-participants",
  "conversation:manage-notes",
  "conversation:manage-markers",
  "transcript:read",
  "transcript:process",
  "transcript:correct",
  "speaker:read",
  "speaker:assign",
  "fact:read",
  "fact:extract",
  "fact:redact",
  "protocol:read",
  "protocol:generate",
  "review-issue:read",
  "review-issue:resolve",
  "document:read",
  "document:edit",
  "document:approve",
  "processing-profile:read",
  "task:read",
  "task:create",
  "task:update",
  "known-speaker:read",
  "known-speaker:manage",
];

const conversation = {
  id: CONVERSATION_ID,
  organization_id: "organization-golden-path",
  created_by_user_id: "operator-user",
  title: "Evidence chain golden path",
  description: null,
  conversation_type: "general",
  status: "uploaded",
  started_at: null,
  ended_at: null,
  duration_ms: 20_000,
  external_reference: null,
  external_reference_type: null,
  privacy_mode: "standard",
  retention_policy_id: null,
  processing_profile_id: null,
  group_id: null,
  created_at: NOW,
  updated_at: NOW,
};

const media = {
  id: "source-media",
  conversation_id: CONVERSATION_ID,
  kind: "source_audio",
  source_type: "file_upload",
  original_filename: "golden-path.wav",
  content_type: "audio/wav",
  size_bytes: 640_044,
  sha256: "0".repeat(64),
  duration_ms: 20_000,
  sample_rate: 16_000,
  channels: 1,
  codec: "pcm_s16le",
  container: "wav",
  derived_from_media_id: null,
  created_by_user_id: "operator-user",
  created_at: NOW,
};

const transcript = {
  id: "transcript-golden-path",
  conversation_id: CONVERSATION_ID,
  source_media_id: media.id,
  language: "en",
  status: "ready",
  provider: "deterministic-e2e",
  model: "fixture",
  model_revision: null,
  is_active: true,
  error_code: null,
  error_message_safe: null,
  created_at: NOW,
  updated_at: NOW,
};

const segment = {
  id: SEGMENT_ID,
  transcript_id: transcript.id,
  speaker_id: null,
  sequence: 0,
  start_ms: 12_345,
  end_ms: 16_000,
  original_text: FACT_TEXT,
  corrected_text: null,
  confidence: 0.99,
  words: null,
  review_status: "confirmed",
  alignment_quality: "confident",
  review_flag: false,
  review_flag_reason: null,
};

const fact = {
  id: "fact-golden-path",
  conversation_id: CONVERSATION_ID,
  processing_run_id: "processing-run",
  category: "general_fact",
  fact_type: "statement",
  structured_value: {
    subject: "Evidence chain",
    attribute: "statement",
    value: FACT_TEXT,
    certainty: "stated",
    evidence_segment_sequences: [0],
  },
  certainty: "stated",
  confidence: 0.99,
  status: "verified",
  review_status: "confirmed",
  corrected_structured_value: null,
  reviewed_by_user_id: "operator-user",
  reviewed_at: NOW,
  is_redacted: false,
  created_at: NOW,
  updated_at: NOW,
};

const evidence = {
  id: "evidence-golden-path",
  fact_id: fact.id,
  transcript_segment_id: SEGMENT_ID,
  evidence_type: "evidence_direct",
  created_at: NOW,
  segment_sequence: 0,
  segment_start_ms: 12_345,
  segment_end_ms: 16_000,
  segment_text: FACT_TEXT,
};

function protocol() {
  return {
    id: "protocol-golden-path",
    conversation_id: CONVERSATION_ID,
    current_revision_id: "protocol-revision",
    created_at: NOW,
    updated_at: NOW,
    current_revision: {
      id: "protocol-revision",
      protocol_id: "protocol-golden-path",
      revision_number: 1,
      status: "ready",
      created_at: NOW,
      sections: [
        {
          id: "protocol-section",
          protocol_revision_id: "protocol-revision",
          position: 0,
          section_type: "facts",
          title: "Verified statement",
          summary: "One statement is grounded in the transcript.",
          start_ms: 12_345,
          end_ms: 16_000,
          confidence: 0.99,
          manually_edited: false,
          items: [
            {
              id: "protocol-item",
              protocol_section_id: "protocol-section",
              position: 0,
              item_type: "fact",
              text: FACT_TEXT,
              responsible_label: null,
              due_date: null,
              completed: null,
              confidence: 0.99,
              manually_edited: false,
            },
          ],
        },
      ],
    },
  };
}

function document(status: "ready_for_approval" | "approved") {
  const revision = {
    id: "document-revision",
    document_id: "document-golden-path",
    revision_number: 1,
    structured_content: [
      { category: "general_fact", title: "Facts", statements: [{ text: FACT_TEXT, fact_ids: [fact.id] }] },
    ],
    rendered_text: FACT_TEXT,
    status,
    blocking_issue_ids: [],
    created_by_user_id: "operator-user",
    approved_by_user_id: status === "approved" ? "operator-user" : null,
    approved_at: status === "approved" ? NOW : null,
    document_layout: "sections",
    created_at: NOW,
    updated_at: NOW,
  };
  return {
    id: "document-golden-path",
    conversation_id: CONVERSATION_ID,
    status,
    current_revision_id: revision.id,
    created_at: NOW,
    updated_at: NOW,
    current_revision: revision,
  };
}

function silentWav(seconds = 20): Buffer {
  const sampleRate = 16_000;
  const dataSize = sampleRate * seconds * 2;
  const wav = Buffer.alloc(44 + dataSize);
  wav.write("RIFF", 0);
  wav.writeUInt32LE(36 + dataSize, 4);
  wav.write("WAVEfmt ", 8);
  wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20);
  wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(sampleRate, 24);
  wav.writeUInt32LE(sampleRate * 2, 28);
  wav.writeUInt16LE(2, 32);
  wav.writeUInt16LE(16, 34);
  wav.write("data", 36);
  wav.writeUInt32LE(dataSize, 40);
  return wav;
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function installMockApi(page: Page) {
  let user: "operator" | "normal" | null = null;
  let uploaded = false;
  let transcriptReady = false;
  let factsReady = false;
  let protocolReady = false;
  let documentStatus: "missing" | "ready_for_approval" | "approved" = "missing";

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const method = request.method();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/v1", "");

    if (path === "/auth/login" && method === "POST") {
      const credentials = request.postDataJSON() as { username: string };
      user = credentials.username === "normal-user" ? "normal" : "operator";
      return json(route, {
        user_id: `${user}-user`,
        username: credentials.username,
        display_name: user === "normal" ? "Normal User" : "Golden Operator",
        csrf_token: "csrf-e2e",
      });
    }
    if (path === "/auth/me") {
      if (!user) return json(route, { detail: "not authenticated" }, 401);
      return json(route, {
        user_id: `${user}-user`,
        username: user === "normal" ? "normal-user" : "operator",
        display_name: user === "normal" ? "Normal User" : "Golden Operator",
        email: null,
        permissions: user === "normal" ? ["conversation:read"] : operatorPermissions,
        groups: [],
        first_name: null,
        last_name: null,
        gender: null,
        avatar_asset_key: null,
      });
    }
    if (path === "/auth/csrf") return json(route, { csrf_token: "csrf-e2e" });
    if (path === "/organizations") {
      return json(route, [{ id: "organization-golden-path", name: "Golden Path Organization", slug: "golden", description: null }]);
    }
    if (path === "/processing-profiles") return json(route, []);
    if (path === "/conversations/stats") return json(route, { counts: {} });
    if (path === "/conversations" && method === "GET") {
      return json(route, { items: uploaded ? [conversation] : [], total: uploaded ? 1 : 0, limit: 50, offset: 0 });
    }
    if (path === "/conversations" && method === "POST") return json(route, conversation, 201);
    if (path === `/conversations/${CONVERSATION_ID}/media` && method === "POST") {
      uploaded = true;
      return json(route, media, 201);
    }
    if (path === `/conversations/${CONVERSATION_ID}`) return json(route, conversation);
    if (path === `/conversations/${CONVERSATION_ID}/media`) return json(route, uploaded ? [media] : []);
    if (path === `/conversations/${CONVERSATION_ID}/media/${media.id}/content`) {
      const audio = silentWav();
      const range = request.headers()["range"];
      const match = range?.match(/^bytes=(\d+)-(\d*)$/);
      if (match) {
        const start = Number(match[1]);
        const requestedEnd = match[2] ? Number(match[2]) : audio.length - 1;
        const end = Math.min(requestedEnd, audio.length - 1);
        return route.fulfill({
          status: 206,
          headers: {
            "Accept-Ranges": "bytes",
            "Content-Length": String(end - start + 1),
            "Content-Range": `bytes ${start}-${end}/${audio.length}`,
            "Content-Type": "audio/wav",
          },
          body: audio.subarray(start, end + 1),
        });
      }
      return route.fulfill({
        headers: {
          "Accept-Ranges": "bytes",
          "Content-Length": String(audio.length),
          "Content-Type": "audio/wav",
        },
        body: audio,
      });
    }
    if (["participants", "markers", "notes", "speakers", "tasks"].some((part) => path === `/conversations/${CONVERSATION_ID}/${part}`)) {
      return json(route, []);
    }
    if (path === "/known-speakers") return json(route, []);
    if (path === `/conversations/${CONVERSATION_ID}/completeness`) {
      return json(route, {
        conversation_id: CONVERSATION_ID,
        template_key: null,
        template_name: null,
        template_version_id: null,
        categories: [],
        category_coverage_ratio: 1,
        decisions_total: 0,
        decisions_missing_decided_by: 0,
        tasks_total: 0,
        tasks_missing_assignee: 0,
        overall_score: 1,
        speaking_shares: [],
        longest_monologue: null,
      });
    }
    if (path === `/conversations/${CONVERSATION_ID}/process/transcript` && method === "POST") {
      transcriptReady = true;
      return json(route, transcript, 202);
    }
    if (path === `/conversations/${CONVERSATION_ID}/processing`) {
      const jobs = transcriptReady
        ? [{ id: "transcript-job", job_type: "align", status: "succeeded", progress: 100, attempt: 1, max_attempts: 3, failure_class: null, error_code: null, error_message_safe: null, queued_at: NOW, started_at: NOW, completed_at: NOW }]
        : [];
      if (protocolReady) jobs.push({ ...jobs[0], id: "protocol-job", job_type: "generate_protocol" });
      return json(route, { conversation_status: transcriptReady ? "ready" : "uploaded", jobs });
    }
    if (path === `/conversations/${CONVERSATION_ID}/transcript`) {
      return transcriptReady ? json(route, transcript) : json(route, { detail: "not found" }, 404);
    }
    if (path === `/conversations/${CONVERSATION_ID}/transcript/segments`) return json(route, [segment]);
    if (path === `/conversations/${CONVERSATION_ID}/process/extract` && method === "POST") {
      factsReady = true;
      return json(route, [fact], 202);
    }
    if (path === `/conversations/${CONVERSATION_ID}/facts`) return json(route, factsReady ? [fact] : []);
    if (path === `/conversations/${CONVERSATION_ID}/facts/${fact.id}/evidence`) return json(route, [evidence]);
    if (path === `/conversations/${CONVERSATION_ID}/review-issues`) return json(route, []);
    if (path === `/conversations/${CONVERSATION_ID}/protocol/generate` && method === "POST") {
      protocolReady = true;
      return json(route, {}, 202);
    }
    if (path === `/conversations/${CONVERSATION_ID}/protocol`) {
      return protocolReady ? json(route, protocol()) : json(route, { detail: "not found" }, 404);
    }
    if (path === `/conversations/${CONVERSATION_ID}/protocol/revisions`) {
      return json(route, protocolReady ? [protocol().current_revision] : []);
    }
    if (path === `/conversations/${CONVERSATION_ID}/protocol/items/protocol-item/sources` || path === `/conversations/${CONVERSATION_ID}/protocol/sections/protocol-section/sources`) {
      return json(route, [{ id: "protocol-source", transcript_segment_id: SEGMENT_ID, segment_start_ms: 12_345, segment_end_ms: 16_000, segment_text: FACT_TEXT, speaker_label: "Speaker 1" }]);
    }
    if (path === `/conversations/${CONVERSATION_ID}/document/compose` && method === "POST") {
      documentStatus = "ready_for_approval";
      return json(route, document(documentStatus));
    }
    if (path === `/conversations/${CONVERSATION_ID}/document/approve` && method === "POST") {
      documentStatus = "approved";
      return json(route, document(documentStatus));
    }
    if (path === `/conversations/${CONVERSATION_ID}/document`) {
      return documentStatus === "missing" ? json(route, { detail: "not found" }, 404) : json(route, document(documentStatus));
    }
    if (path === `/conversations/${CONVERSATION_ID}/document/revisions`) {
      return json(route, documentStatus === "missing" ? [] : [document(documentStatus).current_revision]);
    }
    if (path === `/conversations/${CONVERSATION_ID}/document/export`) {
      return route.fulfill({ status: 200, contentType: "text/plain", body: FACT_TEXT });
    }
    if (path === "/tasks") return json(route, []);

    return json(route, { detail: `unmocked endpoint: ${method} ${path}` }, 501);
  });
}

async function signIn(page: Page, username: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill("test-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

test("operator completes the evidence-preserving browser golden path", async ({ page }) => {
  await installMockApi(page);
  await signIn(page, "operator");

  await page.goto("/app/conversations/new?mode=upload");
  await page.getByLabel("Titel").fill(conversation.title);
  await page.getByLabel("Organisation").selectOption(conversation.organization_id);
  await page.getByLabel("Audiodatei").setInputFiles({
    name: "golden-path.wav",
    mimeType: "audio/wav",
    buffer: silentWav(1),
  });
  await page.getByRole("button", { name: "Erstellen und hochladen" }).click();
  await expect(page).toHaveURL(new RegExp(`/app/conversations/${CONVERSATION_ID}$`));

  await page.getByRole("tab", { name: "Transkript" }).click();
  await page.getByRole("button", { name: "Transkription starten" }).click();
  await expect(page.getByText(FACT_TEXT)).toBeVisible();

  await page.getByRole("tab", { name: "Fakten" }).click();
  await page.getByRole("button", { name: "Fakten extrahieren" }).click();
  const factRow = page.locator("li").filter({ hasText: `Evidence chain — statement: ${FACT_TEXT}` });
  await expect(factRow).toBeVisible();
  await factRow.getByRole("button").first().click();
  await factRow.getByRole("button", { name: FACT_TEXT }).click();
  await expect.poll(() => page.locator("audio").evaluate((audio) => (audio as HTMLAudioElement).currentTime)).toBeCloseTo(12.345, 2);

  await page.getByRole("tab", { name: "Protokoll" }).click();
  await page.getByRole("button", { name: "Protokoll erstellen" }).click();
  const protocolItem = page.locator("li").filter({ hasText: FACT_TEXT });
  await protocolItem.getByTitle("Quelle anzeigen").click();
  await expect(protocolItem.getByText(`“${FACT_TEXT}”`)).toBeVisible();
  await protocolItem.getByRole("button", { name: "Im Transkript öffnen" }).click();
  await expect(page.getByRole("tab", { name: "Transkript" })).toHaveAttribute("aria-selected", "true");
  await expect(page.locator(`#transcript-segment-${SEGMENT_ID}`)).toBeInViewport();

  await page.getByRole("tab", { name: "Review" }).click();
  await expect(page.getByText("Keine offenen Review-Punkte")).toBeVisible();

  await page.getByRole("tab", { name: "Dokumentation" }).click();
  await page.getByRole("button", { name: "Dokument erstellen" }).click();
  await expect(page.getByText(FACT_TEXT)).toBeVisible();
  await page.getByRole("button", { name: "Dokument freigeben" }).click();
  await expect(page.getByText("Freigegeben").first()).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: ".txt" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(`document-${CONVERSATION_ID}.txt`);
});

test("normal user cannot cross the administration permission boundary", async ({ page }) => {
  await installMockApi(page);
  await signIn(page, "normal-user");

  await page.goto("/admin/users");
  await expect(page.getByRole("heading", { name: "Access denied" })).toBeVisible();
  await expect(page.getByText("You don't have permission to view this page.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Administration" })).toHaveCount(0);
});
