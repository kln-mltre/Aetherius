// Metro sees two things outside this directory, and both are deliberate:
//
//   - `@aetherius/engine` and `@aetherius/react-native`, linked with `file:` — npm symlinks them,
//     so Metro must be told the real directories are part of the project or it refuses to follow
//     the link;
//   - the Blueprints of `examples/`, imported as ordinary JSON. Bundling the very files the Python
//     engine runs is the point: "the same Blueprint, both engines" has to be true of this app too.
//
// Hence a watch folder on the repository root, and a resolver that keeps looking up for modules.

const path = require("node:path");
const { getDefaultConfig } = require("expo/metro-config");

const projectRoot = __dirname;
const repoRoot = path.resolve(projectRoot, "..", "..", "..");

const config = getDefaultConfig(projectRoot);

config.watchFolders = [repoRoot];
config.resolver.nodeModulesPaths = [
  path.resolve(projectRoot, "node_modules"),
  path.resolve(repoRoot, "sdks", "node_modules"),
];
// The engine ships as an ES module with an `exports` map; without this Metro falls back to `main`
// and misses the declared entry point.
config.resolver.unstable_enablePackageExports = true;

/**
 * Packages that must have exactly **one** instance in the bundle.
 *
 * A symlinked workspace package resolves its own peers from `sdks/node_modules` — where npm
 * installs them regardless of `peerDependenciesMeta.optional`. Two copies of React means two hook
 * dispatchers, and the second one is `null`: the crash reads `Cannot read property 'useRef' of
 * null` / `Invalid hook call`, which points at the component rather than at the resolution.
 *
 * Re-rooting the resolution at the application is the fix every React Native monorepo ends up
 * with, and it is worth stating rather than discovering twice.
 */
const SINGLETONS = new Set(["react", "react-native", "react-native-webview", "scheduler"]);

// The application's own entry point: resolving *as if from here* always lands on its copy.
const appOrigin = path.join(projectRoot, "index.js");

config.resolver.resolveRequest = (context, moduleName, platform) => {
  const root = moduleName.split("/")[0];
  const from = SINGLETONS.has(root) ? { ...context, originModulePath: appOrigin } : context;
  return context.resolveRequest(from, moduleName, platform);
};

module.exports = config;
