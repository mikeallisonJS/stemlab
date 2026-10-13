import { useState } from "react";

import { api } from "../api";
import type { ModelInfo, ModelsResponse, SystemInfo } from "../types";

interface Props {
  system: SystemInfo | null;
  models: ModelsResponse | null;
  onChanged: () => void;
}

function size(bytes: number | undefined): string {
  if (!bytes) return "";
  return bytes > 1073741824 ? `${(bytes / 1073741824).toFixed(1)} GB` : `${Math.round(bytes / 1048576)} MB`;
}

const EMPTY = { id: "", backend: "msst", arch: "", config: "", weights: "", stems: "", license: "", notes: "" };
const FLAVORS = ["cuda", "rocm", "mps", "cpu"];

/** Desktop app only: its version and a manual update check (checks also run on their own). */
function Updates({ shell }: { shell: CaptainStemsShell }) {
  const [result, setResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const check = async () => {
    setBusy(true);
    const status = await shell.checkForUpdates();
    setResult(
      status.state === "disabled" ? "Updates are not checked in a development build."
        : status.state === "none" ? "Up to date."
        : status.state === "available" ? `Downloading ${status.version}...`
        : status.state === "downloaded" ? `${status.version} is downloaded and installs on restart.`
        : status.state === "error" ? `Could not check: ${status.message}`
        : "Checking...",
    );
    setBusy(false);
  };
  return (
    <p className="muted updates">
      Desktop app {shell.version ?? ""} · <button className="small" disabled={busy} onClick={check}>Check for updates</button> {result}
    </p>
  );
}

/** The Doctor part of the view: override what was detected, then (re)install the libraries for it. */
function Doctor({ system, onChanged }: { system: SystemInfo; onChanged: () => void }) {
  const [flavor, setFlavor] = useState(system.flavor_source === "override" ? system.flavor : "auto");
  const [target, setTarget] = useState(system.rocm_target ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const shell = window.captainstems;
  const windows = system.os === "Windows";
  const changed = flavor !== (system.flavor_source === "override" ? system.flavor : "auto") || (target || "") !== (system.rocm_target ?? "");
  const installed = Boolean(system.torch.version);
  // The installed torch has to match the chosen flavor: ROCm and CUDA builds both report "cuda"
  const matches = installed && (system.flavor === "cpu" || system.flavor === "mps" || system.torch.cuda);

  const apply = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.setSystemConfig({ torch_flavor: flavor === "auto" ? null : flavor, rocm_target: target.trim() || null });
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
    setBusy(false);
  };

  return (
    <div className="doctor">
      <div className="form doctor-form">
        <label className="field"><span className="field-name">Torch flavor</span>
          <select value={flavor} onChange={(e) => setFlavor(e.target.value)}>
            <option value="auto">auto (detected: {system.detected_flavor})</option>
            {FLAVORS.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
        {windows && (flavor === "rocm" || (flavor === "auto" && system.detected_flavor === "rocm")) && (
          <label className="field"><span className="field-name">ROCm target</span>
            <input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="detected, e.g. gfx1151" />
            <span className="field-help">AMD's Windows wheels are built per GPU: gfx1151 Ryzen AI Max, gfx1150 Ryzen AI 300, gfx110X RX 7000, gfx120X RX 9000</span>
          </label>
        )}
        <button className="small" disabled={busy || !changed} onClick={apply}>Apply</button>
      </div>
      {error && <div className="banner error" role="alert">{error}</div>}
      {system.bootstrap?.error && <div className="banner warning">{system.bootstrap.error}</div>}
      {!matches && !system.bootstrap?.error && (
        <div className="banner warning">
          {installed ? `The installed torch (${system.torch.version}) is not a ${system.flavor} build.` : "The model libraries are not installed."}
          {shell ? (
            <div><button className="small primary" onClick={() => shell.bootstrap()}>Install the model libraries</button></div>
          ) : (
            <div>Run <code>captainstems bootstrap</code>, which does:<pre>{system.bootstrap?.commands?.join("\n")}</pre></div>
          )}
        </div>
      )}
      {matches && shell && (
        <p className="muted">Changed the flavor? <button className="small" onClick={() => shell.bootstrap()}>Reinstall the model libraries</button></p>
      )}
    </div>
  );
}

/** The registry and what the machine can run: fetch curated models, add your own. */
export function ModelsView({ system, models, onChanged }: Props) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState(EMPTY);

  const act = async (id: string, action: () => Promise<unknown>) => {
    setBusy(id);
    setError(null);
    try {
      await action();
      onChanged();
    } catch (e) {
      setError(`${id}: ${(e as Error).message}`);
    }
    setBusy(null);
  };

  const add = () => {
    const name = (path: string) => path.replace(/^.*[\\/]/, "");
    const weights = form.weights.split(/[\n;]/).map((item) => item.trim().replace(/^"|"$/g, "")).filter(Boolean);
    const config = form.config.trim().replace(/^"|"$/g, "");
    const files: Record<string, string> = Object.fromEntries(weights.map((path) => [name(path), path]));
    if (config) files[name(config)] = config;
    const manifest: Record<string, unknown> = {
      id: form.id.trim(),
      name: form.id.trim(),
      backend: form.backend,
      arch: form.arch.trim(),
      weights: weights.length === 1 ? name(weights[0]) : weights.map(name),
      stems: form.stems.split(",").map((stem) => stem.trim()).filter(Boolean),
      license: form.license.trim(),
      notes: form.notes.trim(),
    };
    if (config) manifest.config = name(config);
    act(form.id || "new model", () => api.addModel(manifest, files).then(() => setForm(EMPTY)));
  };

  const row = (model: ModelInfo) => (
    <tr key={model.id}>
      <td><strong>{model.id}</strong><div className="muted">{model.notes}</div></td>
      <td>{model.backend}<div className="muted">{model.arch}</div></td>
      <td>{model.stems.join(", ")}</td>
      <td className="muted">{model.license}</td>
      <td>
        {model.installed ? (
          <button className="small" disabled={busy !== null} onClick={() => {
            if (window.confirm(`Delete ${model.id} and its weights?`)) act(model.id, () => api.removeModel(model.id));
          }}>Remove</button>
        ) : model.curated ? (
          <button className="small primary" disabled={busy !== null} onClick={() => act(model.id, () => api.fetchModel(model.id))}>
            {busy === model.id ? "Downloading..." : `Fetch ${size(model.download_bytes)}`}
          </button>
        ) : (
          <span className="muted">incomplete</span>
        )}
      </td>
    </tr>
  );

  return (
    <div className="models-view">
      <section>
        <h3>This machine</h3>
        {system ? (
          <table className="facts">
            <tbody>
              <tr><th>GPU</th><td>{system.gpu ? `${system.gpu}${system.vram_mb ? ` (${Math.round(system.vram_mb / 1024)} GB)` : ""}` : "none detected"}</td></tr>
              <tr><th>Torch flavor</th><td>{system.flavor}{system.flavor_source === "override" ? ` (override; detected ${system.detected_flavor})` : ""}{system.rocm_target ? ` · ${system.rocm_target}` : ""}</td></tr>
              <tr><th>torch</th><td>{system.torch.version ? `${system.torch.version} · ${system.torch.cuda ? (system.torch.hip ? "ROCm" : "CUDA") : system.torch.mps ? "MPS" : "CPU only"}` : "not installed: run captainstems bootstrap"}</td></tr>
              <tr><th>onnxruntime</th><td>{system.onnxruntime.version ? `${system.onnxruntime.version} · ${system.onnxruntime.providers.map((p) => p.replace("ExecutionProvider", "")).join(", ")}` : "not installed"}</td></tr>
              <tr><th>FFmpeg</th><td>{system.ffmpeg ?? "not found"}</td></tr>
              {Object.entries(system.backends).map(([name, versions]) => (
                <tr key={name}><th>backend {name}</th><td>{"error" in versions ? `unavailable: ${versions.error}` : Object.entries(versions).map(([k, v]) => `${k} ${v}`).join(", ")}</td></tr>
              ))}
              <tr><th>Data folder</th><td>{system.home} · cache {size(system.cache_bytes) || "empty"}</td></tr>
            </tbody>
          </table>
        ) : <p className="muted">Loading...</p>}
        {system && <Doctor key={`${system.flavor}:${system.flavor_source}:${system.rocm_target ?? ""}`} system={system} onChanged={onChanged} />}
        {window.captainstems && <Updates shell={window.captainstems} />}
      </section>

      <section>
        <h3>Models</h3>
        <p className="muted">Registry: {models?.root}. Weights are downloaded from their publishers and verified by SHA-256; they carry their own licenses.</p>
        {error && <div className="banner error" role="alert">{error}</div>}
        {models && Object.entries(models.problems).map(([id, problem]) => (
          <div key={id} className="banner warning">{id}: broken manifest: {problem}</div>
        ))}
        <table className="models">
          <thead><tr><th>id</th><th>backend</th><th>stems</th><th>license</th><th /></tr></thead>
          <tbody>{models?.models.map(row)}</tbody>
        </table>
      </section>

      <section>
        <h3>Add your own model</h3>
        <p className="muted">Copies the files into the registry and writes the manifest. For MSST give the architecture (its --model_type, e.g. mel_band_roformer) and the config YAML; for Demucs the bag .yaml as config and its .th files as weights.</p>
        <div className="form add-model">
          <label className="field"><span className="field-name">id</span><input value={form.id} onChange={(e) => setForm({ ...form, id: e.target.value })} placeholder="my-vocal-model" /></label>
          <label className="field"><span className="field-name">backend</span>
            <select value={form.backend} onChange={(e) => setForm({ ...form, backend: e.target.value })}>
              <option value="msst">msst</option><option value="demucs">demucs</option><option value="onnx">onnx</option>
            </select>
          </label>
          <label className="field"><span className="field-name">arch</span><input value={form.arch} onChange={(e) => setForm({ ...form, arch: e.target.value })} placeholder="mel_band_roformer" /></label>
          <label className="field"><span className="field-name">stems</span><input value={form.stems} onChange={(e) => setForm({ ...form, stems: e.target.value })} placeholder="vocals" /></label>
          <label className="field wide"><span className="field-name">weights</span><input value={form.weights} onChange={(e) => setForm({ ...form, weights: e.target.value })} placeholder="path to the checkpoint; separate several with ;" /></label>
          <label className="field wide"><span className="field-name">config</span><input value={form.config} onChange={(e) => setForm({ ...form, config: e.target.value })} placeholder="path to the config YAML (not needed for onnx)" /></label>
          <label className="field"><span className="field-name">license</span><input value={form.license} onChange={(e) => setForm({ ...form, license: e.target.value })} /></label>
          <label className="field"><span className="field-name">notes</span><input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></label>
        </div>
        <button className="primary" disabled={busy !== null || !form.id || !form.weights || !form.stems} onClick={add}>Add model</button>
      </section>
    </div>
  );
}
