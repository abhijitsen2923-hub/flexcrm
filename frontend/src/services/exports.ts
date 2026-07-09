import { apiClient } from "./http";


// Download a CSV through apiClient (adds the auth header + backend base URL) as
// a blob and trigger a save. A plain window.open/location on a relative
// "/api/v1/..." path would hit the frontend SPA (404) and can't send auth.
async function downloadCsv(path: string, fallbackName: string): Promise<void> {
  const res = await apiClient.get(path, { responseType: "blob" });
  const url = window.URL.createObjectURL(res.data as Blob);
  const link = document.createElement("a");
  link.href = url;
  // Honour the server's Content-Disposition filename when present.
  const disposition = res.headers?.["content-disposition"] as string | undefined;
  const match = disposition?.match(/filename="?([^";]+)"?/);
  link.download = match?.[1] ?? fallbackName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export const exportsService = {
  leads: () => downloadCsv("/exports/leads.csv", "leads.csv"),
  customers: () => downloadCsv("/exports/customers.csv", "customers.csv"),
  salesOrders: () => downloadCsv("/exports/sales-orders.csv", "sales-orders.csv"),
  inventory: () => downloadCsv("/exports/inventory.csv", "inventory.csv"),
  bookings: () => downloadCsv("/exports/bookings.csv", "bookings.csv"),
};
