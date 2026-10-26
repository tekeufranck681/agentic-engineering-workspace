"""M3 ModelGateway (ENG-008): the one way the product calls AI models.

Capabilities ask the gateway for text or for a validated pydantic model and
name their capability; configuration routes each capability to a Nightshift
lane or a pinned model id. Nightshift is the primary and only provider (v2.0
POWER requirement), every call leaves a redacted receipt, and failures are
typed instead of silently falling back. ``api`` wires it into FastAPI;
``CapabilityModel`` is the LLMPort that M4's services receive.
"""
