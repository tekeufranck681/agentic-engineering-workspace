"""Aggregation logic behind the sponsor health endpoint (ENG-042).

Each sponsor gets a *distinct* live check, per the task acceptance:

* Zetaris   - datasource inventory + Lightning inventory + a real governed
              SELECT returning rows (never SELECT 1, never a liveness ping);
* Nightshift - the provider-guide status probe (authenticated GET /v1/models,
              /healthz is explicitly not trusted), optionally plus one chat;
* Engine    - the H-MEM sidecar's engine/conformance report;
* Cursor    - build provenance only: reported as not_checked because no
              runtime probe exists for an editor.

Client construction is injected as zero-arg factories so tests can supply
MockTransport-backed clients without touching the network. Default factories
read the same per-module settings as the rest of the backend.
"""

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from app.modules.integrations.registry import LastSuccessRegistry
from app.modules.integrations.schemas import (
    ALL_SPONSORS,
    CURSOR,
    HealthStatus,
    METERLESS_ENGINE,
    NIGHTSHIFT,
    RUNTIME_SPONSORS,
    ZETARIS,
    SponsorHealthCheck,
    SponsorHealthReport,
)
from app.modules.memory.config import MemorySettings
from app.modules.memory.errors import AgentMemoryError, MemoryUnavailableError
from app.modules.memory.provider import MeterlessHMemProvider
from app.modules.nightshift.client import ChatMessage, NightshiftClient
from app.modules.nightshift.config import NightshiftSettings
from app.modules.nightshift.errors import NightshiftConfigError, NightshiftError
from app.modules.nightshift.evidence import RuntimeState
from app.modules.zetaris.config import ZetarisSettings
from app.modules.zetaris.errors import ZetarisConfigError, ZetarisError
from app.modules.zetaris.tool import RunSqlInput, run_sql_tool

# Same real-data truth probe as the Zetaris smoke: sample dataset, real rows.
TRUTH_STATEMENT = "SELECT * FROM NY_TAXI.customers LIMIT 5"
LIGHTNING_STATEMENT = "SHOW LIGHTNING DATABASES"
# Chat ping used only by the smoke command's --chat check; tiny and bounded.
CHAT_PING = "Reply with the single word: ok"
CHAT_LANE = "meterless/auto"
_OK_ENGINE_STATES = frozenset({"ok", "healthy", "up", "passing", "ready"})

ClientFactory = Callable[[], Any]


def default_zetaris_factory() -> Any:
    """Build the Zetaris client from ZETARIS_* settings (raises when unconfigured)."""
    from app.modules.zetaris.client import ZetarisClient

    return ZetarisClient(ZetarisSettings.from_env())


def default_nightshift_factory() -> NightshiftClient:
    return NightshiftClient(NightshiftSettings.from_env())


def default_engine_factory() -> MeterlessHMemProvider:
    # The sidecar holds no credentials, so this always builds; reachability is
    # decided by the health() call itself.
    return MeterlessHMemProvider(MemorySettings())


