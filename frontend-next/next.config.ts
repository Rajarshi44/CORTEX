import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,
  // The repo root holds its own lockfile for the `concurrently` scripts that start the backend and
  // this app together. Turbopack sees two lockfiles, picks the outer one and warns on every start;
  // saying outright that this directory is the workspace keeps the dev console clean.
  turbopack: { root: path.resolve(import.meta.dirname) },
  // The hosted build (Dockerfile) ships the console as static files that the API serves from its
  // own origin, so one service carries both and there is no cross-origin URL to wire up. Every
  // page is a client component, which is what makes a static export possible at all.
  ...(process.env.NEXT_OUTPUT === "export" ? { output: "export" as const } : {}),
};

export default nextConfig;
