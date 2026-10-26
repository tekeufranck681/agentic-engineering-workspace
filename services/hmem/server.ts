// hmem-service: a thin HTTP API over the official Meterless H-MEM reference.
//
// The engine is vendored unmodified under vendor/hmem (Meterless/Meterless at
// VENDORED_SHA, Apache-2.0); this file is our own wrapper, zero dependencies
// (node:http). The image build runs the official conformance suite against the
// same vendored module and /healthz reports that scorecard.
//
// * One HMEM instance per project, persisted under $HMEM_DATA_DIR/<projectId>/
//   (state.json rewritten per mutation, ledger.jsonl append-only). The
//   reference filters recall only by chatId, so stores are never shared.
// * Single writer: exactly one process may own a data directory.
// * Model-free: no credentials, no mining endpoint. Model-assisted extraction
//   stays in the backend behind ModelGateway (ADR adr-meterless-engine.md).
// * Responses never include embeddings; logs carry ids and status only.

import fs from "node:fs";
import http from "node:http";
import path from "node:path";

import { HMEM } from "./vendor/hmem/reference/src/index.ts";
import type { FeedbackKind, LedgerEntry, MemoryRecord, QueryResult } from "./vendor/hmem/reference/src/index.ts";

const VENDORED_SHA = "1742dec56a66e58eef9dda2d2b865823758ca8cd";
const ENGINE = "meterless-hmem";
const HERE = path.dirname(new URL(import.meta.url).pathname);
const DATA_DIR = path.resolve(process.env.HMEM_DATA_DIR ?? "/data");
const PORT = Number(process.env.HMEM_PORT ?? 8099);
const HOST = process.env.HMEM_HOST ?? "0.0.0.0";
const ACTOR = "aew-backend";

const MAX_BODY_BYTES = 64 * 1024;
const MAX_TEXT = 4000;
const MAX_SHORT = 200;
const MAX_TAGS = 20;
const PROJECT_ID = /^[a-z0-9][a-z0-9-]{0,63}$/;
const MEMORY_ID = /^mem-[1-9][0-9]{0,9}$/;
const TYPES = ["personal", "factual", "preference", "general"];
const LAYERS = ["short_term", "working", "long_term"];
const ORIGINS = [
  "chat_message", "user_correction", "file_save", "file_open", "file_edit",
  "model_response", "plan_completion", "document", "manual", "dream", "sleep_synthesis",
];
const FEEDBACK = ["helpful", "not_helpful", "wrong"];

const engineVersion: string = JSON.parse(
  fs.readFileSync(path.join(HERE, "vendor/hmem/reference/package.json"), "utf-8")
).version;

class HttpError extends Error {
  constructor(readonly status: number, readonly kind: string, message: string) {
    super(message);
  }
}

const invalid = (message: string) => new HttpError(400, "invalid_request", message);
const notFound = (message: string) => new HttpError(404, "not_found", message);

// ------------------------------------------------------------------ stores

const stores = new Map<string, HMEM>();

function storeDir(projectId: string): string {
  if (!PROJECT_ID.test(projectId)) throw invalid("project id must be lowercase letters, digits and dashes");
  return path.join(DATA_DIR, projectId);
}

/** The project's engine; undefined for reads of a project that has no store yet. */
function store(projectId: string, create: boolean): HMEM | undefined {
  const cached = stores.get(projectId);
  if (cached) return cached;
  const dir = storeDir(projectId);
  if (!create && !fs.existsSync(path.join(dir, "state.json"))) return undefined;
  const engine = new HMEM({ persistDir: dir, actor: ACTOR });
  stores.set(projectId, engine);
  return engine;
}

function mustGet(engine: HMEM | undefined, memoryId: string): MemoryRecord {
  if (!MEMORY_ID.test(memoryId)) throw invalid("memory id looks like mem-<n>");
  const record = engine?.store.get(memoryId);
  if (!record) throw notFound(`unknown memory ${memoryId}`);
  return record;
}

function publicRecord(record: MemoryRecord): Omit<MemoryRecord, "embedding"> {
  const { embedding: _embedding, ...rest } = record;
  return rest;
}

function publicResult(result: QueryResult) {
  return {
    memories: result.memories.map((m) => ({ memory: publicRecord(m.memory), relevance: m.relevance })),
    context: result.context,
    trace: result.trace,
  };
}

function projectCount(): number {
  if (!fs.existsSync(DATA_DIR)) return 0;
  return fs
    .readdirSync(DATA_DIR, { withFileTypes: true })
    .filter((d) => d.isDirectory() && fs.existsSync(path.join(DATA_DIR, d.name, "state.json"))).length;
}

