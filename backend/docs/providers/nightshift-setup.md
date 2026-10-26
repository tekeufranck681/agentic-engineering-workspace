# Nightshift setup: Mac mini runtime host, ZBook backend (ENG-003)

Nightshift is the product's primary AI runtime (v2.0 POWER requirement). It has no x86_64 Linux edition, so it runs on an Apple Silicon Mac mini and the backend on the ZBook (Ubuntu) reaches it over the network:

```text
ZBook (Ubuntu)                               Mac mini (Apple Silicon)
backend, tests, smoke check  --- LAN --->    Nightshift, Meterless Runtime :8088
```

**Sources:** official Meterless provider guide (`docs/agent-ready/add-meterless-provider.md`) and hotspot page (`docs/products/nightshift/hotspot.md`) in github.com/Meterless/Meterless, plus meterless.ai. What the public docs leave out was filled in from the first live run and the Mac setup report (both 2026-10-26); where the Mac app differs from the docs, this guide says so.

## Facts from the official docs

| Item | Value |
|---|---|
| Editions | Mac **M1 or later** (free), Windows 10/11 with GPU, DGX Spark. The browser-only web edition does not satisfy ENG-003. Intel Macs are not supported |
| API | OpenAI-compatible, default base URL `http://127.0.0.1:8088/v1` |
| Token | written by the runtime to `<stateDir>/proxy-token` (the Mac M1-M4 app names the file `runtime-token`, see below); the placeholder `rt-local` is rejected |
| Headers | `Authorization: Bearer <token>` and `meterless-app: agentic-engineering-workspace` on every call; `meterless-scope: user` on chat calls |
| Status | `GET /v1/models`: 401/403 unauthorized, 200 with `meterless/*` ids online, anything else offline. `/healthz` only proves the process is up |
| Lanes | `meterless/auto`, `fast`, `deep`, `cheap`, `local`, `fusion`, plus `meterless/<class>` forms. Routing modes, not model names |
| Timeouts | a cold model load can take minutes; the client allows 180 s |
| Other machines | "turn on hotspot mode and paste its connect link once" |

## Observed on the live runtime (2026-10-26)

Nightshift on the Mac mini, smoke check from the ZBook over the LAN: PASS (`docs/evidence/nightshift-smoke-2026-10-26.md`).

