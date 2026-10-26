"""M3 capability runtime (ENG-028): validated, bounded, observable capability calls.

A capability (requirements analysis, architecture design, planning, later
evaluation and diagnosis) is declared once as a versioned CapabilityContract in
the registry and invoked through CapabilityRuntime, which sits on the
ModelGateway. Services that build their own prompts get the same guarantees
through CapabilityPort, an LLMPort.
"""
