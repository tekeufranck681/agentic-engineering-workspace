"""Capability registry (architecture §58) and the P0 contracts available today.

Callers look capabilities up by name instead of hard-coding prompts and
policies. Capability owners refine their contract's instructions and bump its
version (requirements, architecture and planning belong to M4); M3 owns the
invocation bounds. Tool names follow architecture §59 and the §50 matrix.
"""

from collections.abc import Iterable

from app.modules.capabilities.contract import CapabilityContract
from app.modules.capabilities.errors import CapabilityNotFoundError

# Logical capability names from the MVP feature lock (§25).
REQUIREMENTS_ANALYZE = "requirements.analyze_input"
ARCHITECTURE_DESIGN = "architecture.design_change"
PLANNING_PLAN = "planning.plan_change"

_GROUNDING = (
    "Work only from the request and the context given. Never invent facts, files, "
    "results or approvals; where the output has room for assumptions or open "
    "questions, put anything uncertain there."
)
_READ_TOOLS = ("project.read", "repo.search", "repo.read")
_NOT_FOR_DESIGN_CAPABILITIES = (
    "repo.apply_patch",
    "shell.execute",
    "evaluation.record_verdict",
    "approval.approve",
    "github.merge",
    "deployment.deploy",
)


class CapabilityRegistry:
    """Contracts by name."""

    def __init__(self, contracts: Iterable[CapabilityContract] = ()) -> None:
        self._contracts: dict[str, CapabilityContract] = {}
        for contract in contracts:
            self.register(contract)

    def register(self, contract: CapabilityContract, *, replace: bool = False) -> None:
        existing = self._contracts.get(contract.name)
        if existing is not None and existing != contract and not replace:
            raise ValueError(
                f"capability {contract.name} is already registered as v{existing.version}; "
                "pass replace=True to swap it"
            )
        self._contracts[contract.name] = contract

    def get(self, name: str) -> CapabilityContract:
        try:
            return self._contracts[name]
        except KeyError:
            raise CapabilityNotFoundError(f"no capability named {name!r}", capability=name) from None

    def names(self) -> list[str]:
        return sorted(self._contracts)

    def allowed_tools(self, name: str) -> tuple[str, ...]:
        return self.get(name).allowed_tools


DEFAULT_CONTRACTS = (
    CapabilityContract(
        name=REQUIREMENTS_ANALYZE,
        version="1.0.0",
        description="Turn an engineering request into requirements, user stories and acceptance criteria.",
        instructions=(
            "You are the requirements capability of an autonomous software-engineering "
            f"workspace. {_GROUNDING} Acceptance criteria must be observable and testable."
        ),
        required_context=("engineering request or project brief",),
        allowed_tools=_READ_TOOLS,
        forbidden_tools=("requirements.approve", *_NOT_FOR_DESIGN_CAPABILITIES),
        failure_modes=("ambiguous request", "conflicting requirements"),
    ),
    CapabilityContract(
        name=ARCHITECTURE_DESIGN,
        version="1.0.0",
        description="Propose the architecture change, ADR and engineering contract for locked requirements.",
        instructions=(
            "You are the architecture capability of an autonomous software-engineering "
            "workspace. Design changes that satisfy the locked requirements and respect "
            f"the existing ADRs and contracts. {_GROUNDING}"
        ),
        required_context=("locked requirements set", "existing ADRs and contracts"),
        allowed_tools=(*_READ_TOOLS, "engineering_data.query"),
        forbidden_tools=_NOT_FOR_DESIGN_CAPABILITIES,
        failure_modes=("requirement not locked", "conflicting ADR"),
    ),
    CapabilityContract(
        name=PLANNING_PLAN,
        version="1.0.0",
        description="Break an approved change into atomic, dependency-ordered tasks traced to acceptance criteria.",
        instructions=(
            "You are the planning capability of an autonomous software-engineering "
            "workspace. Produce atomic, dependency-ordered tasks, each traced to the "
            f"acceptance criteria it serves. Never mark work as done. {_GROUNDING}"
        ),
        required_context=("approved architecture", "locked acceptance criteria"),
        allowed_tools=(*_READ_TOOLS, "engineering_data.query"),
        forbidden_tools=_NOT_FOR_DESIGN_CAPABILITIES,
        failure_modes=("untraceable task", "dependency cycle"),
    ),
)


def default_registry() -> CapabilityRegistry:
    return CapabilityRegistry(DEFAULT_CONTRACTS)
