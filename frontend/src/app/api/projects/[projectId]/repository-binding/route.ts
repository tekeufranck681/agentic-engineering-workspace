import {
  isProjectId,
  parseBinding,
  parseBindingCreate,
} from "@/lib/api/project-contract";
import { requestProjectService } from "@/lib/api/project-proxy";
type Context = { params: Promise<{ projectId: string }> };
export async function GET(_request: Request, { params }: Context) {
  const { projectId } = await params;
  if (!isProjectId(projectId))
    return Response.json({ message: "Invalid project link." }, { status: 400 });
  return requestProjectService(
    `/projects/${projectId}/repository-binding`,
    parseBinding,
    { emptyBinding: true },
  );
}
export async function POST(request: Request, { params }: Context) {
  const { projectId } = await params;
  if (!isProjectId(projectId))
    return Response.json(
      { message: "Invalid project link.", uncertain: false },
      { status: 400 },
    );
  let input;
  try {
    input = parseBindingCreate(await request.json());
  } catch (error) {
    return Response.json(
      {
        message:
          error instanceof Error
            ? error.message
            : "Invalid repository details.",
        uncertain: false,
      },
      { status: 400 },
    );
  }
  return requestProjectService(
    `/projects/${projectId}/repository-binding`,
    parseBinding,
    { method: "POST", body: input },
  );
}
