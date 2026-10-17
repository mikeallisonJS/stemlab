// electron-builder configuration. A script rather than JSON so that Windows
// code signing can be switched on from the environment.
//
// Signing uses Azure Artifact Signing (formerly Trusted Signing), the same
// service and the same six values as Cadent's installer workflow, so one
// signing account serves both apps. Three states, decided here once:
//
//   none of the six set   unsigned build; it runs, SmartScreen warns on first launch
//   all six set           every .exe in the app and the installer are signed and timestamped
//   some set              a mistake: the build fails rather than ship an unsigned
//                         installer to somebody who asked for a signed one
//
//   AZURE_TENANT_ID               the Entra tenant holding the signing identity
//   AZURE_CLIENT_ID               app registration with the Code Signing Certificate Profile Signer role
//   AZURE_CLIENT_SECRET           its client secret (read by the signing module, never by us)
//   STEMLAB_SIGN_ENDPOINT    regional URI, e.g. https://eus.codesigning.azure.net/
//   STEMLAB_SIGN_ACCOUNT     Artifact Signing account name
//   STEMLAB_SIGN_PROFILE     certificate profile name within that account
//
// electron-builder installs the TrustedSigning PowerShell module on the build
// machine and signs with Invoke-TrustedSigning; the private key never leaves
// Azure. .github/workflows/release.yml maps the repository's AZURE_SIGN_*
// secrets onto these names.

const credentials = ["AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"];
const target = ["STEMLAB_SIGN_ENDPOINT", "STEMLAB_SIGN_ACCOUNT", "STEMLAB_SIGN_PROFILE"];

function windowsSigning() {
  const names = [...credentials, ...target];
  const present = names.filter((name) => process.env[name]);
  if (present.length === 0) {
    console.log("electron-builder: no Artifact Signing variables set, building unsigned");
    return {};
  }
  if (present.length !== names.length) {
    const missing = names.filter((name) => !process.env[name]).join(", ");
    throw new Error(`Windows signing needs all of ${names.join(", ")}; missing: ${missing}`);
  }
  console.log(`electron-builder: signing with Artifact Signing account ${process.env.STEMLAB_SIGN_ACCOUNT}`);
  return {
    azureSignOptions: {
      endpoint: process.env.STEMLAB_SIGN_ENDPOINT,
      codeSigningAccountName: process.env.STEMLAB_SIGN_ACCOUNT,
      certificateProfileName: process.env.STEMLAB_SIGN_PROFILE,
      timestampRfc3161: "http://timestamp.acs.microsoft.com",
    },
    signingHashAlgorithms: ["sha256"],
  };
}

// Auto-update: the app checks this folder for latest.yml (latest-linux.yml,
// latest-mac.yml) and downloads the installer named there. The release
// workflow uploads them to Cloudflare R2 behind this host, the same bucket
// and secrets as Cadent. GitHub release assets would redirect to expiring
// links, which electron-updater copes with but the Microsoft Store does not,
// and the Store takes the same installer from the same host.
const UPDATE_URL = process.env.STEMLAB_UPDATE_URL || "https://downloads.mikeallisonjs.com/stemlab";

module.exports = {
  appId: "dev.stemlab.app",
  productName: "Stemlab",
  // assets/ rather than the default build/: build/ is gitignored (the engine is
  // assembled there), and the icon is a source. assets/icon.png is rendered by
  // scripts/build-icons.mjs; electron-builder derives the .ico and .icns from it.
  directories: { output: "release", buildResources: "assets" },
  files: ["dist-electron/**", "assets/icon.png", "package.json"],
  // The engine: the wheel, recipes, MSST, the built UI and FFmpeg (scripts/prepare-engine.mjs)
  extraResources: [{ from: "build/engine", to: "engine" }],
  asar: true,
  // Written into resources/app-update.yml for electron-updater; uploads are the workflow's job
  publish: [{ provider: "generic", url: UPDATE_URL, channel: "latest" }],
  win: {
    target: ["nsis"],
    artifactName: "Stemlab-Setup-${version}.${ext}",
    ...windowsSigning(),
  },
  nsis: {
    oneClick: false,
    allowToChangeInstallationDirectory: true,
    deleteAppDataOnUninstall: false,
  },
  linux: { target: ["AppImage"], artifactName: "Stemlab-${version}.${ext}", category: "AudioVideo" },
  // The zip is what electron-updater downloads on macOS; the dmg is for people
  mac: { target: ["dmg", "zip"], artifactName: "Stemlab-${version}.${ext}", category: "public.app-category.music" },
};
