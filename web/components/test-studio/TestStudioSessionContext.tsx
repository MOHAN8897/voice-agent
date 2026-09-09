"use client";

import { createContext, useContext } from "react";

type TestStudioSessionContextValue = {
  agentId: string;
  sessionId: string;
};

const TestStudioSessionContext = createContext<TestStudioSessionContextValue | null>(null);

export function TestStudioSessionProvider({
  agentId,
  sessionId,
  children,
}: {
  agentId: string;
  sessionId: string;
  children: React.ReactNode;
}) {
  return (
    <TestStudioSessionContext.Provider value={{ agentId, sessionId }}>
      {children}
    </TestStudioSessionContext.Provider>
  );
}

export function useTestStudioSession(): TestStudioSessionContextValue {
  const ctx = useContext(TestStudioSessionContext);
  if (!ctx) {
    throw new Error("useTestStudioSession must be used inside TestStudioSessionProvider");
  }
  return ctx;
}

export function useTestStudioSessionOptional(): TestStudioSessionContextValue | null {
  return useContext(TestStudioSessionContext);
}
