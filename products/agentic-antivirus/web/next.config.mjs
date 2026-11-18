/** Static export: the console is plain files served by the reverse proxy (no Node server on the VM),
 *  and the same build is wrapped by the desktop and mobile shells. API calls go to NEXT_PUBLIC_API_BASE. */
/** Optional sub-path (e.g. /apps/agentic-antivirus) when the console shares a host with other apps. */
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";
export default {
  basePath,
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};
