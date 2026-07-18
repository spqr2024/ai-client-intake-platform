import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emits a self-contained server bundle so the production image ships only
  // the modules actually imported (see frontend/Dockerfile).
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,

  async headers() {
    // Defence-in-depth for the browser tier. The API sets its own headers;
    // these protect the pages that render user- and AI-generated text.
    const apiOrigin = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), interest-cohort=()",
          },
          {
            // Next.js requires 'unsafe-inline' for its style handling and
            // 'unsafe-eval' only in dev; connect-src is pinned to the API so a
            // successful XSS still cannot exfiltrate to an attacker's host.
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              `connect-src 'self' ${apiOrigin}`,
              "img-src 'self' data: blob: https:",
              "style-src 'self' 'unsafe-inline'",
              `script-src 'self' 'unsafe-inline'${
                process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : ""
              }`,
              "font-src 'self' data:",
              "object-src 'none'",
              "base-uri 'self'",
              "form-action 'self'",
              "frame-ancestors 'none'",
            ].join("; "),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
