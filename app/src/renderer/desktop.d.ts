// What the desktop shell's preload script exposes (app/src/main/preload.ts).
// Absent in a browser.
interface StemlabShell {
  api?: string;
  pathForFile: (file: File) => string;
  /** Use instead of localStorage: the page's origin changes with the server's port on every launch */
  storage: Pick<Storage, "getItem" | "setItem">;
  /** Run `stemlab bootstrap` and restart the server; the shell shows its progress */
  bootstrap: () => void;
  version?: string;
  checkForUpdates: () => Promise<{ state: string; version?: string; message?: string }>;
}

interface Window {
  stemlab?: StemlabShell;
}
