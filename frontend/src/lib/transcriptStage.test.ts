import { describe, expect, it } from "vitest";

import type { ProcessingJob } from "../api/transcription";
import { stageFromJobs } from "./transcriptStage";

function job(overrides: Partial<ProcessingJob>): ProcessingJob {
  return {
    id: "job-1",
    job_type: "normalize",
    status: "succeeded",
    progress: 100,
    attempt: 1,
    max_attempts: 3,
    failure_class: null,
    error_code: null,
    error_message_safe: null,
    queued_at: "2026-09-07T22:16:30Z",
    started_at: "2026-09-07T22:16:31Z",
    completed_at: "2026-09-07T22:16:38Z",
    ...overrides,
  };
}

describe("stageFromJobs", () => {
  it("reports the active job's stage", () => {
    const jobs = [
      job({ job_type: "transcribe", status: "running", completed_at: null }),
      job({ job_type: "normalize", status: "succeeded" }),
    ];
    expect(stageFromJobs(jobs, undefined)).toBe("transcribing");
  });

  it("does not report 'failed' during the gap between one job succeeding and the next being enqueued", () => {
    // Real regression: normalize just succeeded, transcribe hasn't been
    // created yet -- no job is queued/running, but nothing has actually
    // failed either. Previously this briefly (and incorrectly) rendered
    // "Transkription fehlgeschlagen" until the next poll caught up.
    const jobs = [job({ job_type: "normalize", status: "succeeded" })];
    expect(stageFromJobs(jobs, undefined)).toBe("preparing");
  });

  it("reports 'failed' only when a job actually failed", () => {
    const jobs = [
      job({ job_type: "transcribe", status: "failed", failure_class: "provider_error" }),
      job({ job_type: "normalize", status: "succeeded" }),
    ];
    expect(stageFromJobs(jobs, undefined)).toBe("failed");
  });

  it("reports 'idle' when no jobs exist yet", () => {
    expect(stageFromJobs([], undefined)).toBe("idle");
  });

  it("defers to the transcript's own status once ready", () => {
    const jobs = [job({ job_type: "align", status: "succeeded" })];
    expect(stageFromJobs(jobs, "ready")).toBe("ready");
  });
});
