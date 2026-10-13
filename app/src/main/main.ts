// The desktop shell: starts the API server as a child process, waits until it
// answers, then shows the UI. The renderer is the same React app that runs in
// a browser; the server is `python -m captainstems serve` on a free port.
//
// Where the Python environment comes from, in order:
//   CAPTAINSTEMS_API     an already running server; nothing is spawned
//   CAPTAINSTEMS_PYTHON  a python interpreter with captainstems installed
//   packaged app         its own environment under the user data folder,
//                        created on the first start (python.ts)
//   <repo>/.venv         the development environment made by `uv sync`
//   uv                   `uv run captainstems serve` in the repository
import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import net from "node:net";
import path from "node:path";

import { BrowserWindow, app, dialog, ipcMain, shell } from "electron";

import loadingHtml from "./loading.html";
import type { ShellState } from "./preload";
import { type Python, managedPython } from "./python";

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const PRELOAD = path.join(__dirname, "preload.cjs");
const DEV_UI = "http://localhost:5173/";
const LOG_LINES = 400;

let server: ChildProcess | null = null;
let apiUrl: string | null = null;
let loading: BrowserWindow | null = null;
let main: BrowserWindow | null = null;
const log: string[] = [];
let pendingAction: ((name: ShellState["actions"][number]) => void) | null = null;

// Logging and the loading screen ----------------------------------------------

function logLine(line: string): void {
  for (const part of line.replace(/\r\n?/g, "\n").split("\n")) {
    if (!part) continue;
    log.push(part);
    if (log.length > LOG_LINES) log.shift();
    loading?.webContents.send("log", part);
    if (!app.isPackaged) console.log(part);
  }
}

function setState(state: ShellState): void {
  loading?.webContents.send("state", state);
}

function status(message: string): void {
  setState({ phase: "starting", message, actions: [] });
}

function showLoading(): BrowserWindow {
  const win = new BrowserWindow({
    width: 640,
    height: 440,
    resizable: false,
    autoHideMenuBar: true,
    title: "CaptainStems",
    backgroundColor: "#16181d",
    webPreferences: { preload: PRELOAD, contextIsolation: true, sandbox: true },
  });
  win.loadURL("data:text/html;charset=utf-8," + encodeURIComponent(loadingHtml));
  win.webContents.on("did-finish-load", () => {
    for (const line of log) win.webContents.send("log", line);
  });
  win.on("closed", () => {
    loading = null;
    if (!main) app.quit();
  });
  return win;
}

/** Show a problem on the loading screen and wait for the user to pick an action. */
function ask(message: string, actions: ShellState["actions"], phase: ShellState["phase"] = "error") {
  return new Promise<ShellState["actions"][number]>((resolve) => {
    setState({ phase, message, actions });
    // Smoke-test aid: answer every question with this action, when it is offered
    const scripted = process.env.CAPTAINSTEMS_DEBUG_ANSWER as ShellState["actions"][number] | undefined;
    if (scripted && actions.includes(scripted)) return resolve(scripted);
    pendingAction = resolve;
  });
}

ipcMain.on("action", (_event, name: ShellState["actions"][number]) => {
  const resolve = pendingAction;
  pendingAction = null;
  if (name === "quit") app.quit();
  else resolve?.(name);
});

// The Python environment ------------------------------------------------------

/** Managed environment: the packaged app, or CAPTAINSTEMS_MANAGED=1 to try it from a checkout. */
function managed(): boolean {
  return app.isPackaged || Boolean(process.env.CAPTAINSTEMS_MANAGED);
}

/** The engine resources: the wheel, recipes, MSST and the built UI (see scripts/prepare-engine.mjs). */
function engineDir(): string {
  return process.env.CAPTAINSTEMS_ENGINE ?? path.join(process.resourcesPath, "engine");
}

function developmentPython(): Python | null {
  const explicit = process.env.CAPTAINSTEMS_PYTHON;
  if (explicit) return { command: explicit, args: ["-m", "captainstems"], describe: explicit, root: REPO_ROOT, env: {} };
  const venv = path.join(REPO_ROOT, ".venv", process.platform === "win32" ? "Scripts\\python.exe" : "bin/python");
  if (fs.existsSync(venv)) return { command: venv, args: ["-m", "captainstems"], describe: venv, root: REPO_ROOT, env: {} };
  const uv = spawnSync(process.platform === "win32" ? "where" : "which", ["uv"], { encoding: "utf8" });
  if (uv.status === 0 && uv.stdout.trim()) {
    const binary = uv.stdout.trim().split(/\r?\n/)[0];
    return {
      command: binary,
      args: ["run", "--project", REPO_ROOT, "captainstems"],
      describe: "uv run captainstems",
      root: REPO_ROOT,
      env: {},
    };
  }
  return null;
}