/** The scorecard the image build wrote; null when the service runs outside the image. */
function conformance(): { passed: number; total: number; ranAt: string | null } | null {
  try {
    const log = fs.readFileSync(path.join(HERE, "conformance.log"), "utf-8");
    const score = log.match(/(\d+)\/(\d+) checks passed/);
    if (!score) return null;
    const ranAt = log.match(/^ran_at=(\S+)$/m);
    return { passed: Number(score[1]), total: Number(score[2]), ranAt: ranAt ? ranAt[1] : null };
  } catch {
    return null;
  }
}

// -------------------------------------------------------------- validation

type Json = Record<string, unknown>;

function text(body: Json, key: string, max: number, required: boolean): string | undefined {
  const value = body[key];
  if (value === undefined || value === null) {
    if (required) throw invalid(`${key} is required`);
    return undefined;
  }
  if (typeof value !== "string" || value.trim() === "") throw invalid(`${key} must be a non-empty string`);
  if (value.length > max) throw invalid(`${key} is longer than ${max} characters`);
  return value;
}

function oneOf(body: Json, key: string, allowed: string[]): string | undefined {
  const value = body[key];
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "string" || !allowed.includes(value)) throw invalid(`${key} must be one of ${allowed.join(", ")}`);
  return value;
}

function strings(value: unknown, key: string, maxItems: number): string[] | undefined {
  if (value === undefined || value === null) return undefined;
  if (!Array.isArray(value) || value.length > maxItems) throw invalid(`${key} must be a list of at most ${maxItems} strings`);
  for (const item of value) {
    if (typeof item !== "string" || item === "" || item.length > MAX_SHORT) {
      throw invalid(`${key} entries must be non-empty strings of at most ${MAX_SHORT} characters`);
    }
  }
  return value as string[];
}

function unit(body: Json, key: string): number | undefined {
  const value = body[key];
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) throw invalid(`${key} must be a number from 0 to 1`);
  return value;
}

function addInput(body: Json) {
  let provenance;
  if (body.provenance !== undefined && body.provenance !== null) {
    const p = body.provenance as Json;
    if (typeof p !== "object" || Array.isArray(p)) throw invalid("provenance must be an object");
    if (typeof p.learnedAt !== "number" || !Number.isFinite(p.learnedAt)) throw invalid("provenance.learnedAt must be epoch milliseconds");
    const origin = oneOf(p, "origin", ORIGINS);
    if (!origin) throw invalid("provenance.origin is required");
    provenance = {
      origin,
      learnedAt: p.learnedAt,
      label: text(p, "label", MAX_SHORT, true)!,
      refs: strings(p.refs, "provenance.refs", 50),
    };
  }
  return {
    content: text(body, "content", MAX_TEXT, true)!,
    source: text(body, "source", MAX_SHORT, true)!,
    type: oneOf(body, "type", TYPES) as MemoryRecord["type"] | undefined,
    layer: oneOf(body, "layer", LAYERS) as MemoryRecord["layer"] | undefined,
    tags: strings(body.tags, "tags", MAX_TAGS),
    confidence: unit(body, "confidence"),
    provenance: provenance as MemoryRecord["provenance"] | undefined,
    chatId: text(body, "chatId", MAX_SHORT, false),
    missionId: text(body, "missionId", MAX_SHORT, false),
    goalRunId: text(body, "goalRunId", MAX_SHORT, false),
  };
}

function queryOptions(body: Json) {
  const topN = body.topN;
  if (topN !== undefined && (!Number.isInteger(topN) || (topN as number) < 1 || (topN as number) > 20)) {
    throw invalid("topN must be an integer from 1 to 20");
  }
  return {
    topN: topN as number | undefined,
    threshold: unit(body, "threshold"),
    chatId: text(body, "chatId", MAX_SHORT, false),
  };
}

// ------------------------------------------------------------------ routes

type Handler = (params: string[], body: Json) => [number, unknown];

