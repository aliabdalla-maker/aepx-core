"use strict";
// electron-builder afterPack hook: flips Electron fuses on the packaged binary (before signing), so the
// shipped app cannot be run as a plain Node runtime, ignores NODE_OPTIONS / --inspect, encrypts cookies
// and loads only its integrity-checked app.asar.
const path = require("node:path");
const { flipFuses, FuseVersion, FuseV1Options } = require("@electron/fuses");

module.exports = async function afterPack(context) {
  const { appOutDir, electronPlatformName, packager, arch } = context;
  const name = packager.appInfo.productFilename;
  // Resolve only the current platform's binary: executableName exists on the Linux packager only.
  let binary;
  if (electronPlatformName === "darwin" || electronPlatformName === "mas") binary = path.join(appOutDir, `${name}.app`);
  else if (electronPlatformName === "win32") binary = path.join(appOutDir, `${name}.exe`);
  else if (electronPlatformName === "linux") binary = path.join(appOutDir, packager.executableName);
  else throw new Error(`No fuse target for ${electronPlatformName}`);
  await flipFuses(binary, {
    version: FuseVersion.V1,
    resetAdHocDarwinSignature: electronPlatformName === "darwin" && arch === 3, // arm64 needs re-sign
    [FuseV1Options.RunAsNode]: false,
    [FuseV1Options.EnableCookieEncryption]: true,
    [FuseV1Options.EnableNodeOptionsEnvironmentVariable]: false,
    [FuseV1Options.EnableNodeCliInspectArguments]: false,
    [FuseV1Options.EnableEmbeddedAsarIntegrityValidation]: true,
    [FuseV1Options.OnlyLoadAppFromAsar]: true,
    [FuseV1Options.GrantFileProtocolExtraPrivileges]: false, // the app never loads file:// content
  });
};
