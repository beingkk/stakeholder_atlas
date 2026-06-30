const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function fetchHealth(): Promise<{ status: string; version: string }> {
  const response = await fetch(`${apiUrl}/health`);
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }
  return response.json();
}

export async function fetchApiStatus(): Promise<{ status: string }> {
  const response = await fetch(`${apiUrl}/api/v1/status`);
  if (!response.ok) {
    throw new Error(`API status check failed: ${response.status}`);
  }
  return response.json();
}
