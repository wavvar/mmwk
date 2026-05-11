import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const root = process.cwd();
const forbidden = [
  { pattern: /python/i, label: "python runtime reference" },
  { pattern: /\.\.\/mmwk\/cli/, label: "../mmwk/cli runtime reference" },
  { pattern: /run\.sh/, label: "run.sh wrapper reference" },
  { pattern: /run\.ps1/, label: "run.ps1 wrapper reference" }
];
const scannedRoots = [
  "index.html",
  "src",
  "src-tauri/Cargo.toml",
  "src-tauri/build.rs",
  "src-tauri/src",
  "vite.config.ts",
  "tsconfig.json"
];
const sourceExtensions = new Set([
  ".css",
  ".html",
  ".js",
  ".json",
  ".mjs",
  ".rs",
  ".toml",
  ".ts",
  ".tsx"
]);

async function collectFiles(relativePath) {
  const absolutePath = path.join(root, relativePath);
  const entries = await readdir(absolutePath, { withFileTypes: true }).catch(() => []);

  if (entries.length === 0) {
    return sourceExtensions.has(path.extname(relativePath)) ? [relativePath] : [];
  }

  const files = [];
  for (const entry of entries) {
    if (entry.name === "node_modules" || entry.name === "dist" || entry.name === "target") {
      continue;
    }

    const childPath = path.join(relativePath, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await collectFiles(childPath)));
    } else if (sourceExtensions.has(path.extname(entry.name))) {
      files.push(childPath);
    }
  }

  return files;
}

const files = [];
for (const scannedRoot of scannedRoots) {
  files.push(...(await collectFiles(scannedRoot)));
}

const violations = [];
for (const file of files) {
  const body = await readFile(path.join(root, file), "utf8");
  for (const rule of forbidden) {
    if (rule.pattern.test(body)) {
      violations.push(`${file}: ${rule.label}`);
    }
  }
}

if (violations.length > 0) {
  console.error("Forbidden Python or CLI-wrapper runtime dependency found:");
  for (const violation of violations) {
    console.error(`- ${violation}`);
  }
  process.exit(1);
}