async function findPython(): Promise<Python> {
  if (managed()) {
    return managedPython(engineDir(), path.join(app.getPath("userData"), "python"), { log: logLine, status });
  }
  const python = developmentPython();
  if (!python) {
    throw new Error("No Python environment was found.\nRun `uv sync --extra server` in the repository (or install uv), then retry.");
  }
  return python;
}

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.once("error", reject);
    probe.listen(0, "127.0.0.1", () => {
      const address = probe.address();
      probe.close(() => (typeof address === "object" && address ? resolve(address.port) : reject(new Error("no port"))));
    });
  });
}

function fetchJson(url: string, timeoutMs = 2000): Promise<any> {
  return new Promise((resolve, reject) => {
    const request = http.get(url, { timeout: timeoutMs }, (response) => {
      let body = "";
      response.setEncoding("utf8");
      response.on("data", (chunk) => (body += chunk));
      response.on("end", () => {
        if (response.statusCode !== 200) return reject(new Error(`${url}: HTTP ${response.statusCode}`));
        try {
          resolve(JSON.parse(body));
        } catch (error) {
          reject(error);
        }
      });
    });
    request.on("timeout", () => request.destroy(new Error("timeout")));
    request.on("error", reject);
  });
}

function reachable(url: string): Promise<boolean> {
  return new Promise((resolve) => {
    const request = http.get(url, { timeout: 1500 }, (response) => {
      response.resume();
      resolve(true);
    });
    request.on("timeout", () => request.destroy());
    request.on("error", () => resolve(false));
  });
}

