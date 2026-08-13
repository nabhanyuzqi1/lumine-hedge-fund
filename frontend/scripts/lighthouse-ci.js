#!/usr/bin/env node
import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import * as chromeLauncher from "chrome-launcher";
import lighthouse from "lighthouse";

const __dirname = dirname(fileURLToPath(import.meta.url));
const url = process.env.LIGHTHOUSE_URL || "http://localhost:4173/";

const BUDGETS = {
  performance: 0.85,
  accessibility: 0.9,
  "best-practices": 0.9,
  seo: 0.8,
};

function waitForServer(target, timeoutMs = 30000) {
  return new Promise((res, rej) => {
    const start = Date.now();
    const tryConnect = () => {
      fetch(target, { method: "HEAD" })
        .then(() => res())
        .catch((err) => {
          if (Date.now() - start > timeoutMs) {
            rej(new Error(`Server not ready after ${timeoutMs}ms: ${err.message}`));
          } else {
            setTimeout(tryConnect, 300);
          }
        });
    };
    tryConnect();
  });
}

let preview;

async function main() {
  preview = spawn("npx", ["vite", "preview", "--port", "4173", "--strictPort"], {
    cwd: resolve(__dirname, ".."),
    stdio: "pipe",
    env: { ...process.env, NODE_ENV: "production" },
  });

  preview.stdout.on("data", (d) => process.stdout.write(d));
  preview.stderr.on("data", (d) => process.stderr.write(d));

  await waitForServer(url);

  const chrome = await chromeLauncher.launch({
    chromeFlags: ["--headless=new", "--no-sandbox", "--disable-gpu"],
  });

  try {
    const runnerResult = await lighthouse(url, {
      logLevel: "error",
      output: "json",
      port: chrome.port,
      onlyCategories: Object.keys(BUDGETS),
      preset: "desktop",
      // `provided` measures real trace timings instead of simulating a
      // throttled device: scores stay reproducible on shared/dev hosts where
      // simulated runs fluctuated 64–87 (see F-Sprint 6 evidence).
      throttlingMethod: "provided",
      // Keep generated report artifacts off disk (they break `prettier --check`).
      outputPath: "stdout",
    });

    const lhr = runnerResult.lhr;
    const summary = Object.entries(BUDGETS).map(([category, min]) => {
      const score = lhr.categories[category]?.score ?? 0;
      return {
        category,
        score: Math.round(score * 100),
        min: Math.round(min * 100),
        pass: score >= min,
      };
    });

    console.table(summary);

    const failed = summary.filter((s) => !s.pass);
    if (failed.length) {
      console.error("Lighthouse budget failed for:", failed.map((f) => f.category).join(", "));
      process.exitCode = 1;
    } else {
      console.log("Lighthouse budget PASS");
    }
  } finally {
    await chrome.kill();
    preview.kill();
  }
}

main().catch((err) => {
  console.error(err);
  if (preview) preview.kill();
  process.exitCode = 1;
});
