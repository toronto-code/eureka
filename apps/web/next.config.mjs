/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    typedRoutes: false,
  },
  // Standalone output keeps the docker image small.
  output: "standalone",
};

export default nextConfig;
