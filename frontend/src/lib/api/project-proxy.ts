import "server-only";
import { parseProject, parseProjects } from "./project-contract";

export async function readProjectService(
  path: string,
  list = false,
): Promise<Response> {
  const base = process.env.BACKEND_API_URL;
  const headers = { "Cache-Control": "no-store" };
  if (!base)
    return Response.json(
      {
        message:
          "Project service is unavailable. Try again or contact the workspace operator.",
      },
      { status: 503, headers },
    );
  try {
    const url = new URL(base.replace(/\/$/, "") + path);
    if (
      !["http:", "https:"].includes(url.protocol) ||
      url.username ||
      url.password
    )
      throw new Error("Invalid backend configuration");
    const response = await fetch(url, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
      redirect: "error",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      return Response.json(
        {
          message:
            response.status === 404
              ? "This project could not be found. Choose another project."
              : "Project service could not load the requested data. Try again.",
        },
        { status: response.status === 404 ? 404 : 502, headers },
      );
    }
    let data;
    try {
      const raw: unknown = await response.json();
      data = list ? parseProjects(raw) : parseProject(raw);
    } catch {
      return Response.json(
        {
          message:
            "Project service returned an unsupported response. Contact the workspace operator.",
        },
        { status: 502, headers },
      );
    }
    return Response.json(data, { headers });
  } catch (error) {
    return Response.json(
      { message: "Project service could not be reached. Try again." },
      {
        status:
          error instanceof Error && error.name === "TimeoutError" ? 504 : 503,
        headers,
      },
    );
  }
}
