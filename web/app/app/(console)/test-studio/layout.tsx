import { TestStudioLayout } from "@/components/test-studio/TestStudioLayout";

export default function AppTestStudioLayout({ children }: { children: React.ReactNode }) {
  return <TestStudioLayout portal="app">{children}</TestStudioLayout>;
}
