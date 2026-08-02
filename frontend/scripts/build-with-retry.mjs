import { rmSync } from "node:fs";
import { spawnSync } from "node:child_process";

const MAX_ATTEMPTS = 3;

for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
  rmSync(".next", { recursive: true, force: true });

  const result = spawnSync("npx", ["next", "build"], {
    stdio: "inherit",
    shell: process.platform === "win32",
  });

  if (result.status === 0) {
    process.exit(0);
  }

  if (attempt < MAX_ATTEMPTS) {
    console.error(
      `\n[next-build] Attempt ${attempt}/${MAX_ATTEMPTS} failed (exit ${result.status}). ` +
        `This is a known intermittent Next.js standalone-output race; retrying...\n`,
    );
  } else {
    process.exit(result.status ?? 1);
  }
}
