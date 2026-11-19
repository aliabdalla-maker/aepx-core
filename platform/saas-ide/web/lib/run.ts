// Run button state and output formatting. The run itself happens in the isolated sandbox runner
// behind POST /api/v1/projects/{id}/run; nothing executes in the browser.

export type ExecutionStatus = { enabled: boolean; languages: string[]; reason: string };
export type RunOutput = {
  stdout: string; stderr: string; exit_code: number | null; timed_out: boolean;
  duration_ms: number; truncated: boolean; runtime?: string; language?: string;
};

const RUNNABLE = /\.(py|js|mjs|cjs)$/i;
export const isRunnable = (path: string | undefined) => Boolean(path && RUNNABLE.test(path));

/** Why Run is disabled (empty string when it can run). */
export function runHint(o: { signedIn: boolean; status: ExecutionStatus | null; path?: string; running: boolean }): string {
  if (!o.signedIn) return "Sign in to run code.";
  if (!o.path) return "Open a Python or JavaScript file to run it.";
  if (!isRunnable(o.path)) return "Only Python (.py) and JavaScript (.js) files can be run.";
  if (!o.status) return "Checking whether code can run here…";
  if (!o.status.enabled) return o.status.reason || "Running code is not available.";
  if (o.running) return "Running…";
  return "";
}

/** One-line summary under the output, e.g. "exit 0 · 0.42 s · gVisor sandbox". */
export function runSummary(r: RunOutput): string {
  const parts = [r.timed_out ? "stopped: time limit" : `exit ${r.exit_code ?? "?"}`,
    `${(r.duration_ms / 1000).toFixed(2)} s`];
  if (r.runtime) parts.push(r.runtime === "runsc" ? "gVisor sandbox" : `${r.runtime} sandbox`);
  if (r.truncated) parts.push("output truncated");
  return parts.join(" · ");
}

export const runSucceeded = (r: RunOutput) => !r.timed_out && r.exit_code === 0;
