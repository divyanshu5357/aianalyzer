import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_API_URL || "http://13.53.205.56:8000";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["172.26.21.85", "localhost:3000", "127.0.0.1:3000"],
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
