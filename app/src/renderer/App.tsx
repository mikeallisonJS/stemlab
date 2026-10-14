import { useCallback, useEffect, useRef, useState } from "react";

import { api, followJob } from "./api";
import type { InputFile, Job, JobEvent, ModelsResponse, RecipeData, Schema, SystemInfo, Validation } from "./types";
import { ModelsView } from "./views/ModelsView";
import { RecipeView } from "./views/RecipeView";
import { ResultsView } from "./views/ResultsView";
import { RunView } from "./views/RunView";

type Tab = "recipe" | "run" | "results" | "models";

const STORED_RECIPE = "captainstems.recipe";
const BLANK: RecipeData = { name: "new-recipe", nodes: {} };

function storedRecipe(): RecipeData | null {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORED_RECIPE) ?? "null");
    return parsed && typeof parsed === "object" && parsed.nodes ? (parsed as RecipeData) : null;
  } catch {
    return null;
  }
}

/** Fold a runner event into a job, the same way the server does. */
function applyEvent(job: Job, event: JobEvent): Job {
  const name = event.node;
  if (event.type === "job_done" && event.status) return { ...job, status: event.status as Job["status"] };
  if (event.type === "run_started") return { ...job, status: "running" };
  if (!name || !(name in job.nodes)) return job;
  const node = { ...job.nodes[name] };
  if (event.type === "node_started") {
    node.status = "running";
    node.fraction = 0;
  } else if (event.type === "node_status") node.message = event.status ?? "";
  else if (event.type === "node_progress") node.fraction = event.fraction ?? node.fraction;
  else if (event.type === "node_finished") {
    node.status = event.cached ? "cached" : "done";
    node.fraction = 1;
    node.message = "";
    node.seconds = event.seconds;
  } else return job;
  return { ...job, nodes: { ...job.nodes, [name]: node } };
}

export function App() {
  // #models etc. opens on that tab
  const [tab, setTab] = useState<Tab>(() => {
    const wanted = window.location.hash.slice(1);
    return wanted === "run" || wanted === "results" || wanted === "models" ? wanted : "recipe";
  });
  const [schema, setSchema] = useState<Schema | null>(null);
  const [models, setModels] = useState<ModelsResponse | null>(null);
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [recipe, setRecipeState] = useState<RecipeData>(() => storedRecipe() ?? BLANK);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [logs, setLogs] = useState<Record<string, JobEvent[]>>({});
  const [inputs, setInputs] = useState<InputFile[]>([]);
  const [resultsJob, setResultsJob] = useState<string | null>(null);
  const [fatal, setFatal] = useState<string | null>(null);
  const following = useRef<Map<string, () => void>>(new Map());

  const setRecipe = useCallback((next: RecipeData) => {
    setRecipeState(next);
    try {
      localStorage.setItem(STORED_RECIPE, JSON.stringify(next));
    } catch {
      // storage full or unavailable: the recipe just is not remembered
    }
  }, []);

  const refreshModels = useCallback(() => {
    api.models().then(setModels).catch((e: Error) => setFatal(e.message));
    api.system().then(setSystem).catch(() => undefined);
  }, []);

  const refreshJobs = useCallback(() => {
    api.jobs().then(setJobs).catch(() => undefined);
  }, []);

  useEffect(() => {
    api
      .schema()
      .then(async (loaded) => {
        setSchema(loaded);
        setFatal(null);
        // First visit: start from a shipped example instead of an empty canvas
        if (!storedRecipe()) {
          const examples = await api.recipes().catch(() => []);
          const start = examples.find((item) => item.name === "vocals-instrumental") ?? examples[0];
          if (start) setRecipe(await api.parseRecipe(start.yaml));
        }
      })
      .catch((e: Error) => setFatal(e.message));
    refreshModels();
    refreshJobs();
  }, [refreshModels, refreshJobs, setRecipe]);

  // Check the recipe against the installed models shortly after every change
  useEffect(() => {
    if (!schema) return;
    let stale = false;
    const timer = window.setTimeout(() => {
      api
        .validate(recipe)
        .then((result) => !stale && setValidation(result))
        .catch((e: Error) => !stale && setValidation({ ok: false, error: e.message }));
    }, 250);
    return () => {
      stale = true;
      window.clearTimeout(timer);
    };
  }, [recipe, schema, models]);

  // Follow every job that is still going over its websocket
  useEffect(() => {
    for (const job of jobs) {
      if ((job.status !== "queued" && job.status !== "running") || following.current.has(job.id)) continue;
      const id = job.id;
      const seen = new Set<number>();
      const stop = followJob(
        id,
        (event) => {
          if (seen.has(event.seq)) return;
          seen.add(event.seq);
          setLogs((current) => ({ ...current, [id]: [...(current[id] ?? []), event] }));
          setJobs((current) => current.map((item) => (item.id === id ? applyEvent(item, event) : item)));
          // Finished nodes carry stems and metrics that only the server knows in full
          if (event.type === "node_finished" || event.type === "job_done" || event.type === "run_started") {
            api.job(id).then((fresh) => setJobs((current) => current.map((item) => (item.id === id ? fresh : item)))).catch(() => undefined);
          }
        },
        () => {
          following.current.delete(id);
        },
      );
      following.current.set(id, stop);
    }
  }, [jobs]);

  useEffect(() => {
    const stops = following.current;
    return () => {
      for (const stop of stops.values()) stop();
      stops.clear();
    };
  }, []);

  const active = jobs.filter((job) => job.status === "queued" || job.status === "running").length;

  if (fatal && !schema) {
    return (
      <div className="fatal">
        <h1>CaptainStems</h1>
        <div className="banner error" role="alert">{fatal}</div>
        <button onClick={() => window.location.reload()}>Try again</button>
      </div>
    );
  }
  if (!schema) return <div className="fatal muted">Loading...</div>;

  return (
    <div className="app">
      <header>
        <h1>CaptainStems</h1>
        <nav>
          {(["recipe", "run", "results", "models"] as Tab[]).map((item) => (
            <button key={item} className={tab === item ? "tab on" : "tab"} onClick={() => setTab(item)} aria-current={tab === item}>
              {item[0].toUpperCase() + item.slice(1)}
              {item === "run" && active > 0 ? ` (${active})` : ""}
            </button>
          ))}
        </nav>
        <span className="spacer" />
        <span className="muted">
          {system ? `${system.gpu ?? "CPU"} · ${system.flavor} · v${system.version}` : ""}
        </span>
      </header>

      <main>
        {tab === "recipe" && (
          <RecipeView recipe={recipe} setRecipe={setRecipe} schema={schema} models={models?.models ?? []}
            validation={validation} onRun={() => setTab("run")} />
        )}
        {tab === "run" && (
          <RunView recipe={recipe} validation={validation} jobs={jobs} logs={logs} inputs={inputs} setInputs={setInputs}
            onRefresh={refreshJobs}
            onJobsCreated={(created) => setJobs((current) => [...current, ...created])}
            onShowResults={(job) => {
              setResultsJob(job.id);
              setTab("results");
            }} />
        )}
        {tab === "results" && (
          <ResultsView jobs={jobs} jobId={resultsJob} setJobId={setResultsJob}
            onOpened={(job) => {
              setJobs((current) => [...current.filter((item) => item.id !== job.id), job]);
              setResultsJob(job.id);
            }} />
        )}
        {tab === "models" && <ModelsView system={system} models={models} onChanged={refreshModels} />}
      </main>
    </div>
  );
}
