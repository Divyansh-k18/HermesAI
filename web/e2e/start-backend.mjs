// Starts the Hermes backend against a fresh SQLite database for end-to-end tests.
// Cross-platform: resolves the virtualenv layout for Windows and POSIX.
import { spawn, spawnSync } from "node:child_process";
import { existsSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const backend = resolve(here, "..", "..", "backend");
const bin = process.platform === "win32" ? join(backend, ".venv", "Scripts") : join(backend, ".venv", "bin");
const exe = (name) => join(bin, process.platform === "win32" ? `${name}.exe` : name);

const dbFile = join(backend, "e2e.db");
if (existsSync(dbFile)) rmSync(dbFile);

const env = {
  ...process.env,
  HERMES_ENV: "test",
  HERMES_DATABASE_URL: "sqlite:///./e2e.db",
  HERMES_LOGIN_RATE_LIMIT: "1000",
};

const migrate = spawnSync(exe("alembic"), ["upgrade", "head"], { cwd: backend, env, stdio: "inherit" });
if (migrate.status !== 0) process.exit(migrate.status ?? 1);

const server = spawn(
  exe("python"),
  ["-m", "uvicorn", "app.main:create_app", "--factory", "--port", "8000"],
  { cwd: backend, env, stdio: "inherit" },
);
server.on("exit", (code) => process.exit(code ?? 0));
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => server.kill());