| Item | Observed |
|---|---|
| Host | Mac mini, Apple M4, 16 GB RAM, macOS 26.5.1, 13 GiB free disk |
| App | `Nightshift M1-M4.app` 0.92.7 (bundle id `ai.meterless.nightshift.m1m4`; `/healthz`: `"build": "m1-m4"`). The engine runs inside the app window (`"served": "in-tab"`), so keep the app open. It embeds the web build: a few features, such as the provider "Diagnose" button, answer "not served in the web build" (harmless) |
| Signing | ad-hoc signature, not notarized: `codesign --verify` passes, `spctl` (Gatekeeper) rejects it. M3 reviewed this and approved running it |
| Token | the file `~/Library/Application Support/ai.meterless.nightshift.m1m4/runtime-token` (not `proxy-token`), also shown under **Console ▸ API key** (the runtime's own 401 hint). Rotating the key in the app invalidates every copy |
| Hotspot mode | switch in the app's Settings (hotspot / Network area). Nightshift then also listens on the Wi-Fi address (`<LAN-IP>:8088`), and `/healthz` (no token needed) names both URLs. The connect link has the form `http://<host>:8088/connect#k=<token>`: **it contains the token**, so treat it as a secret |
| LAN address | assigned by DHCP with a 1-hour lease, and it changed once during setup. The hotspot binds to the current address, so after a change, update `NIGHTSHIFT_BASE_URL` and toggle hotspot off and on. A DHCP reservation or wired Ethernet keeps it stable |
| Providers | NVIDIA key under Settings ▸ Providers ▸ Cloud provider keys ▸ NVIDIA (`/healthz`: `"cloud": {"keys": ["nvidia"]}`). Its "Free Endpoint" is a trial allowance (credits plus a per-minute cap), not unlimited |
| Models listed | 19 ids: 6 `meterless/*` lanes; 5 `nvidia/*` cloud models (`nemotron-3.5-lightning-30b-a3b`, `nemotron-3-ultra-550b-a55b`, `nemotron-3.5-bolt-e4b` and two embedding models); 8 `webllm/*` local models that run in the app (Llama 3.2 1B/3B, Qwen 2.5 1.5B/3B, Qwen 2.5 Coder 3B, Gemma 2 2B, Phi 3.5 Mini, SmolLM2 1.7B) |
| Local models | none downloaded: the in-app download failed ("Load failed") although the Mac reaches huggingface.co. There is no local fallback, so every call goes to NVIDIA and `meterless/local` does not work yet |
| Routing | a lane does not pin a model, and the same lane can change between calls (`learned-router` policy): `auto` was answered by `nemotron-3.5-bolt-e4b` in one run and by `nemotron-3.5-lightning-30b-a3b` ten minutes later; `fast` and `deep` were both answered by `nemotron-3.5-bolt-e4b`. Requesting an `nvidia/*` id directly pins it: `nvidia/nemotron-3.5-lightning-30b-a3b` answered as itself, receipt included |
| Reply | the response `model` field names the model that answered. A `meterless` object (schema `meterless.compute_receipt.v1`) carries `routed_model`, `winning_route {kind, model, provider, tier}`, `receipt_id`, `decision_id`, `usage`, `cost` and `egress`; `requested_model` and `provider_model` echo the lane. `receipt_envelope` was null (unsigned). No `meterless-*` response headers |
| Privacy | the nested `receipt.prompt_preview` holds the prompt text, so raw receipts are never stored as evidence; the client keeps a hash and the key list |
| Cost and speed | `cost.actual_usd` 0 within the NVIDIA trial allowance; 0.5 to 7.8 s per call. The reasoning model `nemotron-3.5-lightning-30b-a3b` spent 184 to 198 completion tokens on a one-word reply, so keep `max_tokens` generous |
| Other servers | an Ollama server listens on the Mac's `127.0.0.1:11434`, one of the provider guide's auto-detect ports. It is loopback-only; always use `:8088` explicitly |

## On the Mac mini

1. **Check the chip.** Apple menu, About This Mac: it must say *Apple M1* or later. Note the memory size.
2. **Install Nightshift for Mac M1+** from https://meterless.ai/Nightshift/M1+/ and launch it. The 0.92.7 installer (`Nightshift-Setup-mac-m1.dmg`, SHA-256 `f387ea2668ff8f767f3e95a5e5463c975e738ab9836768b09ab21ca09e336fa8`) is ad-hoc signed and not notarized, so Gatekeeper rejects it; running it needs the Mac owner's explicit approval.
3. **Give it at least one working lane.** With limited memory, prefer small local models, or add a cloud provider under Settings ▸ Providers ▸ Cloud provider keys so heavy reasoning runs in the cloud while Nightshift stays the runtime the app talks to. Cloud providers bill your own key; don't add a paid one without agreeing it with the team. For the optional Nemotron award (ENG-053), add the NVIDIA credentials there. Once a key is in, `/healthz` shows `"cloud": {"keys": ["nvidia"]}` and `/v1/models` gains the `nvidia/*` ids.
4. **Find the token.** The app shows it under **Console ▸ API key**. The Mac app also keeps it in a file; check that it exists without printing it:
   ```bash
   TOKEN_FILE="$HOME/Library/Application Support/ai.meterless.nightshift.m1m4/runtime-token"
   [ -s "$TOKEN_FILE" ] && echo "token file present"
   ```
5. **Check the runtime locally** (Terminal on the Mac):
   ```bash
   read -r TOKEN < "$TOKEN_FILE"
   curl -s http://127.0.0.1:8088/v1/models \
     -H "Authorization: Bearer $TOKEN" -H "meterless-app: agentic-engineering-workspace" | head -c 800
   ```
   Expect a JSON list containing `meterless/*` ids.
6. **Turn on hotspot mode** in the app's Settings (hotspot / Network area). Nightshift then also listens on the Mac's Wi-Fi address, and `/healthz` from another machine returns 200 and names the LAN URL. The connect link it shows contains the token: never paste it into chat, tickets or `NIGHTSHIFT_BASE_URL`.
7. **Note the Mac's LAN address:** `ipconfig getifaddr en1` (Wi-Fi on a Mac mini; `en0` is its Ethernet port). If the macOS firewall is on, allow incoming connections for Nightshift. The address can change with DHCP (see troubleshooting).
8. **Keep it awake while serving:** System Settings, Energy, enable *Prevent automatic sleeping when the display is off* (`pmset -g` then shows `sleep 0`).
9. **Allow fetching the token over SSH** (ZBook step 2): System Settings, General, Sharing, turn on *Remote Login*.

## On the ZBook

1. **Reachability.** First without the token: JSON naming `http://<mac-ip>:8088` means the Mac is reachable.
   ```bash
   curl -s -m 5 http://<mac-ip>:8088/healthz | head -c 300; echo
   ```
   Then with the token, typed without echo so it stays out of shell history:
   ```bash
   read -rs TOKEN   # paste the token, press Enter
   curl -s -o /dev/null -w '%{http_code}\n' http://<mac-ip>:8088/v1/models \
     -H "Authorization: Bearer $TOKEN" -H "meterless-app: agentic-engineering-workspace"
   ```
   `200` is good; `401` means a wrong or rotated token; `000` means not reachable (hotspot mode off, firewall, Mac asleep, different network, or the Mac's address changed).
2. **Configure the backend** in the repo-root `.env` (never committed):
   ```bash
   NIGHTSHIFT_BASE_URL=http://<mac-ip>:8088/v1
   NIGHTSHIFT_TOKEN=<the API key>
   ```
   The token can come straight from the Mac over SSH without being displayed. From the repo root (asks for the Mac password; writes nothing if SSH fails):
   ```bash
   umask 077
   tok="$(ssh <mac-user>@<mac-ip> 'cat "$HOME/Library/Application Support/ai.meterless.nightshift.m1m4/runtime-token"')" \
     && [ -n "$tok" ] && printf 'NIGHTSHIFT_TOKEN=%s\n' "$tok" >> .env; unset tok
   ```
   Keep `.env` private (`chmod 600 .env`). A pasted URL ending in `/v1/models`, `/v1/chat/completions`, `/healthz` or `/connect` is normalized automatically; a connect link's token part is dropped, so the token still goes into `NIGHTSHIFT_TOKEN`.
3. **Run the smoke check** from the repo root. The ZBook's system Python is 3.10 and the backend needs 3.11+, so it runs in a throwaway Python 3.12 container; `--network host` lets it reach the Mac:
   ```bash
   docker run --rm --network host --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 \
     -v "$PWD:/repo" -w /repo/backend python:3.12-slim bash -c \
     "pip install -q --user --no-warn-script-location -r requirements.txt && \
      python -m app.modules.nightshift.smoke --evidence-out ../docs/evidence/nightshift-smoke-$(date +%F).md"
   ```
   The module reads the repo-root `.env` itself. Expected end: `SMOKE OK: the application reached Nightshift and got real model responses.`, exit code 0. To also verify a pinned Nemotron model (ENG-053), list every lane, since `--lane` replaces the defaults: `--lane meterless/auto --lane meterless/fast --lane meterless/deep --lane nvidia/nemotron-3.5-lightning-30b-a3b`.
4. **Review the evidence file** before committing it. It records the endpoint, advertised ids, the model that answered each lane (from the routing receipt when the runtime returns one), latency and token counts. The token is never written, and the smoke refuses to save a file containing it.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `CONFIG: NIGHTSHIFT_TOKEN is not set` / `placeholder 'rt-local'` | `.env` missing the real token |
| `probe: offline` with connection refused or timeout | Mac asleep, Nightshift closed (the engine runs in its window), hotspot mode off, firewall, or the Mac's address changed: update `NIGHTSHIFT_BASE_URL`, then toggle hotspot off and on |
| `probe: offline`, "listed no meterless/* ids" | something else answers on that port (another OpenAI-compatible server) |
| `probe: unauthorized` | token wrong or rotated in the app; fetch it again (ZBook step 2) |
| `401` with code `runtime_token_missing` | the request carried no `Authorization` header |
| `NightshiftRateLimitedError` (HTTP 429) | likely the per-minute cap of the NVIDIA trial allowance; wait and retry |
| `meterless/local` or a `webllm/*` id fails or hangs | no local model downloaded; the in-app download failed on 2026-10-26 |
| `NightshiftProviderError` with an `*_empty_response` code | reported by other teams when a reasoning model spends the whole `max_tokens` budget before answering; the smoke uses 1024 |
| first call very slow | cold model load; allowed up to 180 s |

## What to send M3 after setting up another host

The evidence file, the Mac's chip and memory, the Nightshift version, which lanes and providers are configured, and anything that differs from this guide. Never paste the token or the connect link into chat, HackOS, screenshots or commits.
