// What the desktop shell's preload script exposes (app/src/main/preload.ts).
// Absent in a browser.
interface CaptainStemsShell {
  api?: string;
  pathForFile: (file: File) => string;
  /** Run `captainstems bootstrap` and restart the server; the shell shows its progress */
  bootstrap: () => void;
}

interface Window {
  captainstems?: CaptainStemsShell;
}
