import { Empty } from "antd";
import { useTranslation } from "react-i18next";
import PageShell from "../../layouts/PageShell";
import { useIsMobile } from "../../hooks/useIsMobile";

interface Props {
  title?: string;
  subtitle?: string;
}

/**
 * Temporary placeholder for admin pages pending sub-project ⑨.
 */
export default function AdminPlaceholder({ title, subtitle }: Props) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  return (
    <PageShell
      title={title || t("common.comingSoon", "Coming soon")}
      subtitle={isMobile ? undefined : subtitle}
    >
      <Empty
        description={t(
          "common.notImplemented",
          "This page is under construction.",
        )}
      />
    </PageShell>
  );
}
