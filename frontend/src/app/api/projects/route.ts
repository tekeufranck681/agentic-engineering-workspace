import { parseProjectCreate, parseProject } from "@/lib/api/project-contract";
import {
  requestProjectService,
  readProjectService,
} from "@/lib/api/project-proxy";
export async function GET(request: Request) {
  const value = new URL(request.url).searchParams.get("offset") ?? "0";
  if (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)))
    return Response.json({ message: "Invalid project page." }, { status: 400 });
  return readProjectService(`/projects?offset=${value}&limit=100`, true);
}

export async function POST(request: Request) {
  let input;
  try {
    input = parseProjectCreate(await request.json());
  } catch (error) {
    return Response.json(
      {
        message:
          error instanceof Error ? error.message : "Invalid project details.",
        uncertain: false,
      },
      { status: 400 },
    );
  }
  return requestProjectService("/projects", parseProject, {
    method: "POST",
    body: input,
  });
}
