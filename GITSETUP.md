# GitHub Setup Notes

This project was prepared for GitHub with a root `.gitignore` that keeps local dependencies, build output, Python caches, virtual environments, local databases, logs, and generated output out of source control.

## Suggested First-Time Setup

From the project root:

```sh
git init
git status --short --ignored
```

Review the status output before adding files. The ignored list should include things like:

- `.DS_Store`
- `.pytest_cache/`
- `__pycache__/`
- `python/.venv/`
- `typescript/ui/node_modules/`
- `output/`
- `nodegraph.sqlite`

If that looks right, stage the project:

```sh
git add .
git status --short
```

Then make the first commit:

```sh
git commit -m "Initial project import"
```

## Create the GitHub Repository

Option A, using the GitHub CLI:

```sh
gh repo create nodegraph --private --source=. --remote=origin --push
```

Change `--private` to `--public` if you want the repository to be public.

Option B, using the GitHub website:

1. Create a new empty repository on GitHub.
2. Do not add a README, license, or `.gitignore` on GitHub because this project already has local files.
3. Copy the repository URL.
4. Connect and push from this project:

```sh
git remote add origin https://github.com/YOUR_USERNAME/nodegraph.git
git branch -M main
git push -u origin main
```

## Files To Review Before Publishing

Check these before the first commit:

- `citations.txt`: currently not ignored. If this is generated output or contains private research data, uncomment `citations.txt` in `.gitignore`.
- `CYCLES.md`, `HumanInTheLoopAnalysis.md`, `ai_agents.md`, `changes_210226.md`, and `typescript_port_notes.md`: documentation-like files that are safe to track if they are part of the project history.
- `docs/`, `python/`, and `typescript/`: expected source/project directories to track.
- `schemas/`: currently only shows ignored macOS metadata. Add and track this folder when it contains real schema files.
- `typescript/package-lock.json` and `typescript/ui/package-lock.json`: keep these tracked so installs are reproducible.
- `.vscode/settings.json`: currently allowed if present. Remove the exception from `.gitignore` if your local settings are personal.

## Things That Should Stay Local

Do not commit:

- `.env` files or credentials
- virtual environments such as `python/.venv/`
- installed Node dependencies such as `node_modules/`
- local SQLite databases such as `nodegraph.sqlite`
- generated run output under `output/`
- cache folders such as `.pytest_cache/` and `__pycache__/`

If you accidentally stage something local, unstage it before committing:

```sh
git restore --staged PATH_TO_FILE_OR_FOLDER
```

If a file was already committed and should become ignored, remove it from Git tracking while keeping it on disk:

```sh
git rm --cached PATH_TO_FILE
git commit -m "Stop tracking local generated file"
```

For folders:

```sh
git rm -r --cached PATH_TO_FOLDER
git commit -m "Stop tracking generated folder"
```

## Recommended Follow-Up

After the first push, consider adding:

- A fuller `README.md` with install and run steps for both Python and TypeScript.
- A license file if this will be public or shared.
- `.env.example` with placeholder environment variable names only.
- Basic GitHub Actions for Python tests and TypeScript build checks.
