"""ToolGateway: typed, scoped and recorded tool calls (ENG-020).

Every tool call from the agent goes through ``ToolGateway.call``:

1. the tool must be registered and allowed for the run (``ToolScope.allowed_tools``);
2. the run's call budget must not be exhausted;
3. the raw input is validated against the tool's Pydantic input model;
4. for tools that write, every target path must sit inside the task's
   ``target_paths`` (ENG-004 ``Task``), so the model cannot widen its own scope;
5. the handler runs, its output is validated against the output model;
6. one ``ToolCallRecord`` is written for every call, including rejected ones.

Model output never reaches a handler without passing steps 1-4. Tool failures
are returned as structured results (``status="error"``), not raised, so the
LangGraph loop can show them to the model. Records go to a ``ToolCallRecorder``;
the in-memory recorder here is replaced by M2's run-event persistence (ENG-027).
"""

import json
import posixpath
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel, Field, ValidationError

from app.domain.ids import ReadableId
from app.domain.task import Task

In = TypeVar("In", bound=BaseModel)
Out = TypeVar("Out", bound=BaseModel)

CallStatus = Literal["ok", "rejected", "error"]
MAX_RECORDED_CHARS = 4_000


class ToolScope(BaseModel):
    """What one run may do. Built from the run's Task; never from model output."""

    run_id: ReadableId
    task_id: ReadableId
    allowed_tools: frozenset[str]
    writable_paths: tuple[str, ...] = ()
    """Repo-relative files or directories (``src/``) the run may change."""
    max_calls: int = Field(default=50, ge=1, le=1000)

    @classmethod
    def for_task(cls, run_id: str, task: Task, allowed_tools: set[str], max_calls: int = 50) -> "ToolScope":
        return cls(
            run_id=run_id,
            task_id=task.id,
            allowed_tools=frozenset(allowed_tools),
            writable_paths=tuple(task.target_paths),
            max_calls=max_calls,
        )

    def allows_write(self, path: str) -> bool:
        target = posixpath.normpath(path)
        for allowed in self.writable_paths:
            if allowed.endswith("/"):
                if target.startswith(posixpath.normpath(allowed) + "/"):
                    return True
            elif target == posixpath.normpath(allowed):
                return True
        return False


class ToolContext:
    """Dependencies a handler may use, plus the scope it runs under."""

    def __init__(self, scope: ToolScope, **deps: Any):
        self.scope = scope
        self._deps = deps

    def dep(self, name: str) -> Any:
        if self._deps.get(name) is None:
            raise ToolUnavailableError(f"{name} is not available in this run")
        return self._deps[name]


class ToolUnavailableError(Exception):
    """A dependency the tool needs is not configured for this run."""


class ToolSpec(BaseModel, Generic[In, Out]):
    model_config = {"arbitrary_types_allowed": True}

    name: str
    description: str
    input_model: type[In]
    output_model: type[Out]
    handler: Callable[[ToolContext, In], Out]
    writes: bool = False
    write_paths: Callable[[In], list[str]] | None = None
    """For write tools: which repo paths this input would change."""

    def schema_for_model(self) -> dict[str, Any]:
        """Function-calling description handed to the model (M3 ModelGateway)."""
        return {"name": self.name, "description": self.description, "parameters": self.input_model.model_json_schema()}


class ToolCallRecord(BaseModel):
    call_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    run_id: str
    task_id: str
    tool: str
    status: CallStatus
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime
    duration_ms: int


class ToolCallResult(BaseModel):
    """What the orchestrator (and the model) sees."""

    call_id: uuid.UUID
    tool: str
    status: CallStatus
    output: dict[str, Any] | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class ToolCallRecorder(Protocol):
    def record(self, record: ToolCallRecord) -> None: ...

    def count(self, run_id: str) -> int: ...


class InMemoryRecorder:
    def __init__(self) -> None:
        self.records: list[ToolCallRecord] = []

    def record(self, record: ToolCallRecord) -> None:
        self.records.append(record)

    def count(self, run_id: str) -> int:
        return sum(1 for r in self.records if r.run_id == run_id)


def _bounded(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """Keep stored records small: oversized payloads are replaced by a preview."""
    if data is None:
        return None
    text = json.dumps(data, default=str)
    if len(text) <= MAX_RECORDED_CHARS:
        return json.loads(text)
    return {"_truncated": True, "_chars": len(text), "_preview": text[:MAX_RECORDED_CHARS]}


class ToolGateway:
    def __init__(self, recorder: ToolCallRecorder | None = None):
        self._tools: dict[str, ToolSpec] = {}
        self.recorder = recorder or InMemoryRecorder()

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool {spec.name!r} is already registered")
        if spec.writes and spec.write_paths is None:
            raise ValueError(f"write tool {spec.name!r} must declare write_paths")
        self._tools[spec.name] = spec

    def tool_names(self) -> list[str]:
        return sorted(self._tools)

    def schemas_for(self, scope: ToolScope) -> list[dict[str, Any]]:
        """Only the tools this run may call are shown to the model."""
        return [self._tools[n].schema_for_model() for n in sorted(scope.allowed_tools) if n in self._tools]

    def call(self, ctx: ToolContext, name: str, raw_input: dict[str, Any]) -> ToolCallResult:
        scope = ctx.scope
        started_at = datetime.now(timezone.utc)
        clock = time.monotonic()

        def finish(status: CallStatus, *, output: dict | None = None, error: str | None = None,
                   recorded_input: dict | None = None) -> ToolCallResult:
            if recorded_input is None and isinstance(raw_input, dict):
                recorded_input = raw_input
            record = ToolCallRecord(
                run_id=scope.run_id, task_id=scope.task_id, tool=name, status=status,
                input=_bounded(recorded_input),
                output=_bounded(output), error=error, started_at=started_at,
                duration_ms=int((time.monotonic() - clock) * 1000),
            )
            self.recorder.record(record)
            return ToolCallResult(call_id=record.call_id, tool=name, status=status, output=output, error=error)

        spec = self._tools.get(name)
        if spec is None:
            return finish("rejected", error=f"unknown tool {name!r}")
        if name not in scope.allowed_tools:
            return finish("rejected", error=f"tool {name!r} is not allowed for {scope.run_id}")
        if self.recorder.count(scope.run_id) >= scope.max_calls:
            return finish("rejected", error=f"call budget of {scope.max_calls} exhausted for {scope.run_id}")
        try:
            data = spec.input_model.model_validate(raw_input)
        except ValidationError as exc:
            return finish("rejected", error=f"invalid input: {exc.errors(include_url=False, include_input=False)}")
        if spec.writes:
            assert spec.write_paths is not None
            outside = [p for p in spec.write_paths(data) if not scope.allows_write(p)]
            if outside:
                return finish("rejected", error=f"paths outside the task scope: {outside}",
                              recorded_input=data.model_dump(mode="json"))
        try:
            result = spec.handler(ctx, data)
            output = spec.output_model.model_validate(result).model_dump(mode="json")
        except ToolUnavailableError as exc:
            return finish("error", error=str(exc), recorded_input=data.model_dump(mode="json"))
        except ValidationError as exc:
            return finish("error", error=f"tool returned invalid output: {exc.error_count()} error(s)",
                          recorded_input=data.model_dump(mode="json"))
        except Exception as exc:  # typed adapter errors carry no secrets
            return finish("error", error=f"{type(exc).__name__}: {str(exc)[:300]}",
                          recorded_input=data.model_dump(mode="json"))
        return finish("ok", output=output, recorded_input=data.model_dump(mode="json"))
