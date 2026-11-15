/** Media Studio client: types, API calls and pure helpers (unit-tested in lib.test.ts). */
import type { Requester } from "./api";

export type MediaKind = "image" | "video" | "music" | "voice" | "script";
export type Platform = "mock" | "mastodon" | "x" | "linkedin" | "youtube" | "tiktok" | "instagram";

export type MediaJob = {
  id: string; kind: MediaKind; provider: string; prompt: string; params: Record<string, unknown>;
  estimate_pence: number; state: "proposed" | "approved" | "rejected" | "running" | "succeeded" | "failed";
  requested_by: string; approved_by: string | null; result_url: string | null; result_text: string | null;
  error: string | null; has_asset: boolean; created_at: string;
};
export type SocialPost = {
  id: string; platform: Platform; mode: "api" | "export"; body: string; media_job_ids: string[];
  scheduled_for: string | null; state: "draft" | "approved" | "rejected" | "publishing" | "published" | "exported" | "failed";
  created_by: string; approved_by: string | null; external_url: string | null; error: string | null;
};
export type MediaCapabilities = {
  providers: Record<string, { kinds: MediaKind[]; configured: boolean }>;
  platforms: Record<Platform, { mode: "api" | "export"; limit: number; configured: boolean }>;
  templates: { id: string; title: string; description: string; files: string[] }[];
  approval_required: boolean; four_eyes: boolean;
};
export type Storyboard = {
  title: string; logline: string; fps: 24 | 25 | 30; soundtrack_job_id: string | null;
  scenes: { id: string; title: string; script: string; shots: { id: string; description: string; duration_s: number; media_job_id: string | null }[] }[];
  timeline: { shot_id: string; start_s: number; end_s: number }[];
};

const e = encodeURIComponent;

export const mediaApi = (r: Requester) => ({
  capabilities: () => r<MediaCapabilities>("/api/v1/media/capabilities"),
  applyTemplate: (project: string, template: string) =>
    r<{ created: string[]; skipped: string[] }>(`/api/v1/projects/${e(project)}/media-templates/${e(template)}`, "POST"),
  storyboard: (project: string) => r<Storyboard>(`/api/v1/projects/${e(project)}/storyboard`),
  saveStoryboard: (project: string, board: Storyboard) => r<Storyboard>(`/api/v1/projects/${e(project)}/storyboard`, "PUT", board),
  jobs: (project: string) => r<MediaJob[]>(`/api/v1/projects/${e(project)}/media-jobs`),
  createJob: (project: string, kind: MediaKind, provider: string, prompt: string, params: Record<string, unknown> = {}) =>
    r<MediaJob>(`/api/v1/projects/${e(project)}/media-jobs`, "POST", { kind, provider, prompt, params }),
  decideJob: (id: string, approved: boolean) => r<MediaJob>(`/api/v1/media-jobs/${e(id)}/decision?approved=${approved}`, "POST"),
  runJob: (id: string) => r<MediaJob>(`/api/v1/media-jobs/${e(id)}/run`, "POST"),
  refreshJob: (id: string) => r<MediaJob>(`/api/v1/media-jobs/${e(id)}/refresh`, "POST"),
  posts: (project: string) => r<SocialPost[]>(`/api/v1/projects/${e(project)}/social-posts`),
  createPost: (project: string, platform: Platform, body: string, media: string[] = [], scheduledFor?: string) =>
    r<SocialPost>(`/api/v1/projects/${e(project)}/social-posts`, "POST",
      { platform, body, media_job_ids: media, ...(scheduledFor ? { scheduled_for: scheduledFor } : {}) }),
  decidePost: (id: string, approved: boolean) => r<SocialPost>(`/api/v1/social-posts/${e(id)}/decision?approved=${approved}`, "POST"),
  publishPost: (id: string) => r<SocialPost>(`/api/v1/social-posts/${e(id)}/publish`, "POST"),
});

export function formatPence(pence: number): string {
  if (!Number.isFinite(pence) || pence <= 0) return "free";
  return pence < 100 ? `~${pence}p` : `~£${(pence / 100).toFixed(2)}`;
}

export const canApprove = (role: string | undefined) => role === "owner" || role === "admin";
export const canEdit = (role: string | undefined) => canApprove(role) || role === "editor";

/** Providers that are enabled and can make this kind of media, mock last. */
export function providersFor(caps: MediaCapabilities | null, kind: MediaKind): string[] {
  if (!caps) return [];
  return Object.entries(caps.providers)
    .filter(([, p]) => p.configured && p.kinds.includes(kind))
    .map(([name]) => name)
    .sort((a, b) => (a === "mock" ? 1 : 0) - (b === "mock" ? 1 : 0) || a.localeCompare(b));
}

/** Characters left for a platform; negative means the post is too long. */
export function charsLeft(caps: MediaCapabilities | null, platform: Platform, body: string): number {
  const limit = caps?.platforms[platform]?.limit ?? 5000;
  return limit - [...body].length;
}

/** Total running time of a storyboard's timeline, as m:ss. */
export function runtime(board: Pick<Storyboard, "timeline">): string {
  const end = board.timeline.reduce((m, c) => Math.max(m, c.end_s), 0);
  const total = Math.round(end);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}
