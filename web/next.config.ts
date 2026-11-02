import type { NextConfig } from "next";

const backendUrl = process.env.HERMES_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Tailwind v4 is compiled by its Turbopack loader. It applies only to our own stylesheet, so it never
  // touches generated font CSS or library CSS.
  turbopack: {
    rules: {
      "globals.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // The browser talks only to this origin. API calls are proxied to the backend so the
  // session cookie stays first-party and no cross-origin configuration is needed.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
};

export default nextConfig;
