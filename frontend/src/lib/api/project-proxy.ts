import "server-only";
import { parseProject, parseProjects } from "./project-contract";

export async function requestProjectService<T>(
  path: string,
  parse: (value: unknown) => T,
  options: {
    method?: "GET" | "POST";
    body?: unknown;
    emptyBinding?: boolean;
  } = {},
): Promise<Response> {
  const base = process.env.BACKEND_API_URL;
  const headers = { "Cache-Control": "no-store" };
  const mutation = options.method === "POST";
  const fail = (message: string, status: number, uncertain = false) =>
    Response.json({ message, uncertain }, { status, headers });
  if (!base)
    return fail(
      "Project service is unavailable. Try again or contact the workspace operator.",
      503,
    );
  try {
    const url = new URL(base.replace(/\/$/, "") + path);
    if (
      !["http:", "https:"].includes(url.protocol) ||
      url.username ||
      url.password
    )
      return fail(
        "Project service is unavailable. Contact the workspace operator.",
        503,
      );
    const response = await fetch(url, {
      method: options.method ?? "GET",
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
      redirect: "error",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
    });
    if (!response.ok) {
      if (response.status === 404 && options.emptyBinding) {
        const body: unknown = await response.json();
        if (
          typeof body === "object" &&
          body !== null &&
          "detail" in body &&
          body.detail === "no active repository binding"
        )
          return Response.json(null, { headers });
      }
      if (response.status === 409)
        return fail(
          "A project with this name already exists. Choose a different name or open the existing project.",
          409,
        );
      if (response.status === 422)
        return fail(
          "Some project or repository details were rejected. Check the fields and try again.",
          422,
        );
      if (response.status === 404)
        return fail(
          "This project could not be found. Choose another project.",
          404,
        );
      return fail(
        mutation
          ? "The save could not be confirmed. Refresh saved records before trying again."
          : "Project service could not load the requested data. Try again.",
        502,
        mutation,
      );
    }
    try {
      return Response.json(parse(await response.json()), {
        headers,
        status: response.status,
      });
    } catch {
      return fail(
        mutation
          ? "The save could not be confirmed. Refresh saved records before trying again."
          : "Project service returned an unsupported response. Contact the workspace operator.",
        502,
        mutation,
      );
    }
  } catch (error) {
    return fail(
      mutation
        ? "The save could not be confirmed. Check saved records before trying again."
        : "Project service could not be reached. Try again.",
      error instanceof Error && error.name === "TimeoutError" ? 504 : 503,
      mutation,
    );
  }
}
export function readProjectService(path: string, list = false) {
  return list
    ? requestProjectService(path, parseProjects)
    : requestProjectService(path, parseProject);
}
