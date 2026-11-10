// Phoebe tenant config for mikeallisonJS/stemlab.
//
// Phoebe (https://github.com/JesusFilm/phoebe) picks up issues labelled
// `ready-for-agent`, works each one on a `phoebe/` branch in its own clone, runs
// the gates below, and opens a PR. This repo is one tenant of a Phoebe
// workspace: the workspace root discovers this file and runs the shared engine
// in its container. This file names only what is specific to this repo.
//
// No import on purpose: the container loads this file from a mount with no
// node_modules, and this repo has no `phoebe-agent` dependency. The fields are
// `PhoebeUserConfig` from phoebe-agent (docs/configuration.md).
//
// Everything else Phoebe reads lives in `.phoebe/` (`configDir` below): the
// engine's shipped prompts, unedited, in .phoebe/prompts/, and the gitignored
// secrets file .phoebe/.env (see .phoebe/.env.example):
// GH_TOKEN, a fine-grained PAT for this repo, and ANTHROPIC_AUTH_TOKEN, the
// provider key. The workspace image sends Claude Code through a shared proxy
// when that key is the one it is given.
//
// Gates from CLAUDE.md (uv: ruff and pytest) and app/package.json (tsc and
// vitest for the Electron UI).

const config = {
  repoSlug: "mikeallisonJS/stemlab",
  repoUrl: "https://github.com/mikeallisonJS/stemlab.git",
  configDir: ".phoebe",
  installCommand:
    "uv sync --locked --extra dev --extra server && cd app && ELECTRON_SKIP_BINARY_DOWNLOAD=1 pnpm install --frozen-lockfile",
  checkCommand: "uv run ruff check . && cd app && pnpm typecheck",
  testCommand: "uv run pytest && cd app && pnpm test",
  readyCommand:
    "uv run ruff check . && cd app && pnpm typecheck && uv run pytest && cd app && pnpm test",
  defaultProvider: "claude",
  providerEnv: { claude: "ANTHROPIC_AUTH_TOKEN" },
};

export default config;
