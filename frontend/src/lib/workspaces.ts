export const workspaces = [
  {
    slug: "overview",
    label: "Overview",
    description:
      "Project context, repository connection and the next engineering action.",
    task: "ENG-011",
  },
  {
    slug: "requirements",
    label: "Requirements",
    description:
      "Review acceptance criteria and lock requirements before design begins.",
    task: "ENG-016",
  },
  {
    slug: "architecture",
    label: "Architecture",
    description:
      "Inspect architecture proposals, decisions and engineering contracts.",
    task: "ENG-021",
  },
  {
    slug: "planning",
    label: "Planning",
    description:
      "Inspect task dependencies, validation requirements and code readiness.",
    task: "ENG-026",
  },
  {
    slug: "runs",
    label: "Agent Runs",
    description:
      "Follow bounded execution, evaluation, diagnosis and correction.",
    task: "ENG-031",
  },
  {
    slug: "delivery",
    label: "Delivery",
    description:
      "Review changes, acceptance evidence and the resulting GitHub pull request.",
    task: "ENG-036",
  },
] as const;
