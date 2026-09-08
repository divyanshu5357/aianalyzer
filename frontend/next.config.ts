import type { NextConfig } from "next";

const rawBackendUrl =
  process.env.BACKEND_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8000";

const backendUrl = rawBackendUrl.trim().replace(/\/+$/, "");

const nextConfig: NextConfig = {
  allowedDevOrigins: ["172.26.21.85", "localhost:3000", "127.0.0.1:3000"],
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
      {
        source: "/health",
        destination: `${backendUrl}/health`,
      },
    ];
  },
};

export default nextConfig;
