"""Declarative ENG-017 read-model spec and execution-plan building.

Pure data and pure functions: nothing here touches the network, so every
plan can be unit-tested and reviewed before any statement reaches Zetaris.

The read model publishes the engineering state Zetaris may serve to agents

* over the product PostgreSQL through a JDBC datasource (validated route
  from the 2026-10-23 spike),
* with tables registered explicitly by name (introspection proved shallow),
* behind datasource views exposing a demo-safe column subset only.
"""

from dataclasses import dataclass, field

PASSWORD_PLACEHOLDER = "{password}"

DATASOURCE_NAME = "aew_pg"
DATASOURCE_DESCRIPTION = "AEW product PostgreSQL - engineering read model"
"""DESCRIBE BY allows letters, digits, spaces and `_ . - ,` only. Do not add
parentheses, slashes or colons (rejected at validation time on Zetaris)."""

JDBC_DRIVER = "org.postgresql.Driver"
FETCHSIZE = "1000"


@dataclass(frozen=True)
class TableSpec:
    """One published PostgreSQL table and its governed view."""

    name: str
    view_name: str
    view_columns: tuple[str, ...]


TABLES: tuple[TableSpec, ...] = (
    TableSpec(
        name="projects",
        view_name="aew_projects",
        view_columns=("id", "name", "description", "status", "created_at", "updated_at"),
    ),
    TableSpec(
        name="repository_bindings",
        view_name="aew_repository_bindings",
        view_columns=(
            "id", "project_id", "provider", "owner", "name", "full_name",
            "default_branch", "base_sha", "status", "bound_at",
        ),
    ),
)


@dataclass(frozen=True)
class JdbcTarget:
    """Where the product PostgreSQL lives, as seen from Zetaris containers."""

    host: str
    port: int
    database: str
    user: str


@dataclass(frozen=True)
class CurrentState:
    """What Zetaris currently knows about our datasource."""

    datasource_exists: bool
    registered_objects: frozenset[str] = field(default_factory=frozenset)
    """Names of tables and views already registered under the datasource.
    Parsed from the first SHOW DATASOURCE TABLES column."""


@dataclass(frozen=True)
class PlanStatement:
    """One statement to run, keeping the secret out of any display output."""

    action: str
    sql_template: str

    def rendered(self, password: str) -> str:
        return self.sql_template.replace(PASSWORD_PLACEHOLDER, password)

    def display(self) -> str:
        return self.sql_template.replace(PASSWORD_PLACEHOLDER, "<redacted>")


def create_datasource_template(target: JdbcTarget) -> str:
    return (
        f'CREATE DATASOURCE {DATASOURCE_NAME} DESCRIBE BY "{DATASOURCE_DESCRIPTION}" '
        f'OPTIONS (jdbcdriver "{JDBC_DRIVER}", '
        f'jdbcurl "jdbc:postgresql://{target.host}:{target.port}/{target.database}", '
        f'username "{target.user}", password "{PASSWORD_PLACEHOLDER}", '
        f'fetchsize "{FETCHSIZE}")'
    )


def register_table_template(table: str) -> str:
    return f"REGISTER DATASOURCE TABLE '{table}' FROM {DATASOURCE_NAME}"


def create_view_template(view: str, table: str, columns: tuple[str, ...]) -> str:
    column_list = ", ".join(columns)
    return (
        f"CREATE DATASOURCE VIEW {view} FROM {DATASOURCE_NAME} "
        f"AS SELECT {column_list} FROM {table}"
    )


def build_plan(target: JdbcTarget, current: CurrentState) -> list[PlanStatement]:
    """Diff desired read model vs live Zetaris state, in execution order.

    Idempotent: a complete current state produces an empty plan. The
    datasource creation must precede any registration; views come last.
    """
    plan: list[PlanStatement] = []

    if not current.datasource_exists:
        plan.append(
            PlanStatement("create datasource aew_pg", create_datasource_template(target))
        )

    for table in TABLES:
        if table.name not in current.registered_objects:
            plan.append(
                PlanStatement(f"register table {table.name}", register_table_template(table.name))
            )

    for table in TABLES:
        if table.view_name not in current.registered_objects:
            plan.append(
                PlanStatement(
                    f"create governed view {table.view_name}",
                    create_view_template(table.view_name, table.name, table.view_columns),
                )
            )

    return plan
