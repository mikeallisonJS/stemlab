import type {
  FsListing,
  InputFile,
  Job,
  JobEvent,
  ModelsResponse,
  Peaks,
  RecipeData,
  Schema,
  SystemInfo,
  Validation,
} from "./types";

// Served by `stemlab serve` the API shares our origin; under Vite's dev
// server (or with VITE_API set) it lives on its own port. The desktop app
// starts the server itself and says where.
const DEV_API = "http://127.0.0.1:8787";
export const API: string =
  window.stemlab?.api ??
  (import.meta.env.VITE_API as string | undefined) ??
  (import.meta.env.DEV ? DEV_API : window.location.origin);

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(API + path, init);
  } catch {
    throw new ApiError(0, `Cannot reach the Stemlab server at ${API}. Start it with: stemlab serve`);
  }
  if (!response.ok) {
    let message = response.statusText;
    try {
      const body = await response.json();
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // keep the status text
    }
    throw new ApiError(response.status, message);
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

const enc = encodeURIComponent;

export const api = {
  system: () => request<SystemInfo>("/system"),
  setSystemConfig: (config: { torch_flavor: string | null; rocm_target: string | null }) =>
    request<SystemInfo>("/system/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }),
  schema: () => request<Schema>("/schema"),
  models: () => request<ModelsResponse>("/models"),
  fetchModel: (id: string) => post<unknown>(`/models/${enc(id)}/fetch`),
  removeModel: (id: string) => request<void>(`/models/${enc(id)}`, { method: "DELETE" }),
  addModel: (manifest: Record<string, unknown>, files: Record<string, string>) =>
    post<unknown>("/models", { manifest, files }),

  recipes: () => request<{ file: string; name: string; yaml: string; nodes: number }[]>("/recipes"),
  parseRecipe: (yaml: string) => post<{ recipe: RecipeData }>("/recipes/parse", { yaml }).then((r) => r.recipe),
  recipeYaml: (recipe: RecipeData) => post<{ yaml: string }>("/recipes/yaml", { recipe }).then((r) => r.yaml),
  validate: (recipe: RecipeData) => post<Validation>("/recipes/validate", { recipe }),

  jobs: () => request<Job[]>("/jobs"),
  job: (id: string) => request<Job>(`/jobs/${id}`),
  createJobs: (recipe: RecipeData, inputs: string[], outDir: string | null, useCache: boolean) =>
    post<Job[]>("/jobs", { recipe, inputs, out_dir: outDir || null, use_cache: useCache }),
  cancelJob: (id: string) => post<Job>(`/jobs/${id}/cancel`),
  deleteJob: (id: string) => request<void>(`/jobs/${id}`, { method: "DELETE" }),
  openRun: (path: string) => post<Job>("/runs/open", { path }),

  peaks: (job: string, node: string, stem: string, buckets = 2000) =>
    request<Peaks>(`/jobs/${job}/peaks/${enc(node)}/${enc(stem)}?buckets=${buckets}`),
  audioUrl: (job: string, node: string, stem: string) => `${API}/jobs/${job}/audio/${enc(node)}/${enc(stem)}`,
  spectrogramUrl: (job: string, node: string, stem: string, width = 1400, height = 180) =>
    `${API}/jobs/${job}/spectrogram/${enc(node)}/${enc(stem)}?width=${width}&height=${height}`,

  browse: (path?: string) => request<FsListing>("/fs" + (path ? `?path=${enc(path)}` : "")),
  audioInfo: (path: string) => request<InputFile>(`/audio/info?path=${enc(path)}`),
  upload: (file: File) =>
    request<InputFile>(`/uploads?name=${enc(file.name)}`, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: file,
    }),
};

/** Follow a job's events. The server replays everything from the start, then streams. */
export function followJob(id: string, onEvent: (event: JobEvent) => void, onClose: () => void): () => void {
  const socket = new WebSocket(API.replace(/^http/, "ws") + `/jobs/${id}/events`);
  socket.onmessage = (message) => onEvent(JSON.parse(message.data) as JobEvent);
  socket.onclose = onClose;
  socket.onerror = () => socket.close();
  return () => {
    socket.onclose = null;
    socket.close();
  };
}
