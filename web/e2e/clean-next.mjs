// Removes the previous build output before the browser tests build the app.
// OneDrive can briefly lock files inside .next and make the build fail with EPERM, so deletion is retried.
import { rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const target = resolve(dirname(fileURLToPath(import.meta.url)), "..", ".next");

try {
  rmSync(target, { recursive: true, force: true, maxRetries: 8, retryDelay: 400 });
  console.log("Cleared .next");
} catch (error) {
  // Not fatal: the build may still succeed. Report so a failure is easy to diagnose.
  console.warn(`Could not clear .next (${error.code ?? error.message}). Continuing.`);
}
