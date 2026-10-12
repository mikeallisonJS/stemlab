# CaptainStems

A power-user stem separation workbench: run any separation model you choose, compose separations as a
graph (a *recipe*), and rerun the same recipe on any file.

This is version 2, a rewrite. The original PyQt application is kept in [`archive/v1/`](archive/v1/).
Plan and decisions: [CaptainStems v2 handoff](https://claude.ai/artifact/FoargYKnKDffjnQYnFNWzF).

## Setup

Requires [uv](https://docs.astral.sh/uv/) and git.

```
git clone --recurse-submodules https://github.com/mikeallisonJS/CaptainStems
cd CaptainStems
uv sync --extra dev --extra server
uv run captainstems bootstrap
uv run captainstems doctor
```

`bootstrap` installs the build of PyTorch that matches your GPU (CUDA, ROCm, Apple Silicon or CPU), the
model libraries and onnxruntime. They are deliberately not regular dependencies, so `uv sync` removes
them: run `bootstrap` again afterwards, or use `uv sync --inexact`.

## License

MIT, see [LICENSE](LICENSE). Model weights are downloaded separately and carry their own licenses.
