"""Typed failures of validation planning, with the HTTP status the API answers."""


class ValidationPlanError(Exception):
    kind = "validation_plan_error"
    status_code = 422


class ValidationPlanNotFoundError(ValidationPlanError):
    kind = "validation_plan_not_found"
    status_code = 404


class ValidationPlanConflictError(ValidationPlanError):
    """The inputs are not in a state a plan can be built on or approved from."""

    kind = "validation_plan_conflict"
    status_code = 409
