# Nightshift setup: Mac mini runtime host, ZBook backend (ENG-003)

Nightshift is the product's primary AI runtime (v2.0 POWER requirement). It has no x86_64 Linux edition, so it runs on an Apple Silicon Mac mini and the backend on the ZBook (Ubuntu) reaches it over the network:

```text
ZBook (Ubuntu)                               Mac mini (Apple Silicon)
backend, tests, smoke check  --- LAN --->    Nightshift, Meterless Runtime :8088
```

**Sources:** official Meterless provider guide (`docs/agent-ready/add-meterless-provider.md`) and hotspot page (`docs/products/nightshift/hotspot.md`) in github.com/Meterless/Meterless, plus meterless.ai. Steps marked **(verify)** are not documented publicly; record what you actually see so this guide can be corrected after the first run.

## Facts from the official docs

| Item | Value |
|---|---|
| Editions | Mac **M1 or later** (free), Windows 10/11 with GPU, DGX Spark. The browser-only web edition does not satisfy ENG-003. Intel Macs are not supported |
| API | OpenAI-compatible, default base URL `http://127.0.0.1:8088/v1` |
| Token | written by the runtime to `<stateDir>/proxy-token`; the placeholder `rt-local` is rejected |
| Headers | `Authorization: Bearer <token>` and `meterless-app: agentic-engineering-workspace` on every call; `meterless-scope: user` on chat calls |
| Status | `GET /v1/models`: 401/403 unauthorized, 200 with `meterless/*` ids online, anything else offline. `/healthz` only proves the process is up |
| Lanes | `meterless/auto`, `fast`, `deep`, `cheap`, `local`, `fusion`, plus `meterless/<class>` forms. Routing modes, not model names |
| Timeouts | a cold model load can take minutes; the client allows 180 s |
| Other machines | "turn on hotspot mode and paste its connect link once" |

## On the Mac mini

1. **Check the chip.** Apple menu, About This Mac: it must say *Apple M1* or later. Note the memory size.
2. **Install Nightshift for Mac M1+** from https://meterless.ai/Nightshift/M1+/ and launch it.
3. **Give it at least one working lane.** With limited memory, prefer small local models, or add a cloud provider in Nightshift's Providers settings so heavy reasoning runs in the cloud while Nightshift stays the runtime the app talks to. Cloud providers bill your own key; don't add a paid one without agreeing it with the team. For the optional Nemotron award (ENG-053), add the NVIDIA credentials here. **(verify: Providers UI)**
4. **Find the token.** **(verify: state directory location)**
   ```bash
   find ~/Library ~/.config ~/.local -name proxy-token 2>/dev/null
   ```
5. **Check the runtime locally** (Terminal on the Mac):
   ```bash
   read -rs TOKEN < "/path/from/step/4/proxy-token"
   curl -s http://127.0.0.1:8088/v1/models \
     -H "Authorization: Bearer $TOKEN" -H "meterless-app: agentic-engineering-workspace" | head -c 800
   ```
   Expect a JSON list containing `meterless/*` ids.
6. **Turn on hotspot mode** and note the connect link. **(verify: where the switch is, what the link contains)**
7. **Note the Mac's LAN address:** `ipconfig getifaddr en0` (Wi-Fi) or `ipconfig getifaddr en1`. Allow incoming connections if macOS asks about Nightshift.
8. **Keep it awake while serving:** System Settings, Energy, enable *Prevent automatic sleeping when the display is off*.

## On the ZBook

1. **Reachability.** The token is typed without echo, so it stays out of shell history:
   ```bash
   read -rs TOKEN   # paste the token, press Enter
   curl -s -o /dev/null -w '%{http_code}\n' http://<mac-ip>:8088/v1/models \
     -H "Authorization: Bearer $TOKEN" -H "meterless-app: agentic-engineering-workspace"
   ```
   `200` is good; `401` means a wrong or rotated token; `000` means not reachable (hotspot mode off, firewall, Mac asleep, different network).
2. **Configure the backend** in the repo-root `.env` (never committed):
   ```bash
   NIGHTSHIFT_BASE_URL=http://<mac-ip>:8088/v1
   NIGHTSHIFT_TOKEN=<contents of proxy-token>
   ```
   A pasted URL ending in `/v1/models`, `/v1/chat/completions` or `/healthz` is normalized automatically.
3. **Run the smoke check** from the repo root. The ZBook's system Python is 3.10 and the backend needs 3.11+, so it runs in a throwaway Python 3.12 container; `--network host` lets it reach the Mac:
   ```bash
   docker run --rm --network host --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 \
     -v "$PWD:/repo" -w /repo/backend python:3.12-slim bash -c \
     "pip install -q --user --no-warn-script-location -r requirements.txt && \
      python -m app.modules.nightshift.smoke --evidence-out ../docs/evidence/nightshift-smoke-$(date +%F).md"
   ```
   The module reads the repo-root `.env` itself. Expected end: `SMOKE OK: the application reached Nightshift and got real model responses.`, exit code 0.
4. **Review the evidence file** before committing it. It records the endpoint, advertised ids, the model that answered each lane (from the routing receipt when the runtime returns one), latency and token counts. The token is never written, and the smoke refuses to save a file containing it.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `CONFIG: NIGHTSHIFT_TOKEN is not set` / `placeholder 'rt-local'` | `.env` missing the real token |
| `probe: offline` with connection refused or timeout | Mac asleep, hotspot mode off, firewall, wrong IP |
| `probe: offline`, "listed no meterless/* ids" | something else answers on that port (another OpenAI-compatible server) |
| `probe: unauthorized` | token wrong or rotated; copy `proxy-token` again |
| a lane `SKIP ... not listed by /v1/models` | that routing mode is not configured on this runtime |
| `NightshiftProviderError` with an `*_empty_response` code | reported by other teams when a reasoning model spends the whole `max_tokens` budget before answering; the smoke uses 1024 |
| first call very slow | cold model load; allowed up to 180 s |

## What to send M3 after the first run

The evidence file, the Mac's chip and memory, the Nightshift version, which lanes and providers are configured, and the hotspot connect-link format (without the token). Never paste the token into chat, HackOS, screenshots or commits.
