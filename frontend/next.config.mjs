/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // A self-contained server bundle for the multi-stage Docker image.
  output: "standalone",
  // `npm run dev` binds to 0.0.0.0 but the browser opens the page on 127.0.0.1. Next 16 blocks
  // dev-only resources (HMR and the dev runtime) for origins it does not allow, and the console
  // error is easy to miss: the page renders its server HTML but never hydrates, so every fetch
  // effect silently does nothing and the UI sits on "Loading users...". Both loopback spellings
  // are the same machine, so both are allowed.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
};

export default nextConfig;
