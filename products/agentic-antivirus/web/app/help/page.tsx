"use client";
import { useI18n } from "../../lib/i18n";
import { StaticPage } from "../../components/StaticPage";

export default function Help() {
  const { t } = useI18n();
  return (
    <StaticPage title={t("help.title")}>
      <h2>{t("ui.protect_a_device")}</h2>
      <p>{t("ui.go_to_devices_choose_enrol_a")}</p>
      <h2>{t("ui.when_something_is_blocked")}</h2>
      <p>{t("ui.known_malware_is_moved_to_quarantine")}</p>
      <h2>{t("ui.approving_actions")}</h2>
      <p>{t("ui.stopping_processes_isolating_devices_restoring_files")}</p>
      <h2>{t("ui.the_ai_assistant")}</h2>
      <p>{t("ui.the_assistant_groups_related_alerts_lists")}</p>
      <h2>{t("ui.contact")}</h2>
      <p>{t("ui.email_support_at")} <a href="mailto:support@softwareequality.com">{t("ui.support_softwareequality_com")}</a>.</p>
    </StaticPage>);
}
