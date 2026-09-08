/**
 * AI Analyst Conversational Assistant API
 */
import { API_BASE_URL } from "./client";
import type {
  ChatResponse,
} from "./types";

export async function askAgent(question: string, conversationId?: string, periodA?: string, periodB?: string): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      question,
      conversation_id: conversationId,
      period_a: periodA,
      period_b: periodB,
    }),
  });

  if (!response.ok) {
    let errorMessage = "Failed to process question";
    try {
      const errorJson = await response.json();
      if (errorJson.detail) {
        errorMessage =
          typeof errorJson.detail === "string"
            ? errorJson.detail
            : JSON.stringify(errorJson.detail);
      }
    } catch {
      const errorText = await response.text();
      if (errorText) errorMessage = errorText;
    }
    throw new Error(errorMessage);
  }

  return response.json();
}
