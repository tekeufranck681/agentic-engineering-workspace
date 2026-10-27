export class ApiError extends Error {
  status: number;
  uncertain: boolean;
  constructor(status: number, message: string, uncertain = false) {
    super(message);
    this.status = status;
    this.uncertain = uncertain;
  }
}
export async function apiRequest<T>(
  path: string,
  parse: (body: unknown) => T,
  options: { method?: "GET" | "POST"; body?: unknown } = {},
): Promise<T> {
  const mutation = options.method === "POST";
  try {
    const response = await fetch(`/api${path}`, {
      method: options.method ?? "GET",
      headers: { "Content-Type": "application/json" },
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: "no-store",
      signal: AbortSignal.timeout(12000),
    });
    const body: unknown = await response.json();
    if (!response.ok) {
      const error =
        typeof body === "object" && body !== null
          ? (body as Record<string, unknown>)
          : {};
      throw new ApiError(
        response.status,
        typeof error.message === "string"
          ? error.message
          : "The request could not be completed.",
        typeof error.uncertain === "boolean"
          ? error.uncertain
          : mutation && response.status >= 500,
      );
    }
    try {
      return parse(body);
    } catch {
      throw new ApiError(
        502,
        mutation
          ? "The save could not be confirmed. Refresh the saved records before trying again."
          : "The project service returned an unsupported response.",
        mutation,
      );
    }
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(
      0,
      mutation
        ? "The save could not be confirmed. Check saved records before trying again."
        : "Project service could not be reached. Try again.",
      mutation,
    );
  }
}
