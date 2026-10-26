import { isProjectId } from "@/lib/api/project-contract";
import { readProjectService } from "@/lib/api/project-proxy";
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ projectId: string }> },
) {
  const { projectId } = await params;
  if (!isProjectId(projectId))
    return Response.json(
      { message: "This project link is invalid. Choose another project." },
      { status: 400 },
    );
  return readProjectService(`/projects/${projectId}`);
}
