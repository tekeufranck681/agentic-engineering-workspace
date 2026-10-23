# ZETARIS_INSTALL Evidence — Complete Operational Log

## 1. Stack Inventory & Component Versions

*(per v2.0 evidence delta: "component/version")*

* **Operator:** Member2
* **Date:** 2026-10-23
* **Command:** `docker compose ps` *(from `zetaris-platform` clone root)*

### Container Inventory

| Name | Image (Tag) | Status | Ports |
| :--- | :--- | :--- | :--- |
| `zetaris-api-1` | `zetarishackathon.azurecr.io/zetaris-ndp-api:2.4.3-v2.4.3.1-hackathon.a2848d8a41fa21673a0d719deb41b675412710fe` | Up 2 hours (healthy) | `127.0.0.1:8888-8889->8888-8889/tcp` |
| `zetaris-driver-1` | `zetarishackathon.azurecr.io/zetaris-ndp-driver:2.4.3-v2.4.3.1-hackathon.cb88df0b255aba5a9a9eda96483fc877cc82df80` | Up 2 hours (healthy) | `127.0.0.1:4040->4040/tcp`<br>`127.0.0.1:10000->10000/tcp`<br>`127.0.0.1:32769->8080/tcp` |
| `zetaris-postgres-1` | `postgres:16-alpine` | Up 2 hours (healthy) | `127.0.0.1:32768->5432/tcp` |
| `zetaris-ui-1` | `zetarishackathon.azurecr.io/zetaris-new-ui:2.4.3-v2.4.3.1-hackathon.88e49b0db015979a2d071d2d68a6865d38a39f15` | Up 2 hours (healthy) | `0.0.0.0:3000->3000/tcp` |

### Notes
* **Platform Version:** `2.4.3` (build for the hackathon track, suffix `2.4.3.1-hackathon`).
* **Network Binding:** All runtime surfaces loopback-only (`127.0.0.1`) except the UI (`0.0.0.0:3000`, needed for sign-in).
* **Metastore & Databases:**
  * The Zetaris-internal Postgres metastore is ephemeral localhost (`127.0.0.1:32768->5432`).
  * The engineering read model is reached by Zetaris via `host.docker.internal:5433` against the product DB.

---

## 2. Platform Verification Log (`verify.sh`)

*(mvp-feature-lock v2.0 verification: "Zetaris verify.sh (nine checks)")*

* **Operator:** Member2
* **Machine:** local Windows host (bash via UCRT64/MSYS2)
* **Date:** 2026-10-23
* **Command:** `bash verify.sh` *(from the Zetaris platform clone root, stack running 2 days)*
* **Sanitization:** None required — output contains no secrets (login account email shown; password not shown anywhere).

```text
=== verify.sh output (verbatim) ===
Zetaris platform -- verify
==========================
  PASS  postgres: running (healthy)
  PASS  driver: running (healthy)
  PASS  api: running (healthy)
  PASS  ui: running (healthy)
  PASS  init: completed (exit 0 -- this is correct for a one-shot job)
  PASS  bootstrap: completed (exit 0 -- this is correct for a one-shot job)
  PASS  ui responding (/api/config 200)
  PASS  login as admin@zetaris.com
  PASS  query through ui -> api -> driver -> spark

All 9 checks passed. The platform is ready on http://localhost:3000
Sign in as admin@zetaris.com
```

> **Note:** The 9th check (`query through ui -> api -> driver -> spark`) is sample-data plumbing, NOT the application integration. The decision-relevant internal-data integration is proven separately:
>
> * **ENG-017 spike (2026-10-23T08:00Z):** `CREATE DATASOURCE aew_pg` + REGISTER + governed qualified query with `QueryEvidence` (see `infra/zetaris/ENG-017-SPIKE.md`).
> * **Publisher apply + check (2026-10-23T09:12Z / 09:42Z):** `docs/evidence/zetaris-publish-2026-10-23.json` plus a successful `publisher --check` run reporting **READ MODEL FRESH** (report `2ba83edf-e8ae-456c-b90a-6c88df0d68d8`, counts matched 1/1 + 1/1, both views queryable).

---

## 3. Hardware Preflight Evidence

*(Participant guide operational constraint: Zetaris Docker allocation >= 8 GB RAM, 4 CPUs, 15 GB disk; practical host recommendation 16 GB RAM)*

* **Operator:** Member2
* **Machine:** local Windows host
* **Date:** 2026-10-23
* **Command:** `docker info | Select-String -Pattern "Total Memory|CPUs"`

### Initial Check
* **CPUs:** `8` -> requirement >= 4 CPUs: **PASS**
* **Total Memory:** `7.386 GiB` -> requirement >= 8 GB RAM: **FAIL** (by ~0.7 GiB, letter of the rule)
* **Disk 15 GB:** Not measured here; Zetaris images ~a few GB, workspace small - assumed OK, verify if organizers ask.

**Verdict:** CPUs sufficient; Docker VM memory allocation is BELOW the stated 8 GB minimum. The stack currently passes `verify.sh` 9/9 (see `zetaris-verify-2026-10-23.md`), i.e. it *works*, but the sponsor verification line says >= 8 GB — "configuration is not completion" cuts both ways.

### Operator Action Taken
Docker Desktop: **Settings** -> **Resources** -> **Advanced** -> **Memory**: Set to **8.0 GB** (or higher, host permitting) -> **Apply & restart**.

### Follow-Up Result
*(2026-10-23, same day, after raising Docker Desktop memory allocation and restarting)*

* **CPUs:** `8` -> **PASS**
* **Total Memory:** `9.386 GiB` -> requirement >= 8 GB RAM: **PASS**

**Verdict (Final):** Hardware preflight **PASSES** the participant-guide constraint (>= 8 GB RAM, 4 CPUs). Stack re-verified healthy earlier the same day (`zetaris-verify-2026-10-23.md`, 9/9).