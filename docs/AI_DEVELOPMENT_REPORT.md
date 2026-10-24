# AI-assisted development report

## AI tools used

OpenAI Codex (ChatGPT) was used as the AI coding assistant during this project. It helped inspect the supplied challenge brief and CSV, propose the architecture and data rules, draft the Python/FastAPI and React modules, create deterministic tests, and prepare the documentation. The developer reviewed the metric choices, tested the generated implementation, and retained the important assumptions in the README and design notes.

Groq is the runtime intent-classification provider in the application. The integration sends a question to the Groq Chat Completions API and expects a small JSON intent structure. It does not ask Groq for SQL or numerical answers. The API adapter and failure fallback have been tested with mocked responses; no live Groq request has been made because no user API key was configured during development.

## How AI was used

- Read and summarized the challenge requirements and all rows of the supplied CSV.
- Identified the missing unit price, zero-quantity row, and return-status semantics for explicit handling.
- Drafted schema, importer, fixed analytics queries, intent validation, API routes, UI, and tests.
- Used test failures and runtime output to identify and correct issues, including a temporary-directory restriction during pytest setup and an allowed build-script setting required by pnpm 11 for esbuild.
- Produced the diagrams and implementation documentation from the code and observed data behavior.

## Problems and debugging methods

- `TXN0051` has no unit price. The importer rejects it and reports the source row instead of guessing a price.
- Returned transactions have no refund amount or return quantity. The documented metric excludes returned rows rather than inventing a net return.
- The first pytest invocation could not create its default temp directory in the managed environment. Pytest was configured to use an ignored project-local temporary directory; the full suite then passed.
- FastAPI's synchronous test client required a local Windows event-loop socket pair unavailable in the sandbox. The suite was run in the authorized environment outside the sandbox and passed.
- pnpm 11 changed its build-script allowlist setting. The project explicitly allows esbuild's platform-binary setup so Vite can build; unrelated dependency scripts remain unapproved.
- The frontend build was checked with Vite, while API and business logic were checked with pytest and temporary SQLite fixtures.

## What is implemented and verified

- CSV validation and repeatable SQLite import.
- Five deterministic analytics functions with supporting figures.
- Groq intent adapter, local fallback, output validation, and protected API key handling.
- FastAPI question and health endpoints.
- React question interface with loading, unsupported, API status, and error states.
- Backend suite: 44 tests pass. Frontend production build succeeds.

The live Groq network request and full browser interaction have not been verified with a user API key and browser session. The implementation should not be described as having passed those checks.

## Improvements for one more day

- Perform a live Groq smoke test with a developer-owned key and record model, latency, and classification accuracy over a small set of representative and ambiguous questions.
- Add a broader intent evaluation set, including paraphrases, typos, prompt-injection attempts, and requests that combine multiple metrics.
- Add browser-based UI tests and keyboard/screen-reader accessibility review.
- Move allowed category/region/channel values from hard-coded lists into configurable validation or a reference table.
- Add richer return/refund data and agree on currency and accounting rules with a business owner.
- Add import history display, downloadable rejection report, and a clear UI notice when the API is offline.
- Add authentication, structured operational logging, and deployment hardening only if the app needs to move beyond local demonstration use.
