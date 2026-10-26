<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## Team Git workflow (user instruction)

- Fetch the latest origin/main before starting each task and create a dedicated task branch from that commit.
- Commit and push task branches only. Do not push to main, merge branches, or force-push.
- The user creates and merges pull requests manually in GitHub. Do not create or merge PRs from the CLI, API, or browser automation.
- If main advances while a task is in progress, report the new base and coordinate the update; do not merge it into the task branch automatically.
