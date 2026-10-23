"""M2 Zetaris module: governed query client and grounded evidence (ENG-022).

Wraps the Zetaris direct REST API (``/api/v1.0``) behind a strict,
read-only-by-default query surface. Every successful query returns data plus a
:class:`~app.modules.zetaris.evidence.QueryEvidence` record assembled in
:mod:`tool`, so agent decisions can cite exactly which governed fact they
used. Registration of the workspace read model into Zetaris (ENG-017) and the
sponsor health endpoint (ENG-042) build on this client but are not part of
this module yet.
"""
