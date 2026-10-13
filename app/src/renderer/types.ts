// Shapes of what the API sends. They mirror captainstems/recipe.py and server/jobs.py.

export type Op = "separate" | "subtract" | "ensemble" | "postprocess" | "analyze" | "export";

export interface NodeData {
  op: Op;
  model?: string;
  /** Per-slot references for most ops, a list (or labelled mapping) for ensemble and export */
  inputs?: Record<string, string | string[]> | string[];
  targets?: string[] | null;
  target?: string | null;
  params?: Record<string, unknown>;
}

export interface RecipeData {
  version?: number;
  name: string;
  defaults?: Record<string, unknown>;
  nodes: Record<string, NodeData>;
}

export interface JsonSchema {
  type?: string;
  title?: string;
  description?: string;
  default?: unknown;
  enum?: unknown[];
  const?: unknown;
  minimum?: number;
  maximum?: number;
  items?: JsonSchema;
  properties?: Record<string, JsonSchema>;
  anyOf?: JsonSchema[];
  allOf?: JsonSchema[];
  $ref?: string;
  $defs?: Record<string, JsonSchema>;
  error?: string;
}

export interface OpInfo {
  inputs: { name: string; many: boolean }[];
  /** A fixed list, or "model" when the outputs are the stems of the chosen model */
  outputs: string[] | "model";
  model?: boolean;
}

export interface Schema {
  recipe: JsonSchema;
  ops: Record<Op, OpInfo>;
  backends: Record<string, JsonSchema>;
  export_formats: string[];
}

export interface ModelInfo {
  id: string;
  name?: string;
  backend: string;
  arch?: string;
  stems: string[];
  installed: boolean;
  curated?: boolean;
  download_bytes?: number;
  license?: string;
  notes?: string;
  defaults?: Record<string, unknown>;
}

export interface ModelsResponse {
  root: string;
  models: ModelInfo[];
  problems: Record<string, string>;
}

export interface JobNode {
  op: Op;
  model: string | null;
  status: "waiting" | "running" | "done" | "cached" | "failed";
  fraction: number;
  message: string;
  seconds?: number;
  stems: Record<string, string>;
  info: {
    metrics?: Metrics;
    files?: { stem: string; file: string }[];
    adjustments?: string[];
    kept?: string;
  };
  warnings?: string[];
}

export interface Metrics {
  mix_rms_db: number;
  residual_rms_db: number;
  residual_vs_mix_db: number;
  residual_peak_db: number;
  si_sdr_db?: number;
  si_sdr_stem?: string;
  stems: Record<string, { rms_db: number; peak_db: number }>;
}

export type JobStatus = "queued" | "running" | "finished" | "failed" | "cancelled";

export interface Job {
  id: string;
  status: JobStatus;
  recipe: string;
  input: string;
  track: string;
  created: number;
  started: number | null;
  finished: number | null;
  error: string | null;
  order: string[];
  nodes: Record<string, JobNode>;
  has_mix: boolean;
  output_dir: string | null;
  outputs: { stem: string; file: string; path?: string; node: string }[];
  warnings: { node: string; message: string }[];
  seconds: number | null;
}

export interface JobEvent {
  type: string;
  job_id: string;
  seq: number;
  node?: string;
  fraction?: number;
  status?: string;
  message?: string;
  error?: string;
  cached?: boolean;
  seconds?: number;
}

export interface SystemInfo {
  version: string;
  os: string;
  machine: string;
  python: string;
  gpu: string | null;
  vram_mb: number | null;
  flavor: string;
  detected_flavor: string;
  flavor_source: string;
  rocm_target?: string | null;
  torch: { version: string | null; hip?: string | null; cuda: boolean; mps: boolean };
  onnxruntime: { version: string | null; providers: string[] };
  ffmpeg: string | null;
  home: string;
  backends: Record<string, Record<string, string>>;
  cache_bytes: number;
}

export interface Validation {
  ok: boolean;
  error?: string;
  order?: string[];
  nodes?: Record<string, { op: Op; model: string | null; params: Record<string, unknown>; outputs: string[] }>;
}

export interface Peaks {
  peaks: [number, number][];
  duration: number;
  sample_rate: number;
  rms_db: number;
  peak_db: number;
}

export interface FsListing {
  path: string | null;
  parent: string | null;
  folders: { name: string; path: string }[];
  files: { name: string; path: string; size: number }[];
}

export interface InputFile {
  path: string;
  name: string;
  duration?: number;
}
