// The Python environment the packaged app owns, created under the user data
// folder on the first start: a pinned uv, a uv-managed CPython and the
// captainstems wheel bundled with the app. The GPU-specific libraries come
// later through `captainstems bootstrap`, from the loading screen.
//
// A development checkout needs none of this: main.ts uses the repository's
// .venv there.
import { spawn } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import https from "node:https";
import path from "node:path";
import { pathToFileURL } from "node:url";

export const UV_VERSION = "0.12.15";
export const PYTHON_VERSION = "3.12";

export interface Python {
  command: string;
  args: string[];
  describe: string;
  /** The folder the server runs in and, for the packaged app, CAPTAINSTEMS_ROOT */
  root: string;
  env: NodeJS.ProcessEnv;
}

export interface Progress {
  log: (line: string) => void;
  status: (message: string) => void;
}

const WINDOWS = process.platform === "win32";

function uvAsset(): string {
  const arch = process.arch === "arm64" ? "aarch64" : "x86_64";
  if (WINDOWS) return `uv-${arch}-pc-windows-msvc.zip`;
  if (process.platform === "darwin") return `uv-${arch}-apple-darwin.tar.gz`;
  return `uv-${arch}-unknown-linux-gnu.tar.gz`;
}

function download(url: string, file: string, log: (line: string) => void, redirects = 0): Promise<void> {
  return new Promise((resolve, reject) => {
    https
      .get(url, (response) => {
        const status = response.statusCode ?? 0;
        if ([301, 302, 303, 307, 308].includes(status) && response.headers.location && redirects < 5) {
          response.resume();
          return resolve(download(response.headers.location, file, log, redirects + 1));
        }
        if (status !== 200) {
          response.resume();
          return reject(new Error(`${url}: HTTP ${status}`));
        }
        const total = Number(response.headers["content-length"] ?? 0);
        let received = 0;
        let nextReport = 0.25;
        const out = fs.createWriteStream(file);
        response.on("data", (chunk: Buffer) => {
          received += chunk.length;
          if (total && received / total >= nextReport) {
            log(`  ${Math.round((received / total) * 100)}%`);
            nextReport += 0.25;
          }
        });
        response.pipe(out);
        out.on("finish", () => resolve());
        out.on("error", reject);
        response.on("error", reject);
      })
      .on("error", reject);
  });
}

function run(command: string, args: string[], env: NodeJS.ProcessEnv, log: (line: string) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    log(`$ ${path.basename(command)} ${args.join(" ")}`);
    const child = spawn(command, args, { env, stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
    const forward = (data: Buffer) => {
      for (const line of data.toString("utf8").split(/\r?\n/)) if (line.trim()) log(line);
    };
    child.stdout.on("data", forward);
    child.stderr.on("data", forward);
    child.on("error", reject);
    child.on("exit", (code) => (code === 0 ? resolve() : reject(new Error(`${path.basename(command)} failed (exit code ${code})`))));
  });
}

async function extract(archive: string, into: string, env: NodeJS.ProcessEnv, log: (line: string) => void): Promise<void> {
  fs.mkdirSync(into, { recursive: true });
  if (archive.endsWith(".zip")) {
    await run("powershell", ["-NoProfile", "-NonInteractive", "-Command", `Expand-Archive -LiteralPath '${archive}' -DestinationPath '${into}' -Force`], env, log);
  } else {
    await run("tar", ["-xzf", archive, "-C", into], env, log);
  }
}

function findFile(folder: string, name: string): string | null {
  for (const entry of fs.readdirSync(folder, { withFileTypes: true })) {
    const full = path.join(folder, entry.name);
    if (entry.isFile() && entry.name === name) return full;
    if (entry.isDirectory()) {
      const found = findFile(full, name);
      if (found) return found;
    }
  }
  return null;
}

