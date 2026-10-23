"""M2 persistence module: projects and repository bindings (ENG-012).

Owns the transactional storage for workspace projects and the binding of a
project to the external git repository the autonomous agent is allowed to
inspect. Writes go through :mod:`repository`; HTTP exposure lives in
:mod:`router`.
"""
