"use client";
import { useI18n } from "../../lib/i18n";
import { StaticPage } from "../../components/StaticPage";

export default function Privacy() {
  const { t } = useI18n();
  return (
    <StaticPage title={t("privacy.title")}>
      <p>{t("ui.equality_software_ltd_operates_agentic_antivirus")}</p>
      <h2>{t("ui.what_devices_send")}</h2>
      <p>{t("ui.by_default_the_agent_sends_security")}</p>
      <h2>{t("voice.voice")}</h2>
      <p>{t("ui.read_aloud_and_dictation_use_your")}</p>
      <h2>{t("ui.advertising")}</h2>
      <p>{t("ui.during_the_free_trial_and_on")}</p>
      <h2>{t("ui.retention")}</h2>
      <p>{t("ui.your_organisation_sets_how_long_telemetry")}</p>
      <h2>{t("ui.your_rights")}</h2>
      <p>{t("ui.you_can_delete_your_account_from")} <a href="mailto:privacy@softwareequality.com">{t("ui.privacy_softwareequality_com")}</a> {t("ui.for_access_or_correction_requests")}</p>
    </StaticPage>);
}
