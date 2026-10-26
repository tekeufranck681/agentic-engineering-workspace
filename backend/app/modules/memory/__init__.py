"""Project memory on the Meterless H-MEM engine (ENG-018).

H-MEM is the product's Meterless Engine (ADR ``docs/decisions/adr-meterless-engine.md``).
The official reference runs unmodified in the ``hmem-service`` sidecar
(``services/hmem``); this module is the backend's only way to it:

* ``AgentMemoryProvider`` and its ``MeterlessHMemProvider`` (HTTP, one engine
  store per project);
* the write path: ``record_verified_lesson`` stores only lessons an
  independent evaluator verified, with provenance back to the run;
* the read path: ``recall`` turns a capability's request into an H-MEM query
  and a clearly labelled, supplemental prompt block plus text-free evidence;
* ``api``: the visible API (list, query, record, feedback, ledger history).

Memory is derived and supplemental, never authoritative: locked requirements,
ADRs and contracts stay in PostgreSQL and win on conflict. Failures fail
closed with ``MemoryUnavailableError``; memory is never silently skipped.
"""
