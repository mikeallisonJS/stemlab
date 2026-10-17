// Assembles build/engine, the resources the packaged app ships beside the
// Electron shell (electron-builder's extraResources):
//
//   stemlab-<version>-py3-none-any.whl   the engine, built with uv
//   recipes/                                  the example recipes
//   third_party/msst/                         the MSST submodule (its code and configs)
//   app/dist/                                 the built UI, hosted by the server
//   bin/ffmpeg[.exe]                          FFmpeg, when one is found (FFMPEG env or PATH)
//
// On the first start the app installs the wheel into its own Python environment
// and points STEMLAB_ROOT at this folder, which is laid out like the repository.
import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const APP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO = path.resolve(APP, "..");
const ENGINE = path.join(APP, "build", "engine");

function copy(from, to, skip = () => false) {
  for (const entry of fs.readdirSync(from, { withFileTypes: true })) {
    if (skip(entry.name)) continue;
    const source = path.join(from, entry.name);
    const target = path.join(to, entry.name);
    if (entry.isDirectory()) {
      fs.mkdirSync(target, { recursive: true });
      copy(source, target, skip);
    } else {
      fs.copyFileSync(source, target);
    }
  }
}

fs.rmSync(ENGINE, { recursive: true, force: true });
fs.mkdirSync(ENGINE, { recursive: true });

console.log("engine: building the wheel");
execFileSync("uv", ["build", "--wheel", "--project", REPO, "--out-dir", ENGINE], { stdio: "inherit" });
fs.rmSync(path.join(ENGINE, ".gitignore"), { force: true });

console.log("engine: recipes");
fs.mkdirSync(path.join(ENGINE, "recipes"));
copy(path.join(REPO, "recipes"), path.join(ENGINE, "recipes"));

const msst = path.join(REPO, "third_party", "msst");
if (!fs.existsSync(path.join(msst, "inference.py"))) {
  console.error("engine: third_party/msst is empty. Run: git submodule update --init third_party/msst");
  process.exit(1);
}
console.log("engine: MSST");
const msstTarget = path.join(ENGINE, "third_party", "msst");
fs.mkdirSync(msstTarget, { recursive: true });
copy(msst, msstTarget, (name) => [".git", ".github", "docs", "tests", "gui", "__pycache__"].includes(name));
// The backend reports the commit it wraps; without .git it reads this file
const commit = spawnSync("git", ["-C", msst, "rev-parse", "--short", "HEAD"], { encoding: "utf8" });
if (commit.status === 0) fs.writeFileSync(path.join(msstTarget, "COMMIT"), commit.stdout.trim() + "\n");

const dist = path.join(APP, "dist");
if (!fs.existsSync(path.join(dist, "index.html"))) {
  console.error("engine: app/dist is missing. Run: pnpm build");
  process.exit(1);
}
console.log("engine: UI");
fs.mkdirSync(path.join(ENGINE, "app", "dist"), { recursive: true });
copy(dist, path.join(ENGINE, "app", "dist"));

const exe = process.platform === "win32" ? "ffmpeg.exe" : "ffmpeg";
let ffmpeg = process.env.FFMPEG;
if (!ffmpeg) {
  const lookup = spawnSync(process.platform === "win32" ? "where" : "which", ["ffmpeg"], { encoding: "utf8" });
  if (lookup.status === 0) ffmpeg = lookup.stdout.trim().split(/\r?\n/)[0];
}
if (ffmpeg && fs.existsSync(ffmpeg)) {
  console.log(`engine: FFmpeg from ${ffmpeg}`);
  fs.mkdirSync(path.join(ENGINE, "bin"), { recursive: true });
  fs.copyFileSync(ffmpeg, path.join(ENGINE, "bin", exe));
} else {
  console.warn("engine: no FFmpeg found (FFMPEG env or PATH); the app will look for one on the user's PATH");
}

console.log(`engine: ready in ${ENGINE}`);
