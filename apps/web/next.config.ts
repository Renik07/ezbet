import type { NextConfig } from "next";

function getServerActionAllowedOrigins() {
  const configuredHost = process.env.EZBET_PUBLIC_HOST?.trim();
  const hosts = [
    configuredHost,
    "localhost:3000",
    "127.0.0.1:3000",
    "localhost",
    "127.0.0.1"
  ].filter((value): value is string => Boolean(value));

  return Array.from(new Set(hosts));
}

const nextConfig: NextConfig = {
  typedRoutes: true,
  images: {
    remotePatterns: [{ protocol: "https", hostname: "leon.ru", pathname: "/blog/uploads/logotypes/**" }]
  },
  experimental: {
    serverActions: {
      allowedOrigins: getServerActionAllowedOrigins()
    }
  }
};

export default nextConfig;
