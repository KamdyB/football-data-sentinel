export async function processBatch(payload) {
    const response = await fetch("/api/process", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.error || "Pipeline request failed");
    }

    return data;
}

export async function refreshSentinel() {
  const response = await fetch("/api/refresh", {
    method: "POST",
  });

  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || "Sentinel refresh failed");
  }

  return data;
}