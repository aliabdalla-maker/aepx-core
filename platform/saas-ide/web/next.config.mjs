// Security headers for every route. The policy is computed at build time from the same
// NEXT_PUBLIC_* settings the app uses, so only the configured API, IdP and (if enabled) ad
// origins are reachable from the browser.
const origin = (value) => {
  try { return value ? new URL(value).origin : ""; } catch { return ""; }
};

const api = origin(process.env.NEXT_PUBLIC_IDE_API_URL);
const idp = origin(process.env.NEXT_PUBLIC_OIDC_AUTHORITY);
const ads = process.env.NEXT_PUBLIC_ADS_ENABLED === "true"
  ? ["https://pagead2.googlesyndication.com", "https://*.googlesyndication.com",
     "https://*.doubleclick.net", "https://*.google.com", "https://*.gstatic.com",
     "https://*.adtrafficquality.google"]
  : [];

const list = (...items) => items.flat().filter(Boolean).join(" ");

// Next.js bootstraps with inline scripts, so script-src keeps 'unsafe-inline' (no nonce
// middleware yet); 'unsafe-eval' is NOT allowed. Monaco is self-hosted from /monaco/vs and
// needs blob: workers and inline styles.
const csp = [
  "default-src 'self'",
  `script-src ${list("'self'", "'unsafe-inline'", ads)}`,
  "style-src 'self' 'unsafe-inline'",
  `img-src ${list("'self'", "data:", "blob:", ads)}`,
  "font-src 'self' data:",
  `connect-src ${list("'self'", api, idp, ads)}`,
  `frame-src ${list("'self'", idp, ads)}`,
  "worker-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  `form-action ${list("'self'", idp)}`,
  "frame-ancestors 'self'", // the silent-renew iframe is same-origin; nobody else may frame the IDE
  // Only force HTTPS sub-requests when the API itself is HTTPS (keeps local http dev working).
  ...(api.startsWith("https://") ? ["upgrade-insecure-requests"] : []),
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(self)" },
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin-allow-popups" },
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
