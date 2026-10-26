import { readProjectService } from "@/lib/api/project-proxy";
export async function GET(request: Request) {
  const value = new URL(request.url).searchParams.get("offset") ?? "0";
  if (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)))
    return Response.json({ message: "Invalid project page." }, { status: 400 });
  return readProjectService(`/projects?offset=${value}&limit=100`, true);
}