function sha256(file: string): string {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

function readText(file: string): string | null {
  try {
    return fs.readFileSync(file, "utf8").trim();
  } catch {
    return null;
  }
}

/** The bundled ffmpeg, when the build put one in engine/bin. */
export function bundledFfmpeg(engineDir: string): string | null {
  const candidate = path.join(engineDir, "bin", WINDOWS ? "ffmpeg.exe" : "ffmpeg");
  return fs.existsSync(candidate) ? candidate : null;
}

/**
 * Make sure uv, the Python environment and the bundled captainstems wheel are
 * in place under `dataDir`, doing only what is missing or outdated.
 */
export async function managedPython(engineDir: string, dataDir: string, progress: Progress): Promise<Python> {
  const uvDir = path.join(dataDir, "uv");
  const uv = path.join(uvDir, WINDOWS ? "uv.exe" : "uv");
  const venv = path.join(dataDir, "venv");
  const python = path.join(venv, WINDOWS ? "Scripts\\python.exe" : "bin/python");
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    // Everything uv downloads stays in the app's data folder
    UV_PYTHON_INSTALL_DIR: path.join(dataDir, "cpython"),
    UV_CACHE_DIR: path.join(dataDir, "cache"),
    UV_NO_PROGRESS: "1",
    NO_COLOR: "1",
  };
  fs.mkdirSync(dataDir, { recursive: true });

  if (readText(path.join(uvDir, "VERSION")) !== UV_VERSION || !fs.existsSync(uv)) {
    progress.status(`Downloading uv ${UV_VERSION} (first run)…`);
    const asset = uvAsset();
    const url = `https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${asset}`;
    const archive = path.join(dataDir, asset);
    const unpacked = path.join(dataDir, "uv-unpacked");
    progress.log(`Downloading ${url}`);
    await download(url, archive, progress.log);
    fs.rmSync(unpacked, { recursive: true, force: true });
    await extract(archive, unpacked, env, progress.log);
    const binary = findFile(unpacked, WINDOWS ? "uv.exe" : "uv");
    if (!binary) throw new Error(`The uv archive ${asset} contains no uv binary`);
    fs.mkdirSync(uvDir, { recursive: true });
    fs.copyFileSync(binary, uv);
    if (!WINDOWS) fs.chmodSync(uv, 0o755);
    fs.writeFileSync(path.join(uvDir, "VERSION"), UV_VERSION);
    fs.rmSync(unpacked, { recursive: true, force: true });
    fs.rmSync(archive, { force: true });
  }

  if (!fs.existsSync(python)) {
    progress.status(`Installing Python ${PYTHON_VERSION} (first run)…`);
    await run(uv, ["venv", "--python", PYTHON_VERSION, "--managed-python", "--seed", venv], env, progress.log);
  }

  const wheel = fs.readdirSync(engineDir).find((name) => name.startsWith("captainstems-") && name.endsWith(".whl"));
  if (!wheel) throw new Error(`No captainstems wheel in ${engineDir}. The app was not built with prepare-engine.`);
  const wheelPath = path.join(engineDir, wheel);
  const installed = path.join(venv, "captainstems.wheel.sha256");
  const digest = sha256(wheelPath);
  if (readText(installed) !== digest) {
    progress.status("Installing CaptainStems…");
    await run(
      uv,
      ["pip", "install", "--python", python, "--reinstall-package", "captainstems", `captainstems[server] @ ${pathToFileURL(wheelPath).href}`],
      env,
      progress.log,
    );
    fs.writeFileSync(installed, digest);
  }

  const ffmpeg = bundledFfmpeg(engineDir);
  return {
    command: python,
    args: ["-m", "captainstems"],
    describe: python,
    root: engineDir,
    env: {
      CAPTAINSTEMS_ROOT: engineDir,
      CAPTAINSTEMS_UV: uv,
      UV_PYTHON_INSTALL_DIR: env.UV_PYTHON_INSTALL_DIR,
      UV_CACHE_DIR: env.UV_CACHE_DIR,
      UV_NO_PROGRESS: "1",
      ...(ffmpeg ? { CAPTAINSTEMS_FFMPEG: ffmpeg } : {}),
    },
  };
}
