"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { useApp } from "../../context/AppContext";
import { ChatPanel } from "../../components/ChatPanel";

export default function AIAnalystPage() {
  const router = useRouter();
  const { activeDataset, seededPrompt, setSeededPrompt } = useApp();

  return (
    <div className="space-y-6">
      <ChatPanel
        onNavigateToUpload={() => router.push("/upload")}
        activeDatasetName={activeDataset?.dataset_name}
        initialQuestion={seededPrompt}
        onClearInitialQuestion={() => setSeededPrompt("")}
      />
    </div>
  );
}
