import { useState } from "react";

import { api } from "../api";
import { FilePicker } from "../components/FilePicker";
import type { InputFile, Job, JobEvent, RecipeData, Validation } from "../types";

interface Props {
  recipe: RecipeData;
  validation: Validation | null;
  jobs: Job[];
  logs: Record<string, JobEvent[]>;
  inputs: InputFile[];
  setInputs: (inputs: InputFile[]) => void;
  onJobsCreated: (jobs: Job[]) => void;
  onRefresh: () => void;
  onShowResults: (job: Job) => void;
}

function clock(seconds: number | undefined | null): string {
  if (seconds === undefined || seconds === null) return "";
  return seconds < 60 ? `${seconds.toFixed(1)} s` : `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, "0")}`;
}

function describe(event: JobEvent): string | null {
  switch (event.type) {
    case "job_queued":
      return "queued";
    case "run_started":
      return "started";
    case "node_started":
      return `${event.node}: started`;
    case "node_status":
      return `${event.node}: ${event.status}`;
    case "node_finished":
      return `${event.node}: ${event.cached ? "from cache" : "done"} (${clock(event.seconds)})`;
    case "warning":
      return `${event.node}: WARNING ${event.message}`;
    case "run_finished":
      return `finished in ${clock(event.seconds)}`;
    case "run_failed":
      return `FAILED: ${event.error}`;
    case "run_cancelled":
      return "cancelled";
    default:
      return null;
  }
}

