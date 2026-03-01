import { NextResponse } from "next/server";

/**
 * BFF health check — proxies to backend.
 */
export async function GET() {
  const backendUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  try {
    const res = await fetch(`${backendUrl}/health`);
    const data = await res.json();
    return NextResponse.json({ frontend: "ok", backend: data.status });
  } catch {
    return NextResponse.json(
      { frontend: "ok", backend: "unreachable" },
      { status: 502 },
    );
  }
}
