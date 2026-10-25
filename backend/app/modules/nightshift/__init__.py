"""M3 Nightshift module: client for the Meterless Runtime that Nightshift serves.

Nightshift is the product's primary AI runtime (v2.0 POWER requirement). It
exposes one OpenAI-compatible base URL; this module wraps it with the headers,
status classification and typed failures from the official Meterless provider
guide, and records a redacted evidence record for every call. The runtime
smoke check (ENG-003) builds on it; ModelGateway (ENG-008) will sit on top.
"""