class SponsorHealthService:
    """Runs the per-sponsor checks and rolls them into one report."""

    def __init__(
        self,
        *,
        zetaris_factory: ClientFactory | None = None,
        nightshift_factory: ClientFactory | None = None,
        engine_factory: ClientFactory | None = None,
        registry: LastSuccessRegistry | None = None,
    ) -> None:
        self._zetaris_factory = zetaris_factory or default_zetaris_factory
        self._nightshift_factory = nightshift_factory or default_nightshift_factory
        self._engine_factory = engine_factory or default_engine_factory
        self._registry = registry or LastSuccessRegistry()
        self._secrets: tuple[str, ...] = ()

    @classmethod
    def default(cls) -> "SponsorHealthService":
        """Env-backed service used by the FastAPI dependency."""
        return cls()

    # ------------------------------------------------------------- public API

    def run_all(self, *, include_chat: bool = False) -> SponsorHealthReport:
        checks = [
            self.check_zetaris(),
            self.check_nightshift(include_chat=include_chat),
            self.check_engine(),
            self.check_cursor(),
        ]
        return SponsorHealthReport(
            generated_at=datetime.now(timezone.utc),
            overall=self._overall(checks),
            checks=checks,
        )

    def check(self, sponsor: str, *, include_chat: bool = False) -> SponsorHealthCheck:
        if sponsor == ZETARIS:
            return self.check_zetaris()
        if sponsor == NIGHTSHIFT:
            return self.check_nightshift(include_chat=include_chat)
        if sponsor == METERLESS_ENGINE:
            return self.check_engine()
        if sponsor == CURSOR:
            return self.check_cursor()
        raise KeyError(sponsor)

    def known_sponsors(self) -> tuple[str, ...]:
        return ALL_SPONSORS

    # ----------------------------------------------------------------- Zetaris

    def check_zetaris(self) -> SponsorHealthCheck:
        try:
            client = self._zetaris_factory()
        except ZetarisConfigError as exc:
            return self._not_checked(ZETARIS, str(exc))
        self._remember_secret(client)
        try:
            datasources = client.list_datasources()
            lightning = run_sql_tool(RunSqlInput(statement=LIGHTNING_STATEMENT), client)
            truth = run_sql_tool(RunSqlInput(statement=TRUTH_STATEMENT), client)
        except ZetarisError as exc:
            return self._failed(ZETARIS, f"zetaris check failed: {self._scrub(str(exc))}")
        finally:
            client.close()

        provenance = {
            "datasources": list(datasources),
            "lightning_database_count": lightning.row_count,
            "truth_statement": TRUTH_STATEMENT,
            "truth_row_count": truth.evidence.row_count,
            "query_id": truth.evidence.query_id,
            "request_id": truth.evidence.request_id,
            "org_id": truth.evidence.org_id,
            "endpoint": truth.evidence.endpoint,
            "duration_ms": truth.evidence.duration_ms,
        }
        if truth.evidence.row_count == 0 or not datasources:
            return SponsorHealthCheck.build(
                ZETARIS,
                HealthStatus.DEGRADED,
                latency_ms=truth.evidence.duration_ms,
                detail="reachable and authenticated, but the truth query returned no rows "
                "or no datasources are registered; verify the read model and sample data",
                provenance=self._scrub_mapping(provenance),
                last_success=self._registry.get(ZETARIS),
            )
        last_success = self._registry.record(ZETARIS, provenance)
        return SponsorHealthCheck.build(
            ZETARIS,
            HealthStatus.VERIFIED,
            latency_ms=truth.evidence.duration_ms,
            detail="governed REST query returned real rows with grounded evidence",
            provenance=self._scrub_mapping(provenance),
            last_success=last_success,
        )

    # -------------------------------------------------------------- Nightshift

    def check_nightshift(self, *, include_chat: bool = False) -> SponsorHealthCheck:
        try:
            client = self._nightshift_factory()
        except NightshiftConfigError as exc:
            return self._not_checked(NIGHTSHIFT, str(exc))
        self._remember_secret(client)
        provenance: dict[str, Any] = {}
        try:
            try:
                probe = client.probe()
            except NightshiftError as exc:
                return self._failed(
                    NIGHTSHIFT, f"nightshift probe failed: {self._scrub(str(exc))}"
                )

            provenance = {
                "endpoint": probe.endpoint,
                "http_status": probe.http_status,
                "model_count": len(probe.model_ids),
                "meterless_lanes": [
                    model_id
                    for model_id in probe.model_ids
                    if model_id.startswith("meterless/")
                ],
                "latency_ms": probe.latency_ms,
            }
            if probe.state is not RuntimeState.ONLINE:
                return self._failed(
                    NIGHTSHIFT,
                    f"nightshift probe state={probe.state.value}: {self._scrub(probe.detail)}",
                    provenance=provenance,
                )

            if include_chat:
                try:
                    chat = client.chat(
                        CHAT_LANE,
                        [ChatMessage(role="user", content=CHAT_PING)],
                        max_tokens=16,
                    )
                except NightshiftError as exc:
                    # Discovery succeeded but a real model call failed: the
                    # runtime is degraded, not down.
                    return SponsorHealthCheck.build(
                        NIGHTSHIFT,
                        HealthStatus.DEGRADED,
                        latency_ms=probe.latency_ms,
                        detail=f"model discovery ok but chat completion failed: {self._scrub(str(exc))}",
                        provenance=self._scrub_mapping(provenance),
                        last_success=self._registry.get(NIGHTSHIFT),
                    )
                receipt = chat.evidence.receipt
                provenance["chat"] = {
                    "lane": CHAT_LANE,
                    "call_id": chat.evidence.call_id,
                    "served_model": chat.evidence.served_model,
                    "receipt_id": receipt.receipt_id if receipt else None,
                    "latency_ms": chat.evidence.latency_ms,
                    "prompt_sha256": chat.evidence.prompt_sha256,
                }
        finally:
            client.close()

        last_success = self._registry.record(NIGHTSHIFT, provenance)
        return SponsorHealthCheck.build(
            NIGHTSHIFT,
            HealthStatus.VERIFIED,
            latency_ms=probe.latency_ms,
            detail="authenticated model discovery succeeded"
            + ("; live chat completion receipt captured" if include_chat else ""),
            provenance=self._scrub_mapping(provenance),
            last_success=last_success,
        )

    # ------------------------------------------------------------- H-MEM engine

    def check_engine(self) -> SponsorHealthCheck:
        provider = self._engine_factory()
        try:
            engine_health = provider.health()
        except MemoryUnavailableError as exc:
            return self._failed(METERLESS_ENGINE, f"engine sidecar unreachable: {exc}")
        except AgentMemoryError as exc:
            return SponsorHealthCheck.build(
                METERLESS_ENGINE,
                HealthStatus.DEGRADED,
                detail=f"engine sidecar answered incorrectly: {exc.kind}",
                last_success=self._registry.get(METERLESS_ENGINE),
            )
        finally:
            provider.close()

        provenance = {
            "sidecar_status": engine_health.status,
            "engine": engine_health.engine,
            "engine_version": engine_health.engine_version,
            "vendored_sha": engine_health.vendored_sha,
            "conformance": (
                {
                    "passed": engine_health.conformance.passed,
                    "total": engine_health.conformance.total,
                }
                if engine_health.conformance
                else None
            ),
            "projects": engine_health.projects,
        }
        if engine_health.status.lower() not in _OK_ENGINE_STATES:
            return SponsorHealthCheck.build(
                METERLESS_ENGINE,
                HealthStatus.DEGRADED,
                detail=f"sidecar reported non-ok status {engine_health.status!r}",
                provenance=provenance,
                last_success=self._registry.get(METERLESS_ENGINE),
            )
        last_success = self._registry.record(METERLESS_ENGINE, provenance)
        return SponsorHealthCheck.build(
            METERLESS_ENGINE,
            HealthStatus.VERIFIED,
            detail="engine sidecar healthy; vendored engine and conformance scorecard reported",
            provenance=provenance,
            last_success=last_success,
        )

    # ------------------------------------------------------------------ Cursor

    def check_cursor(self) -> SponsorHealthCheck:
        # Cursor is development tooling, not a runtime service (v2.0 contract
        # delta). Never report it as verified from a network probe.
        return SponsorHealthCheck.build(
            CURSOR,
            HealthStatus.NOT_CHECKED,
            detail="Cursor is build-time provenance, not a runtime service; record "
            "CURSOR_BUILD evidence in docs/evidence/ and the submission narrative (ENG-057)",
        )

    # --------------------------------------------------------------- internals

    def _not_checked(self, sponsor: str, detail: str) -> SponsorHealthCheck:
        return SponsorHealthCheck.build(
            sponsor,
            HealthStatus.NOT_CHECKED,
            detail=self._scrub(detail),
            last_success=self._registry.get(sponsor),
        )

    def _failed(
        self,
        sponsor: str,
        detail: str,
        *,
        provenance: dict | None = None,
    ) -> SponsorHealthCheck:
        return SponsorHealthCheck.build(
            sponsor,
            HealthStatus.UNAVAILABLE,
            detail=detail,
            provenance=self._scrub_mapping(provenance or {}),
            last_success=self._registry.get(sponsor),
        )

    def _overall(self, checks: list[SponsorHealthCheck]) -> HealthStatus:
        statuses = [
            check.status for check in checks if check.sponsor in RUNTIME_SPONSORS
        ]
        if all(status is HealthStatus.NOT_CHECKED for status in statuses):
            return HealthStatus.NOT_CHECKED
        if any(status is HealthStatus.UNAVAILABLE for status in statuses):
            return HealthStatus.UNAVAILABLE
        if any(status is HealthStatus.DEGRADED for status in statuses):
            return HealthStatus.DEGRADED
        if all(status is HealthStatus.VERIFIED for status in statuses):
            return HealthStatus.VERIFIED
        # Verified + not_checked mix: partially configured, honestly degraded.
        return HealthStatus.DEGRADED

    def _remember_secret(self, client: Any) -> None:
        """Collect configured bearer secrets so output can be scrubbed."""
        settings = getattr(client, "_settings", None)
        secret = None
        if settings is not None and getattr(settings, "api_key", None):
            secret = settings.api_key.get_secret_value()
        elif settings is not None and getattr(settings, "token", None):
            secret = settings.token.get_secret_value()
        if secret:
            self._secrets = tuple(s for s in (*self._secrets, secret) if s)

    def _scrub(self, text: str) -> str:
        cleaned = text
        for secret in self._secrets:
            cleaned = cleaned.replace(secret, "[REDACTED]")
        return cleaned

    def _scrub_mapping(self, data: Any) -> Any:
        if isinstance(data, str):
            return self._scrub(data)
        if isinstance(data, dict):
            return {key: self._scrub_mapping(value) for key, value in data.items()}
        if isinstance(data, list):
            return [self._scrub_mapping(value) for value in data]
        return data
