"""M5 ToolGateway (ENG-020): the only way the agent calls tools.

``gateway`` holds the typed, scoped, recorded call path; ``builtin`` registers
the first tools (repo reads through the GitHub adapter, M2's zetaris.run_sql).
Sandbox file, test and diff tools arrive with ENG-025.
"""
