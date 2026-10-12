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
              <tr><th>Torch flavor</th><td>{system.flavor}{system.flavor_source === "override" ? ` (override; detected ${system.detected_flavor})` : ""}</td></tr>
              <tr><th>torch</th><td>{system.torch.version ? `${system.torch.version} · ${system.torch.cuda ? "CUDA" : system.torch.mps ? "MPS" : "CPU only"}` : "not installed: run captainstems bootstrap"}</td></tr>
              <tr><th>onnxruntime</th><td>{system.onnxruntime.version ? `${system.onnxruntime.version} · ${system.onnxruntime.providers.map((p) => p.replace("ExecutionProvider", "")).join(", ")}` : "not installed"}</td></tr>
              <tr><th>FFmpeg</th><td>{system.ffmpeg ?? "not found"}</td></tr>
              {Object.entries(system.backends).map(([name, versions]) => (
                <tr key={name}><th>backend {name}</th><td>{"error" in versions ? `unavailable: ${versions.error}` : Object.entries(versions).map(([k, v]) => `${k} ${v}`).join(", ")}</td></tr>
              ))}
              <tr><th>Data folder</th><td>{system.home} · cache {size(system.cache_bytes) || "empty"}</td></tr>
            </tbody>
          </table>
        ) : <p className="muted">Loading...</p>}
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
