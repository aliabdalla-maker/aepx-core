/** Static export: the console is plain files served by the reverse proxy (no Node server on the VM),
 *  and the same build is wrapped by the desktop and mobile shells. API calls go to NEXT_PUBLIC_API_BASE. */
export default {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};