const routes: Array<[string, RegExp, Handler]> = [
  ["GET", /^\/healthz$/, () => [200, {
    status: "ok",
    engine: ENGINE,
    engineVersion,
    vendoredSha: VENDORED_SHA,
    conformance: conformance(),
    projects: projectCount(),
  }]],
  ["GET", /^\/projects\/([^/]+)\/memories$/, ([projectId]) => {
    const engine = store(projectId, false);
    const records = engine ? engine.store.all().sort((a, b) => a.timestamp - b.timestamp || a.id.localeCompare(b.id)) : [];
    return [200, { projectId, memories: records.map(publicRecord) }];
  }],
  ["POST", /^\/projects\/([^/]+)\/memories$/, ([projectId], body) => {
    const input = addInput(body);
    return [201, { memory: publicRecord(store(projectId, true)!.add(input)) }];
  }],
  ["GET", /^\/projects\/([^/]+)\/memories\/([^/]+)$/, ([projectId, memoryId]) => {
    return [200, { memory: publicRecord(mustGet(store(projectId, false), memoryId)) }];
  }],
  ["POST", /^\/projects\/([^/]+)\/query$/, ([projectId], body) => {
    const query = text(body, "query", MAX_TEXT, true)!;
    return [200, publicResult(store(projectId, true)!.query(query, queryOptions(body)))];
  }],
  ["POST", /^\/projects\/([^/]+)\/memories\/([^/]+)\/feedback$/, ([projectId, memoryId], body) => {
    const kind = oneOf(body, "kind", FEEDBACK) as FeedbackKind | undefined;
    if (!kind) throw invalid(`kind must be one of ${FEEDBACK.join(", ")}`);
    const engine = store(projectId, false);
    mustGet(engine, memoryId);
    engine!.feedback(memoryId, kind);
    return [200, { memory: publicRecord(mustGet(engine, memoryId)) }];
  }],
  ["GET", /^\/projects\/([^/]+)\/memories\/([^/]+)\/history$/, ([projectId, memoryId]) => {
    const engine = store(projectId, false);
    mustGet(engine, memoryId);
    const entries: LedgerEntry[] = [...engine!.ledger.history(memoryId)];
    return [200, { memoryId, entries }];
  }],
];

// -------------------------------------------------------------------- HTTP

function readBody(req: http.IncomingMessage): Promise<Json> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    let size = 0;
    req.on("data", (chunk: Buffer) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(new HttpError(413, "too_large", `request body is larger than ${MAX_BODY_BYTES} bytes`));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => {
      if (size === 0) return resolve({});
      try {
        const parsed = JSON.parse(Buffer.concat(chunks).toString("utf-8"));
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) throw new Error("not an object");
        resolve(parsed as Json);
      } catch {
        reject(invalid("request body must be a JSON object"));
      }
    });
    req.on("error", reject);
  });
}

function send(res: http.ServerResponse, status: number, payload: unknown): void {
  const body = JSON.stringify(payload);
  res.writeHead(status, { "content-type": "application/json", "content-length": Buffer.byteLength(body) });
  res.end(body);
}

function toHttpError(err: unknown): HttpError {
  if (err instanceof HttpError) return err;
  if (err instanceof URIError) return invalid("malformed path");
  // The engine refuses some input itself, e.g. a record without a source.
  if (err instanceof Error && err.message.startsWith("H-MEM:")) return new HttpError(400, "engine_rejected", err.message);
  console.error(err);
  return new HttpError(500, "internal", "hmem-service failed; see its log");
}

const server = http.createServer(async (req, res) => {
  const started = process.hrtime.bigint();
  const url = new URL(req.url ?? "/", "http://hmem.local");
  let status = 500;
  try {
    const candidates = routes.filter(([, pattern]) => pattern.test(url.pathname));
    if (candidates.length === 0) throw notFound(`no route for ${url.pathname}`);
    const route = candidates.find(([method]) => method === req.method);
    if (!route) throw new HttpError(405, "method_not_allowed", `${req.method} is not allowed on ${url.pathname}`);
    const params = route[1].exec(url.pathname)!.slice(1).map(decodeURIComponent);
    const body = req.method === "POST" ? await readBody(req) : {};
    const [code, payload] = route[2](params, body);
    status = code;
    send(res, status, payload);
  } catch (err) {
    const e = toHttpError(err);
    status = e.status;
    send(res, status, { error: { kind: e.kind, message: e.message } });
  } finally {
    const ms = Number(process.hrtime.bigint() - started) / 1e6;
    console.log(JSON.stringify({ at: new Date().toISOString(), method: req.method, path: url.pathname, status, ms: Math.round(ms) }));
  }
});

fs.mkdirSync(DATA_DIR, { recursive: true });
fs.accessSync(DATA_DIR, fs.constants.W_OK);
server.listen(PORT, HOST, () => {
  const score = conformance();
  console.log(
    `hmem-service: ${ENGINE} ${engineVersion} (Meterless ${VENDORED_SHA.slice(0, 7)}) on ${HOST}:${PORT}, ` +
      `data ${DATA_DIR}, conformance ${score ? `${score.passed}/${score.total}` : "not recorded"}`
  );
});

for (const signal of ["SIGTERM", "SIGINT"] as const) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
