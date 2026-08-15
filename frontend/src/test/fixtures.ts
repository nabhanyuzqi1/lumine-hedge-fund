// Copyright (c) 2026 Lumine. All rights reserved.
/**
 * Test utilities for API integration testing.
 */

export function createMockResponse<T>(data: T, status: number = 200): Response {
  return new Response(JSON.stringify({ data }), { status });
}

export function createErrorResponse(message: string, status: number = 400): Response {
  return new Response(JSON.stringify({ detail: message }), { status });
}

export function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function generateUuid(): string {
  return `${Math.random().toString(36).substring(2, 15)}-${Math.random().toString(36).substring(2, 15)}`;
}
