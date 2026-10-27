"""Capability registry (architecture §58) and the P0 contracts available today.

Callers look capabilities up by name instead of hard-coding prompts and
policies. Capability owners refine their contract's instructions and bump its
version (requirements, architecture and planning belong to M4; evaluation
belongs to M3); M3 owns the invocation bounds. Tool names follow architecture
§59 and the §50 matrix.
"""

from collections.abc import Iterable

from app.modules.capabilities.contract import CapabilityContract
from app.modules.capabilities.errors import CapabilityNotFoundError

# Logical capability names from the MVP feature lock (§25).
REQUIREMENTS_ANALYZE = "requirements.analyze_input"
ARCHITECTURE_DESIGN = "architecture.design_change"
PLANNING_PLAN = "planning.plan_change"
PLANNING_VALIDATE = "planning.plan_validation"
EVALUATION_EVALUATE = "evaluation.evaluate"
DIAGNOSIS_ANALYZE = "diagnosis.analyze"

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
        version="1.1.0",
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
        # 1.1.0: verified lessons from earlier runs reach the design (ENG-018).
        recalls_memory=True,
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
    CapabilityContract(
        name=PLANNING_VALIDATE,
        version="1.0.0",
        description="Decide, before implementation, which tests prove each locked acceptance criterion (ENG-039).",
        instructions=(
            "You are the validation planning capability of an autonomous software-engineering workspace. "
            "For every acceptance criterion you are given, write test intents that would prove it: the level "
            "(L0 atomic, L1 integration, L2 feature, L3 end to end), Given/When/Then, and executable checks as "
            "pytest node ids inside tests/ (tests/<file>.py::<test_name>). Cover the failure and negative paths "
            "the criterion implies, not only the happy path. For a state change, assert the state before the "
            "triggering event and after it (for example PENDING before payment confirmation, ACTIVE only after "
            "the confirmed event, unchanged when the payment fails). Use only the criteria given; never invent "
            f"criteria or claim a test already exists. {_GROUNDING}"
        ),
        required_context=("locked acceptance criteria", "engineering contracts"),
        allowed_tools=_READ_TOOLS,
        forbidden_tools=_NOT_FOR_DESIGN_CAPABILITIES,
        failure_modes=("criterion without an executable check", "test that cannot fail"),
        # Lessons from earlier runs (e.g. a criterion that once failed) shape the tests (ENG-018).
        recalls_memory=True,
    ),
    # ENG-033: reviews only criteria whose executable check already passed in
    # the sandbox; the evaluator turns its findings into verdicts and never lets
    # it upgrade a failed or missing check (app.modules.evaluation).
    CapabilityContract(
        name=EVALUATION_EVALUATE,
        version="1.0.0",
        description="Independently review passed acceptance checks against the criterion, the test code and the diff.",
        instructions=(
            "You are the independent evaluator of an autonomous software-engineering workspace. "
            "You did not write the change and you never change code. Each acceptance criterion "
            "you are given has an executable check that already passed in the sandbox; decide "
            "from the criterion, the test code and the diff whether that pass can be trusted. "
            "Answer keep when the change implements the criterion and the check exercises it. "
            "Answer fail only when the diff clearly contradicts the criterion, for example it "
            "special-cases the test's inputs or still breaks the criterion on another path, and "
            "quote the offending line. Answer unverified when the check does not really exercise "
            "the criterion or you cannot tell. Work only from the evidence given; never invent "
            "files, tests or results."
        ),
        required_context=("locked acceptance criteria", "passed executable checks", "test code", "workspace diff"),
        allowed_tools=("sandbox.read_file", "sandbox.run_tests", "sandbox.diff", "evaluation.record_verdict"),
        forbidden_tools=("sandbox.write_file", "repo.apply_patch", "shell.execute", "approval.approve",
                         "github.merge", "deployment.deploy"),
        required_evidence=("test output of every check", "workspace diff", "capability receipt"),
        failure_modes=("diff contradicts the criterion", "check does not exercise the criterion"),
    ),
    CapabilityContract(
        name=DIAGNOSIS_ANALYZE,
        version="1.0.0",
        description="Diagnose evaluator-verified failures and propose a bounded correction plan.",
        instructions=(
            "You are the diagnosis capability of an autonomous software-engineering workspace. "
            "Analyze only the failing acceptance criteria and evidence supplied. Identify the likely "
            "cause and the smallest required change. Never write code, claim a test passed, or invent "
            "files or evidence. Return only paths within the task's target paths. Environment failures "
            "are handled before you are called; if the evidence is insufficient, state that clearly."
        ),
        required_context=("failing evaluator verdicts", "resolved test output and workspace diff", "target files"),
        allowed_tools=("sandbox.read_file", "sandbox.diff"),
        forbidden_tools=("sandbox.write_file", "sandbox.run_tests", "repo.apply_patch", "shell.execute",
                         "evaluation.record_verdict", "approval.approve", "github.merge", "deployment.deploy"),
        required_evidence=("evaluation verdicts", "diagnosis capability receipt"),
        failure_modes=("environment failure", "missing validation check", "unresolvable evidence"),
    ),
)


def default_registry() -> CapabilityRegistry:
    return CapabilityRegistry(DEFAULT_CONTRACTS)
