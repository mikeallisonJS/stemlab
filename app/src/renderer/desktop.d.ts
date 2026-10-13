// What the desktop shell's preload script exposes (app/src/main/preload.ts).
// Absent in a browser.
interface CaptainStemsShell {
  api?: string;
  pathForFile: (file: File) => string;
}

interface Window {
  captainstems?: CaptainStemsShell;
}
