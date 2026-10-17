/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // A self-contained server bundle for the multi-stage Docker image.
  output: "standalone",
};

export default nextConfig;
