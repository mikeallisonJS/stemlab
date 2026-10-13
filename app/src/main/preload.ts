// Runs in every window before the page, with Node access but isolated from the
// page. Exposes the little the renderer needs from the desktop shell.
import { contextBridge, ipcRenderer, webUtils } from "electron";

const apiArg = process.argv.find((arg) => arg.startsWith("--captainstems-api="));

export interface ShellState {
  phase: "starting" | "bootstrap" | "error" | "ready";
  message: string;
  actions: Array<"bootstrap" | "continue" | "retry" | "quit">;
}

const shell = {
  /** Where the API listens. Set by the main process once the server is up. */
  api: apiArg ? apiArg.slice("--captainstems-api=".length) : undefined,
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
};

export type Shell = typeof shell;

contextBridge.exposeInMainWorld("captainstems", shell);
