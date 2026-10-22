import { TestStudioLayout } from "@/components/test-studio/TestStudioLayout";

export default function DevTestStudioLayout({ children }: { children: React.ReactNode }) {
  return <TestStudioLayout portal="dev">{children}</TestStudioLayout>;
}
