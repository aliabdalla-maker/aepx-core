import { StaticPage } from "../../components/StaticPage";

export default function Help() {
  return (
    <StaticPage title="Help">
      <h2>Protect a device</h2>
      <p>Go to Devices, choose Enrol a device, and run the command shown on the computer you want to protect. The agent starts scanning as soon as it receives its signed policy.</p>
      <h2>When something is blocked</h2>
      <p>Known malware is moved to quarantine, where it cannot run. If you think a file was blocked by mistake, open Quarantine and request a review. An administrator decides, and the file comes back only after a fresh scan finds it clean.</p>
      <h2>Approving actions</h2>
      <p>Stopping processes, isolating devices, restoring files, adding exclusions and changing traffic rules need a person to approve them. An approval covers one action, its exact targets and a limited time. If anything changes, approve again.</p>
      <h2>The AI assistant</h2>
      <p>The assistant groups related alerts, lists what was observed with links to the evidence, and marks anything it cannot prove as a hypothesis. It can suggest actions but cannot approve them. If the model is unavailable, scanning, alerts and manual responses keep working.</p>
      <h2>Contact</h2>
      <p>Email support at <a href="mailto:support@softwareequality.com">support@softwareequality.com</a>.</p>
    </StaticPage>);
}
