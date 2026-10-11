import { useTranslation } from "react-i18next";
import PageShell from "../../../layouts/PageShell";
import { useIsMobile } from "../../../hooks/useIsMobile";
import BridgeSettingsPanel from "../AdvancedSettings/BridgeSettings";

/** User-scoped remote bridge settings (Settings → under Knowledge Bases). */
export default function BridgePage() {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  return (
    <PageShell
      title={t("pageShell.bridge.title")}
      subtitle={isMobile ? undefined : t("pageShell.bridge.subtitle")}
    >
      <BridgeSettingsPanel asPage />
    </PageShell>
  );
}
