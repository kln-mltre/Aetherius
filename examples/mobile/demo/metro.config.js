// Metro sees two things outside this directory, and both are deliberate:
//
//   - `@aetherius/engine`, linked with `file:` — npm symlinks it, so Metro must be told the real
//     directory is part of the project or it refuses to follow the link;
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

module.exports = config;
