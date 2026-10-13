// Runs in every window before the page, with Node access but isolated from the
// page. Exposes the little the renderer needs from the desktop shell.
import { contextBridge, ipcRenderer, webUtils } from "electron";

const argument = (name: string) => {
  const prefix = `--captainstems-${name}=`;
  const found = process.argv.find((arg) => arg.startsWith(prefix));
  return found ? found.slice(prefix.length) : undefined;
};

export interface ShellState {
  phase: "starting" | "bootstrap" | "error" | "ready";
  message: string;
  actions: Array<"bootstrap" | "continue" | "retry" | "quit">;
}

const shell = {
  /** Where the API listens. Set by the main process once the server is up. */
  api: argument("api"),
  /** The desktop app's version */
  version: argument("version"),
  /** The path of a dropped File, so the server reads it in place instead of receiving its bytes. */
  pathForFile: (file: File): string => webUtils.getPathForFile(file),
  // Loading screen <-> main process
  onLog: (callback: (line: string) => void) => {
    ipcRenderer.on("log", (_event, line: string) => callback(line));
  },
  onState: (callback: (state: ShellState) => void) => {
    ipcRenderer.on("state", (_event, state: ShellState) => callback(state));
  },
  action: (name: ShellState["actions"][number]) => ipcRenderer.send("action", name),
  /** From the Models view: install (or reinstall, after a flavor change) the model libraries */
  bootstrap: () => ipcRenderer.send("bootstrap"),
  /** Ask the feed now; the result is the state after the check (downloads continue in the background) */
  checkForUpdates: (): Promise<{ state: string; version?: string; message?: string }> =>
    ipcRenderer.invoke("update:check"),
};

export type Shell = typeof shell;

contextBridge.exposeInMainWorld("captainstems", shell);
