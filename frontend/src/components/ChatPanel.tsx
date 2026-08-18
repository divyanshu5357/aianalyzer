"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  Bot,
  Send,
  Sparkles,
  User,
  Loader2,
  Database,
  UploadCloud,
} from "lucide-react";
import { askAgent, ChatResponse } from "../lib/api";
import { AnalyticsRenderer } from "./AnalyticsRenderer";
import { useApp } from "../context/AppContext";

interface MessageItem {
  id: string;
  sender: "user" | "assistant";
  text: string;
  data?: ChatResponse;
  timestamp: string;
  isEmptyDatasetState?: boolean;
}

interface ChatPanelProps {
  onNavigateToUpload?: () => void;
  activeDatasetName?: string | null;
  initialQuestion?: string;
  onClearInitialQuestion?: () => void;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({
  onNavigateToUpload,
  activeDatasetName,
  initialQuestion,
  onClearInitialQuestion,
}) => {
  const { seededPeriodA, seededPeriodB } = useApp();
  const [inputQuestion, setInputQuestion] = useState("");

  useEffect(() => {
    if (initialQuestion) {
      setTimeout(() => {
        setInputQuestion(initialQuestion);
        if (onClearInitialQuestion) {
          onClearInitialQuestion();
        }
      }, 0);
    }
  }, [initialQuestion, onClearInitialQuestion]);
  const [activeConversationId, setActiveConversationId] = useState<string | undefined>();
  const [messages, setMessages] = useState<MessageItem[]>([
    {
      id: "welcome-1",
      sender: "assistant",
      text: "Hello! I am your AI Analyst. Ask me anything about your admission funnel, conversion rates, channel performance, or yearly trends.",
      timestamp: "12:00 PM",
      data: {
        question: "",
        answer: "",
        recommendations: [
          { label: "How many admissions happened in 2026?", question: "How many admissions happened in 2026?" },
          { label: "Show leads by state", question: "Show leads by state" },
          { label: "Compare Direct vs Website leads", question: "Compare Direct and Website leads" },
          { label: "Which program generated the most leads?", question: "Which program generated the most leads?" },
        ]
      }
    },
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const msgCounter = useRef(1);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const handleSend = async (questionText?: string) => {
    const query = (questionText || inputQuestion).trim();
    if (!query || isLoading) return;

    msgCounter.current += 1;
    const userMsgId = `user-${msgCounter.current}`;

    const userMsg: MessageItem = {
      id: userMsgId,
      sender: "user",
      text: query,
      timestamp: "Just now",
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!questionText) setInputQuestion("");
    setIsLoading(true);

    try {
      const response = await askAgent(query, activeConversationId, seededPeriodA || undefined, seededPeriodB || undefined);
      if (response.conversation_id) {
        setActiveConversationId(response.conversation_id);
      }
      msgCounter.current += 1;
      const botMsgId = `bot-${msgCounter.current}`;

      const textAnswer = response.answer || "I received your question.";
      const isEmptyState =
        textAnswer.toLowerCase().includes("please upload a dataset") ||
        textAnswer.toLowerCase().includes("no dataset");

      const botMsg: MessageItem = {
        id: botMsgId,
        sender: "assistant",
        text: textAnswer,
        data: response,
        timestamp: "Just now",
        isEmptyDatasetState: isEmptyState,
      };
      setMessages((prev) => [...prev, botMsg]);
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "Failed to fetch response.";

      const isEmptyState =
        errorMessage.toLowerCase().includes("please upload a dataset") ||
        errorMessage.toLowerCase().includes("no dataset");

      msgCounter.current += 1;
      const errMsgId = `bot-err-${msgCounter.current}`;

      setMessages((prev) => [
        ...prev,
        {
          id: errMsgId,
          sender: "assistant",
          text: isEmptyState
            ? "Please upload a dataset before asking analytical questions."
            : `⚠️ Error: ${errorMessage}`,
          timestamp: "Just now",
          isEmptyDatasetState: isEmptyState,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs flex flex-col h-[650px]">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-100 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 text-white flex items-center justify-center shadow-md shadow-blue-500/20">
            <Bot className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-extrabold text-slate-900 tracking-tight">
                AI Analyst Assistant
              </h2>
              <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-blue-50 text-blue-600 border border-blue-100">
                ACTIVE SCHEMA ENGINE
              </span>
            </div>
            <p className="text-xs text-slate-500">
              {activeDatasetName
                ? `Context: Active dataset (${activeDatasetName})`
                : "Instant natural language answers powered by agent analytics"}
            </p>
          </div>
        </div>
      </div>



      {/* Messages Thread Container */}
      <div className="flex-1 overflow-y-auto py-4 space-y-4 pr-1">
        {messages.map((msg) => {
          const isUser = msg.sender === "user";
          return (
            <div
              key={msg.id}
              className={`flex items-start gap-3 ${
                isUser ? "flex-row-reverse" : "flex-row"
              }`}
            >
              {/* Avatar */}
              <div
                className={`w-8 h-8 rounded-xl flex items-center justify-center shrink-0 ${
                  isUser
                    ? "bg-slate-900 text-white"
                    : "bg-blue-600 text-white shadow-xs"
                }`}
              >
                {isUser ? (
                  <User className="w-4 h-4" />
                ) : (
                  <Bot className="w-4 h-4" />
                )}
              </div>

              {/* Bubble */}
              <div
                className={`max-w-[82%] rounded-2xl p-4 text-xs leading-relaxed space-y-2 ${
                  isUser
                    ? "bg-blue-600 text-white font-medium rounded-tr-xs"
                    : "bg-slate-100/90 text-slate-800 border border-slate-200/80 rounded-tl-xs"
                }`}
              >
                {msg.isEmptyDatasetState ? (
                  <div className="p-4 bg-white border border-blue-200 rounded-xl space-y-3 text-slate-800 shadow-2xs">
                    <div className="flex items-center gap-2 text-blue-900 font-bold text-xs">
                      <Database className="w-4 h-4 text-blue-600 shrink-0" />
                      <span>No Active Dataset Context</span>
                    </div>
                    <p className="text-xs text-slate-600 leading-relaxed">
                      Please upload a CSV or Excel dataset file in the Data Ingestion center to start asking analytical questions.
                    </p>
                    {onNavigateToUpload && (
                      <button
                        onClick={onNavigateToUpload}
                        className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs rounded-lg shadow-xs transition-all flex items-center gap-1.5"
                      >
                        <UploadCloud className="w-3.5 h-3.5" />
                        <span>Go to Data Upload Center</span>
                      </button>
                    )}
                  </div>
                ) : (!isUser && msg.data?.sections && msg.data.sections.length > 0) ? null : (
                  <p className="font-medium text-sm whitespace-pre-wrap">{msg.text}</p>
                )}

                {/* Structured Analytics Visualization (Tables, Charts, Funnels, Sections) */}
                {!isUser && msg.data && !msg.isEmptyDatasetState && (
                  <AnalyticsRenderer response={msg.data} />
                )}

                {/* Dynamic Recommendations Chips */}
                {!isUser && msg.data?.recommendations && msg.data.recommendations.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-slate-200/60 flex flex-wrap gap-2">
                    <div className="w-full text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1">
                      <Sparkles className="w-3 h-3 text-blue-500 animate-pulse" /> Suggested follow-ups:
                    </div>
                    {msg.data.recommendations.map((rec, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleSend(rec.question)}
                        disabled={isLoading}
                        className="text-xs font-semibold text-slate-700 bg-white border border-slate-200 hover:border-blue-500 hover:bg-blue-50/50 hover:text-blue-600 px-3 py-1.5 rounded-xl transition-all shadow-3xs cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed text-left max-w-full"
                      >
                        {rec.label}
                      </button>
                    ))}
                  </div>
                )}

                <div
                  className={`text-[10px] text-right font-medium ${
                    isUser ? "text-blue-200" : "text-slate-400"
                  }`}
                >
                  {msg.timestamp}
                </div>
              </div>
            </div>
          );
        })}

        {/* Loading Bubble Indicator */}
        {isLoading && (
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-xl bg-blue-600 text-white flex items-center justify-center shadow-xs">
              <Bot className="w-4 h-4 animate-pulse" />
            </div>
            <div className="bg-slate-100 text-slate-600 rounded-2xl rounded-tl-xs p-4 text-xs flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
              <span>Analyzing dataset & querying active context...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Bar */}
      <div className="pt-3 border-t border-slate-100 shrink-0">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center gap-2"
        >
          <input
            type="text"
            value={inputQuestion}
            onChange={(e) => setInputQuestion(e.target.value)}
            placeholder="Ask a question about admissions, funnel, or sources..."
            disabled={isLoading}
            className="flex-1 px-4 py-3 text-xs font-semibold text-slate-800 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all placeholder:text-slate-400"
          />

          <button
            type="submit"
            disabled={isLoading || !inputQuestion.trim()}
            className="flex items-center gap-2 px-5 py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl shadow-sm transition-all"
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <>
                <span>Ask AI</span>
                <Send className="w-3.5 h-3.5" />
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
};