export function RunView({ recipe, validation, jobs, logs, inputs, setInputs, onJobsCreated, onRefresh, onShowResults }: Props) {
  const [outDir, setOutDir] = useState("");
  const [useCache, setUseCache] = useState(true);
  const [picker, setPicker] = useState<"files" | "folder" | null>(null);
  const [typedPath, setTypedPath] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const addPaths = async (paths: string[]) => {
    const known = new Set(inputs.map((item) => item.path));
    const added: InputFile[] = [];
    for (const path of paths) {
      if (known.has(path)) continue;
      try {
        added.push(await api.audioInfo(path));
        known.add(path);
      } catch (e) {
        setError((e as Error).message);
      }
    }
    if (added.length) setInputs([...inputs, ...added]);
  };

  const upload = async (files: FileList | File[]) => {
    setBusy(true);
    setError(null);
    const added: InputFile[] = [];
    for (const file of Array.from(files)) {
      try {
        added.push(await api.upload(file));
      } catch (e) {
        setError(`${file.name}: ${(e as Error).message}`);
      }
    }
    setInputs([...inputs, ...added]);
    setBusy(false);
  };

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await api.createJobs(recipe, inputs.map((item) => item.path), outDir.trim() || null, useCache);
      onJobsCreated(created);
      setSelectedId(created[0]?.id ?? null);
    } catch (e) {
      setError((e as Error).message);
    }
    setBusy(false);
  };

  const ordered = [...jobs].reverse();
  const selected = jobs.find((job) => job.id === selectedId) ?? ordered[0] ?? null;
  const lastFolder = inputs.length ? inputs[inputs.length - 1].path.replace(/[\\/][^\\/]*$/, "") : undefined;

  return (
    <div className="run-view">
      <section className="run-setup">
        <h3>Run “{recipe.name}”</h3>
        {validation && !validation.ok && <div className="banner error">The recipe has a problem: {validation.error}</div>}

        <div className={`drop${dragging ? " over" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            if (!e.dataTransfer.files.length) return;
            // In the desktop app the server reads dropped files where they are; a browser can only send their bytes
            const shell = window.captainstems;
            if (shell) addPaths(Array.from(e.dataTransfer.files).map(shell.pathForFile));
            else upload(e.dataTransfer.files);
          }}>
          Drop audio files here
          <div className="drop-actions">
            <button onClick={() => setPicker("files")}>Browse...</button>
            <form onSubmit={(e) => {
              e.preventDefault();
              if (typedPath.trim()) addPaths([typedPath.trim().replace(/^"|"$/g, "")]).then(() => setTypedPath(""));
            }}>
              <input value={typedPath} onChange={(e) => setTypedPath(e.target.value)} placeholder="or paste a file path and press Enter" aria-label="File path" />
            </form>
          </div>
        </div>

        <ul className="inputs">
          {inputs.map((item) => (
            <li key={item.path} title={item.path}>
              <span className="grow">{item.name}</span>
              <span className="muted">{item.duration ? clock(item.duration) : ""}</span>
              <button className="small" title="Remove" onClick={() => setInputs(inputs.filter((other) => other.path !== item.path))}>×</button>
            </li>
          ))}
          {!inputs.length && <li className="muted">No files yet.</li>}
        </ul>

        <label className="field">
          <span className="field-name">output folder</span>
          <div className="path-row">
            <input value={outDir} onChange={(e) => setOutDir(e.target.value)} placeholder="next to each input file" />
            <button onClick={() => setPicker("folder")}>Browse...</button>
          </div>
          <span className="field-help">
            Each file gets a folder named “track [recipe]” holding its stems and run.json. Dropped files are copied into
            the app’s data folder first, so without a folder chosen here their stems go to its “outputs” folder.
          </span>
        </label>
        <label className="check">
          <input type="checkbox" checked={useCache} onChange={(e) => setUseCache(e.target.checked)} />
          Reuse cached intermediate stems
        </label>

        {error && <div className="banner error" role="alert">{error}</div>}
        <button className="primary big" disabled={busy || !inputs.length || !validation?.ok} onClick={run}>
          {inputs.length > 1 ? `Run on ${inputs.length} files` : "Run"}
        </button>
      </section>

      <section className="run-queue">
        <div className="section-head">
          <h3>Queue</h3>
          <button className="small" onClick={onRefresh}>Refresh</button>
        </div>
        <ul className="jobs">
          {ordered.map((job) => (
            <li key={job.id} className={`job status-${job.status}${selected?.id === job.id ? " selected" : ""}`} onClick={() => setSelectedId(job.id)}>
              <span className="grow">{job.track}</span>
              <span className="muted">{job.recipe}</span>
              <span className={`badge status-${job.status}`}>{job.status}</span>
            </li>
          ))}
          {!ordered.length && <li className="muted">Nothing has run yet.</li>}
        </ul>
      </section>

      <section className="run-detail">
        {selected ? (
          <>
            <div className="section-head">
              <h3>{selected.track}</h3>
              <span className={`badge status-${selected.status}`}>{selected.status}</span>
              <span className="spacer" />
              {(selected.status === "queued" || selected.status === "running") && (
                <button className="danger" onClick={() => api.cancelJob(selected.id).then(onRefresh)}>Cancel</button>
              )}
              {selected.status !== "queued" && (
                <button className="primary" onClick={() => onShowResults(selected)}>Results</button>
              )}
              {selected.status !== "queued" && selected.status !== "running" && (
                <button onClick={() => api.deleteJob(selected.id).then(onRefresh)}>Remove</button>
              )}
            </div>
            {selected.error && <div className="banner error">{selected.error}</div>}
            {selected.status === "finished" && selected.output_dir && (
              <p className="muted">{selected.outputs.length} files in {selected.output_dir} ({clock(selected.seconds)})</p>
            )}
            <ul className="node-progress">
              {selected.order.map((name) => {
                const node = selected.nodes[name];
                return (
                  <li key={name} className={`node-row status-${node.status}`}>
                    <span className={`dot op-${node.op}`} />
                    <span className="node-name">{name}</span>
                    <span className="muted node-op">{node.op}{node.model ? ` · ${node.model}` : ""}</span>
                    <progress value={node.fraction} max={1} aria-label={`${name} progress`} />
                    <span className="node-state">
                      {node.status === "running" ? (node.fraction > 0 || !node.message ? `${Math.round(node.fraction * 100)}%` : node.message) : node.status}
                      {node.seconds !== undefined && node.status !== "running" ? ` · ${clock(node.seconds)}` : ""}
                    </span>
                  </li>
                );
              })}
            </ul>
            {selected.order.flatMap((name) => (selected.nodes[name].warnings ?? []).map((warning) => (
              <div key={name + warning} className="banner warning">{name}: {warning}</div>
            )))}
            <h4>Log</h4>
            <pre className="log">
              {(logs[selected.id] ?? []).map(describe).filter(Boolean).join("\n") || "No events yet."}
            </pre>
          </>
        ) : (
          <p className="muted">Choose files and run the recipe. Progress of every node shows up here.</p>
        )}
      </section>

      {picker === "files" && (
        <FilePicker title="Add audio files" mode="files" start={lastFolder}
          onPick={(paths) => {
            setPicker(null);
            addPaths(paths);
          }} onClose={() => setPicker(null)} />
      )}
      {picker === "folder" && (
        <FilePicker title="Choose the output folder" mode="folder" start={outDir || lastFolder}
          onPick={(paths) => {
            setPicker(null);
            setOutDir(paths[0]);
          }} onClose={() => setPicker(null)} />
      )}
    </div>
  );
}
