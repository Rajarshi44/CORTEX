import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The repo root holds its own lockfile for the `concurrently` scripts that start the backend and
  // this app together. Turbopack sees two lockfiles, picks the outer one and warns on every start;
  // saying outright that this directory is the workspace keeps the dev console clean.
  turbopack: { root: path.resolve(import.meta.dirname) },
};

export default nextConfig;
