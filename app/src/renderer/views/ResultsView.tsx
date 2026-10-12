import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";

import { api } from "../api";
import { FilePicker } from "../components/FilePicker";
import { MIX } from "../recipe";
import type { Job, Op, Peaks } from "../types";

interface Track {
  key: string;
  node: string;
  stem: string;
  label: string;
  op: Op | "mix";
}

function tracksOf(job: Job): Track[] {
  const tracks: Track[] = [];
  if (job.has_mix) tracks.push({ key: "mix/mix", node: MIX, stem: MIX, label: "mix (input)", op: "mix" });
  for (const name of job.order) {
    const node = job.nodes[name];
    if (node.status !== "done" && node.status !== "cached") continue;
    for (const stem of Object.keys(node.stems)) {
      tracks.push({ key: `${name}/${stem}`, node: name, stem, label: `${name}.${stem}`, op: node.op });
    }
  }
  return tracks;
}

function time(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

interface TrackRowProps {
  job: Job;
  track: Track;
  role: "A" | "B" | null;
  active: boolean;
  spectrogram: boolean;
  position: number;
  duration: number;
  onReady: (key: string, player: WaveSurfer, duration: number) => void;
  onGone: (key: string) => void;
  onSeek: (seconds: number) => void;
  onAssign: (role: "A" | "B") => void;
  onSolo: () => void;
}

/** One stem: waveform (drawn from precomputed peaks), optional spectrogram, A/B buttons. */
function TrackRow(props: TrackRowProps) {
  const { job, track, role, active, spectrogram, position, duration, onReady, onGone, onSeek, onAssign, onSolo } = props;
  const container = useRef<HTMLDivElement>(null);
  const playerRef = useRef<WaveSurfer | null>(null);
  const [peaks, setPeaks] = useState<Peaks | null>(null);
  const [error, setError] = useState<string | null>(null);
  const callbacks = useRef({ onReady, onGone, onSeek });
  callbacks.current = { onReady, onGone, onSeek };

  useEffect(() => {
    let cancelled = false;
    setPeaks(null);
    setError(null);
    api
      .peaks(job.id, track.node, track.stem)
      .then((result) => !cancelled && setPeaks(result))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [job.id, track.node, track.stem]);

  useEffect(() => {
    if (!peaks || !container.current) return;
    // Upper and lower half of the waveform come from the max and min envelopes
    const upper = peaks.peaks.map(([, high]) => Math.max(0, high));
    const lower = peaks.peaks.map(([low]) => Math.max(0, -low));
    const player = WaveSurfer.create({
      container: container.current,
      height: 64,
      waveColor: "#5b6b82",
      progressColor: "#4aa3ff",
      cursorColor: "#ffffff",
      cursorWidth: 1,
      normalize: false,
      url: api.audioUrl(job.id, track.node, track.stem),
      peaks: [upper, lower],
      duration: peaks.duration,
    });
    player.on("interaction", (seconds: number) => callbacks.current.onSeek(seconds));
    playerRef.current = player;
    callbacks.current.onReady(track.key, player, peaks.duration);
    return () => {
      playerRef.current = null;
      callbacks.current.onGone(track.key);
      player.destroy();
    };
  }, [peaks, job.id, track.key, track.node, track.stem]);

  // Only the stem being played advances its own cursor. The others would show
  // a stale one, so theirs is hidden and the shared playhead is drawn instead.
  useEffect(() => {
    playerRef.current?.setOptions(
      active
        ? { progressColor: "#4aa3ff", cursorColor: "#ffffff" }
        : { progressColor: "#5b6b82", cursorColor: "transparent" },
    );
  }, [active, peaks]);

  const metrics = job.nodes[track.node]?.info.metrics;
  return (
    <div className={`track op-${track.op}${active ? " active" : ""}`}>
      <div className="track-head">
        <button className="small" title="Play this stem" onClick={onSolo}>▶</button>
        <span className="track-label">{track.label}</span>
        {peaks && <span className="muted">RMS {peaks.rms_db.toFixed(1)} dB · peak {peaks.peak_db.toFixed(1)} dB</span>}
        {track.stem === "residual" && metrics && (
          <span className="metric" title="How far below the mix the lost signal sits. More negative is better.">
            {metrics.residual_vs_mix_db.toFixed(1)} dB vs mix
            {metrics.si_sdr_db !== undefined ? ` · SI-SDR ${metrics.si_sdr_db.toFixed(2)} dB` : ""}
          </span>
        )}
        <span className="spacer" />
        <button className={`small ab${role === "A" ? " on" : ""}`} onClick={() => onAssign("A")} aria-pressed={role === "A"}>A</button>
        <button className={`small ab${role === "B" ? " on" : ""}`} onClick={() => onAssign("B")} aria-pressed={role === "B"}>B</button>
      </div>
      {error ? <div className="banner error">{error}</div> : (
        <div className="wave-box">
          <div ref={container} className="wave">{!peaks && <span className="muted">Loading...</span>}</div>
          {!active && duration > 0 && <div className="playhead" style={{ left: `${(position / duration) * 100}%` }} />}
        </div>
      )}
      {spectrogram && (
        <div className="spectrogram" onClick={(e) => {
          const box = e.currentTarget.getBoundingClientRect();
          if (duration > 0) onSeek(((e.clientX - box.left) / box.width) * duration);
        }}>
          <img src={api.spectrogramUrl(job.id, track.node, track.stem)} alt={`Spectrogram of ${track.label}`} loading="lazy" />
          {duration > 0 && <div className="playhead" style={{ left: `${(position / duration) * 100}%` }} />}
        </div>
      )}
    </div>
  );
}

interface Props {
  jobs: Job[];
  jobId: string | null;
  setJobId: (id: string | null) => void;
  onOpened: (job: Job) => void;
}

export function ResultsView({ jobs, jobId, setJobId, onOpened }: Props) {
  const withResults = jobs.filter((job) => job.status !== "queued");
  const job =
    withResults.find((item) => item.id === jobId) ??
    [...withResults].reverse().find((item) => item.status === "finished") ??
    withResults[withResults.length - 1] ??
    null;
  const tracks = useMemo(() => (job ? tracksOf(job) : []), [job]);

  const players = useRef<Map<string, WaveSurfer>>(new Map());
  const [a, setA] = useState<string | null>(null);
  const [b, setB] = useState<string | null>(null);
  const [side, setSide] = useState<"A" | "B">("A");
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const [spectrogram, setSpectrogram] = useState(true);
  const [volume, setVolume] = useState(0.8);
  const [picker, setPicker] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeKey = side === "A" ? a : b;
  const state = useRef({ activeKey, playing, position, volume });
  state.current = { activeKey, playing, position, volume };

  // Sensible defaults when a job is shown: A is the first stem, B the mix
  useEffect(() => {
    const keys = tracks.map((track) => track.key);
    setA((current) => (current && keys.includes(current) ? current : (keys.find((key) => key !== "mix/mix") ?? keys[0] ?? null)));
    setB((current) => (current && keys.includes(current) ? current : keys.includes("mix/mix") ? "mix/mix" : (keys[1] ?? null)));
  }, [tracks]);

  useEffect(() => {
    setPlaying(false);
    setPosition(0);
    setSide("A");
  }, [job?.id]);

  /** Move every stem to the same time, so switching between them never jumps. */
  const seekAll = useCallback((seconds: number) => {
    for (const player of players.current.values()) player.setTime(seconds);
    setPosition(seconds);
  }, []);

  const playKey = useCallback((key: string | null, from?: number) => {
    const start = from ?? state.current.position;
    for (const [other, player] of players.current) {
      if (other !== key && player.isPlaying()) player.pause();
    }
    const player = key ? players.current.get(key) : undefined;
    if (!player) return setPlaying(false);
    player.setVolume(state.current.volume);
    player.setTime(start);
    player.play().then(() => setPlaying(true)).catch((e: Error) => setError(`Playback failed: ${e.message}`));
  }, []);

  const pause = useCallback(() => {
    for (const player of players.current.values()) player.pause();
    setPlaying(false);
  }, []);

  const toggle = useCallback(() => {
    if (state.current.playing) pause();
    else playKey(state.current.activeKey);
  }, [pause, playKey]);

  const switchSide = useCallback((next: "A" | "B", key: string | null) => {
    setSide(next);
    const current = state.current.activeKey ? players.current.get(state.current.activeKey) : undefined;
    const now = current ? current.getCurrentTime() : state.current.position;
    if (state.current.playing) playKey(key, now);
    else seekAll(now);
  }, [playKey, seekAll]);

  const onReady = useCallback((key: string, player: WaveSurfer, length: number) => {
    players.current.set(key, player);
    setDuration((current) => Math.max(current, length));
    player.setTime(state.current.position);
    player.on("timeupdate", (seconds: number) => {
      if (state.current.activeKey === key && player.isPlaying()) setPosition(seconds);
    });
    player.on("finish", () => {
      if (state.current.activeKey === key) {
        setPlaying(false);
        for (const other of players.current.values()) other.setTime(0);
        setPosition(0);
      }
    });
  }, []);

  const onGone = useCallback((key: string) => {
    players.current.delete(key);
  }, []);

  useEffect(() => {
    for (const player of players.current.values()) player.setVolume(volume);
  }, [volume]);

  // Space plays and pauses, X flips between A and B
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.code === "Space") {
        // A focused button already reacts to Space by itself
        if (target.tagName === "BUTTON") return;
        event.preventDefault();
        toggle();
      } else if (event.key.toLowerCase() === "x") {
        const next = side === "A" ? "B" : "A";
        switchSide(next, next === "A" ? a : b);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle, switchSide, side, a, b]);

  const label = (key: string | null) => tracks.find((track) => track.key === key)?.label ?? "none";
  const analyses = job ? job.order.filter((name) => job.nodes[name].info.metrics) : [];

  return (
    <div className="results-view">
      <div className="toolbar">
        <label>
          Run
          <select value={job?.id ?? ""} onChange={(e) => setJobId(e.target.value || null)} aria-label="Run to show">
            {!withResults.length && <option value="">no runs yet</option>}
            {[...withResults].reverse().map((item) => (
              <option key={item.id} value={item.id}>{item.track} · {item.recipe} · {item.status}</option>
            ))}
          </select>
        </label>
        <button onClick={() => setPicker(true)}>Open run.json...</button>
        <span className="spacer" />
        <label className="check">
          <input type="checkbox" checked={spectrogram} onChange={(e) => setSpectrogram(e.target.checked)} />
          Spectrograms
        </label>
        <label>
          Volume
          <input type="range" min={0} max={1} step={0.01} value={volume} onChange={(e) => setVolume(Number(e.target.value))} aria-label="Volume" />
        </label>
      </div>

      {error && <div className="banner error" role="alert">{error}</div>}

      {job ? (
        <>
          <div className="transport">
            <button className="primary big" onClick={toggle} disabled={!activeKey} aria-label={playing ? "Pause" : "Play"}>
              {playing ? "❚❚ Pause" : "▶ Play"}
            </button>
            <div className="ab-switch" role="group" aria-label="A/B">
              <button className={side === "A" ? "on" : ""} onClick={() => switchSide("A", a)} disabled={!a}>A · {label(a)}</button>
              <button className={side === "B" ? "on" : ""} onClick={() => switchSide("B", b)} disabled={!b}>B · {label(b)}</button>
            </div>
            <span className="time">{time(position)} / {time(duration)}</span>
            <span className="muted">Space plays, X switches A/B. Click a waveform to jump; all stems stay in sync.</span>
          </div>

          {job.status === "running" && <div className="banner">This run is still going. Stems appear here as their nodes finish.</div>}
          {job.error && <div className="banner error">{job.error}</div>}
          {analyses.map((name) => {
            const metrics = job.nodes[name].info.metrics!;
            return (
              <div key={name} className="analysis">
                <strong>{name}</strong>: the chain lost {metrics.residual_vs_mix_db.toFixed(1)} dB relative to the mix
                (residual {metrics.residual_rms_db.toFixed(1)} dBFS RMS, mix {metrics.mix_rms_db.toFixed(1)} dBFS)
                {metrics.si_sdr_db !== undefined && <> · SI-SDR of {metrics.si_sdr_stem}: {metrics.si_sdr_db.toFixed(2)} dB</>}
                <button className="small" onClick={() => {
                  setA(`${name}/residual`);
                  if (job.has_mix) setB("mix/mix");
                  switchSide("A", `${name}/residual`);
                }}>Hear the residual</button>
              </div>
            );
          })}

          <div className="tracks">
            {tracks.map((track) => (
              <TrackRow key={`${job.id}/${track.key}`} job={job} track={track}
                role={track.key === a ? "A" : track.key === b ? "B" : null}
                active={track.key === activeKey} spectrogram={spectrogram} position={position} duration={duration}
                onReady={onReady} onGone={onGone} onSeek={seekAll}
                onAssign={(role) => {
                  if (role === "A") setA(track.key);
                  else setB(track.key);
                  if (role === side) {
                    if (state.current.playing) playKey(track.key);
                  }
                }}
                onSolo={() => {
                  setA(track.key);
                  setSide("A");
                  playKey(track.key);
                }} />
            ))}
            {!tracks.length && <p className="muted">No stems yet.</p>}
          </div>

          {job.outputs.length > 0 && (
            <div className="outputs">
              <h4>Exported files</h4>
              <p className="muted">{job.output_dir}</p>
              <ul>
                {job.outputs.map((output) => <li key={output.file}><code>{output.file}</code></li>)}
              </ul>
            </div>
          )}
        </>
      ) : (
        <p className="muted pad">Run a recipe, or open the run.json of an earlier run, to look at its stems here.</p>
      )}

      {picker && (
        <FilePicker title="Open a run.json" mode="files" onClose={() => setPicker(false)}
          onPick={(paths) => {
            setPicker(false);
            api.openRun(paths[0]).then(onOpened).catch((e: Error) => setError(e.message));
          }} />
      )}
    </div>
  );
}
