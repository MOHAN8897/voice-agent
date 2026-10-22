import { SaasUniversalPhoneStack } from "@/components/dev/SaasUniversalPhoneStack";
import { PageHeader } from "@/components/console/PageHeader";

export default function DevSaasPhoneStackPage() {
  return (
    <div>
      <PageHeader
        eyebrow="SaaS product"
        title="Universal phone AI stack"
        description="One live-phone stack for every subscriber tenant. Agents only choose voice, language, and script — not STT/LLM/TTS tiers."
      />
      <div className="mt-6">
        <SaasUniversalPhoneStack />
      </div>
    </div>
  );
}
