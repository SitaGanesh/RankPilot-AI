import type { NextConfig } from "next";

const DJANGO_URL = process.env.DJANGO_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  skipTrailingSlashRedirect: true,
  async rewrites() {
    return [
      {
        source: "/backend-api/:path*/",
        destination: `${DJANGO_URL}/api/:path*/`,
      },
      {
        source: "/backend-api/:path*",
        destination: `${DJANGO_URL}/api/:path*`,
      },
      {
        source: "/api/:path*/",
        destination: `${DJANGO_URL}/api/:path*/`,
      },
      {
        source: "/api/:path*",
        destination: `${DJANGO_URL}/api/:path*`,
      },
    ];
  },
  experimental: {
    agentFeedback: true,
  },
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