function servesHtml(url: string): Promise<boolean> {
  return new Promise((resolve) => {
    const request = http.get(url, { timeout: 2000 }, (response) => {
      response.resume();
      resolve(response.statusCode === 200 && /text\/html/.test(response.headers["content-type"] ?? ""));
    });
    request.on("timeout", () => request.destroy());
    request.on("error", () => resolve(false));
  });
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// The server ------------------------------------------------------------------

function pipe(child: ChildProcess): void {
  child.stdout?.setEncoding("utf8");
  child.stderr?.setEncoding("utf8");
  child.stdout?.on("data", logLine);
  child.stderr?.on("data", logLine);
}

function pythonEnv(python: Python): NodeJS.ProcessEnv {
  // Unbuffered, UTF-8 output so the log streams, and no colour codes in it
  return {
    ...process.env,
    PYTHONUNBUFFERED: "1",
    PYTHONIOENCODING: "utf-8",
    NO_COLOR: "1",
    TERM: "dumb",
    ...python.env,
  };
}

async function startServer(python: Python): Promise<string> {
  const port = await freePort();
  const url = `http://127.0.0.1:${port}`;
  logLine(`$ ${python.describe} serve --port ${port}`);
  server = spawn(python.command, [...python.args, "serve", "--port", String(port)], {
    cwd: python.root,
    env: pythonEnv(python),
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  pipe(server);
  let exited: string | null = null;
  server.on("exit", (code, signal) => {
    exited = `The server stopped (${signal ?? `exit code ${code}`}).`;
    if (main && !main.isDestroyed()) {
      dialog.showErrorBox("CaptainStems", `${exited}\n\n${log.slice(-15).join("\n")}`);
      app.quit();
    }
  });
  server.on("error", (error) => {
    exited = `The server could not be started: ${error.message}`;
  });

  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    if (exited) throw new Error(exited);
    try {
      await fetchJson(`${url}/system`);
      return url;
    } catch {
      await sleep(400);
    }
  }
  throw new Error("The server did not answer within 90 seconds.");
}

function stopServer(): void {
  if (!server || server.exitCode !== null || server.signalCode !== null) return;
  if (process.platform === "win32") {
    // Kill the tree: with `uv run` the interpreter is a grandchild
    spawnSync("taskkill", ["/pid", String(server.pid), "/T", "/F"], { windowsHide: true });
  } else {
    server.kill("SIGTERM");
  }
  server = null;
}

/** `captainstems bootstrap`: torch for the detected GPU, the model libraries, onnxruntime. */
function runBootstrap(python: Python): Promise<number> {
  return new Promise((resolve) => {
    logLine(`$ ${python.describe} bootstrap`);
    const child = spawn(python.command, [...python.args, "bootstrap"], {
      cwd: python.root,
      env: pythonEnv(python),
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    pipe(child);
    child.on("exit", (code) => resolve(code ?? 1));
    child.on("error", (error) => {
      logLine(error.message);
      resolve(1);
    });
  });
}

// The UI ----------------------------------------------------------------------

async function uiUrl(api: string, python: Python | null): Promise<string> {
  const override = process.env.ELECTRON_RENDERER_URL;
  if (override) return override;
  // Development: Vite's dev server with hot reload, when it is running
  if (!app.isPackaged && (await reachable(DEV_UI))) return DEV_UI;
  // Otherwise the server hosts app/dist, when it existed at its start
  if (!(await servesHtml(api + "/"))) {
    const built = fs.existsSync(path.join(python?.root ?? REPO_ROOT, "app", "dist", "index.html"));
    throw new Error(
      built
        ? `The server at ${api} does not host the UI (it was started before the UI was built). Restart it, or run \`pnpm dev\` in app/ and retry.`
        : "The UI is not built. Run `pnpm build` in app/ (or `pnpm dev` for hot reload) and retry.",
    );
  }
  return api + "/";
}

function showMain(url: string, api: string): BrowserWindow {
  const win = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 960,
    minHeight: 600,
    autoHideMenuBar: true,
    title: "CaptainStems",
    backgroundColor: "#16181d",
    show: false,
    webPreferences: {
      preload: PRELOAD,
      contextIsolation: true,
      sandbox: true,
      additionalArguments: [`--captainstems-api=${api}`],
    },
  });
  win.webContents.setWindowOpenHandler(({ url: target }) => {
    void shell.openExternal(target);
    return { action: "deny" };
  });
  win.once("ready-to-show", () => {
    win.show();
    loading?.close();
    loading = null;
    const screenshot = process.env.CAPTAINSTEMS_DEBUG_SCREENSHOT;
    if (screenshot) {
      // Smoke-test aid: save a picture of the window once the UI has rendered, then quit
      setTimeout(() => {
        void win.webContents
          .capturePage()
          .then((image) => fs.writeFileSync(screenshot, image.toPNG()))
          .finally(() => app.quit());
      }, 3000);
    }
  });
  win.on("closed", () => {
    main = null;
    app.quit();
  });
  void win.loadURL(url);
  return win;
}

// Startup ---------------------------------------------------------------------

async function start(): Promise<void> {
  loading = showLoading();
  status("Starting…");

  let python: Python | null = null;
  const attach = process.env.CAPTAINSTEMS_API;
  if (attach) {
    logLine(`Using the server at ${attach} (CAPTAINSTEMS_API)`);
    apiUrl = attach.replace(/\/$/, "");
  } else {
    while (!python) {
      try {
        python = await findPython();
      } catch (error) {
        logLine((error as Error).message);
        const choice = await ask((error as Error).message, ["retry", "quit"]);
        if (choice !== "retry") return;
      }
    }
    status("Starting the server…");
    while (!apiUrl) {
      try {
        apiUrl = await startServer(python);
      } catch (error) {
        stopServer();
        const choice = await ask((error as Error).message, ["retry", "quit"]);
        if (choice !== "retry") return;
      }
    }

    // First run: the GPU-specific libraries are installed on demand
    let system = await fetchJson(`${apiUrl}/system`).catch(() => null);
    while (system && !system.torch?.version) {
      const gpu = system.gpu ? `${system.gpu} (${system.flavor})` : "no GPU (cpu)";
      const choice = await ask(
        `The model libraries are not installed yet.\nDetected: ${gpu}. Installing torch and the backends takes a few minutes and a few GB.`,
        ["bootstrap", "continue", "quit"],
        "bootstrap",
      );
      if (choice !== "bootstrap") break;
      setState({ phase: "bootstrap", message: "Installing the model libraries…", actions: [] });
      const code = await runBootstrap(python);
      if (code !== 0) {
        const next = await ask("The installation failed. See the log above.", ["bootstrap", "continue", "quit"]);
        if (next !== "bootstrap") break;
        continue;
      }
      // The server imports torch at startup: restart it to pick the libraries up
      status("Restarting the server…");
      stopServer();
      apiUrl = null;
      while (!apiUrl) {
        try {
          apiUrl = await startServer(python);
        } catch (error) {
          const choice2 = await ask((error as Error).message, ["retry", "quit"]);
          if (choice2 !== "retry") return;
        }
      }
      system = await fetchJson(`${apiUrl}/system`).catch(() => null);
    }
  }

  setState({ phase: "ready", message: "Loading the interface…", actions: [] });
  while (!main) {
    try {
      main = showMain(await uiUrl(apiUrl, python), apiUrl);
    } catch (error) {
      const choice = await ask((error as Error).message, ["retry", "quit"]);
      if (choice !== "retry") return;
    }
  }
}

if (process.env.CAPTAINSTEMS_DATA) {
  // Testing aid: a user data folder other than the real one
  app.setPath("userData", process.env.CAPTAINSTEMS_DATA);
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    const win = main ?? loading;
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });
  app.on("before-quit", stopServer);
  app.on("will-quit", stopServer);
  app.on("window-all-closed", () => app.quit());
  process.on("exit", stopServer);
  void app.whenReady().then(() =>
    start().catch((error) => {
      dialog.showErrorBox("CaptainStems", String((error as Error).stack ?? error));
      app.quit();
    }),
  );
}
