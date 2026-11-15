"use strict";
// electron-builder afterPack hook: flips Electron fuses on the packaged binary (before signing), so the
// shipped app cannot be run as a plain Node runtime, ignores NODE_OPTIONS / --inspect, encrypts cookies
// and loads only its integrity-checked app.asar.
const path = require("node:path");
const { flipFuses, FuseVersion, FuseV1Options } = require("@electron/fuses");

module.exports = async function afterPack(context) {
  const { appOutDir, electronPlatformName, packager, arch } = context;
  const name = packager.appInfo.productFilename;
  const binary = {
    darwin: path.join(appOutDir, `${name}.app`),
    mas: path.join(appOutDir, `${name}.app`),
    win32: path.join(appOutDir, `${name}.exe`),
    linux: path.join(appOutDir, packager.executableName),
  }[electronPlatformName];
  if (!binary) throw new Error(`No fuse target for ${electronPlatformName}`);
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
