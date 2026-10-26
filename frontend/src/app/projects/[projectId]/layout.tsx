import { AppShell } from "@/components/layout/app-shell";
export default async function ProjectLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <AppShell projectId={projectId}>{children}</AppShell>;
}
