import { apiRequest } from "@/lib/api/client";
import { parseDeliveries, parseRuns } from "@/lib/api/delivery-contract";
export const deliveryService = {
    deliveries: (projectId: string) => apiRequest(`/delivery/traceability?project_id=${encodeURIComponent(projectId)}`, parseDeliveries),
    runs: (projectId: string) => apiRequest(`/delivery/runs?project_id=${encodeURIComponent(projectId)}`, parseRuns),
};
