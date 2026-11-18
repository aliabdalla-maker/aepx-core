import { StaticPage } from "../../components/StaticPage";

export default function Privacy() {
  return (
    <StaticPage title="Privacy">
      <p>Equality Software Ltd operates Agentic Antivirus. This page describes what the service collects. It must be reviewed by the product owner before publication.</p>
      <h2>What devices send</h2>
      <p>By default the agent sends security telemetry and file hashes: process names and command lines, file paths, network connection metadata, and detections. File contents are collected only if your organisation turns that on.</p>
      <h2>Voice</h2>
      <p>Read-aloud and dictation use your browser's built-in speech features. We do not record or store audio.</p>
      <h2>Advertising</h2>
      <p>During the free trial, and on unpaid plans, the console shows Google AdSense adverts and the mobile apps show Google AdMob adverts, after asking for your consent. Subscribers see 95% fewer adverts. Adverts never appear on approval, containment, threat warning, quarantine review, sign-in, payment or audit screens.</p>
      <h2>Retention</h2>
      <p>Your organisation sets how long telemetry and evidence are kept. Audit records cannot be edited or deleted.</p>
      <h2>Your rights</h2>
      <p>You can delete your account from your profile. Contact <a href="mailto:privacy@softwareequality.com">privacy@softwareequality.com</a> for access or correction requests.</p>
    </StaticPage>);
}
