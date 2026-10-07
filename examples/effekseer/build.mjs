import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { mkdir, readFile, writeFile, cp, readdir, stat, lstat, realpath } from 'node:fs/promises';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '../..');
const require = createRequire(path.join(repo, 'web/package.json'));
const { build } = require('esbuild');
const args = process.argv.slice(2);
const options = {};
for (let i = 0; i < args.length; i += 2) {
  if (!['--runtime', '--effects', '--out'].includes(args[i]) || !args[i + 1]) {
    throw new Error('Usage: node examples/effekseer/build.mjs --runtime <webgl-runtime> --effects <effect-bundle> --out <site>');
  }
  options[args[i].slice(2)] = path.resolve(args[i + 1]);
}
if (!options.runtime || !options.effects || !options.out) throw new Error('Missing --runtime, --effects or --out');
options.runtime = await realpath(options.runtime);
options.effects = await realpath(options.effects);
// Resolve existing parents as well, so junctions cannot hide overlapping paths.
async function canonicalDestination(candidate) {
  try {
    return await realpath(candidate);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    const parent = path.dirname(candidate);
    if (parent === candidate) throw error;
    return path.join(await canonicalDestination(parent), path.basename(candidate));
  }
}
options.out = await canonicalDestination(options.out);
function contains(parent, candidate) {
  const relative = path.relative(parent, candidate);
  return relative === '' || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative));
}
for (const source of [options.effects, options.runtime]) {
  if (contains(source, options.out) || contains(options.out, source)) throw new Error('Output must not overlap the effect bundle or runtime directory');
}
try {
  await lstat(options.out);
  throw new Error('Output already exists. Choose a fresh site directory to preserve previous revisions.');
} catch (error) {
  if (error.code !== 'ENOENT') throw error;
}
// Require and retain the licenses of both shipped rendering libraries.
await stat(path.join(options.runtime, 'LICENSE'));
const threeLicense = path.join(repo, 'web/node_modules/three/LICENSE');
await stat(threeLicense);
const manifest = JSON.parse(await readFile(path.join(options.effects, 'effects.json'), 'utf8'));
if (manifest.version !== 1 || !Array.isArray(manifest.effects) || !manifest.effects.length) throw new Error('Expected version:1 and a non-empty effects array');
const ids = new Set();
for (const effect of manifest.effects) {
  if (!effect.id || ids.has(effect.id)) throw new Error('Each effect needs a unique id');
  ids.add(effect.id);
  if (typeof effect.url !== 'string' || !/^effects\/[\w ./-]+\.(efkefc|efk)$/.test(effect.url) || effect.url.split('/').includes('..')) throw new Error(`Effect ${effect.id}: use a relative effects/ runtime URL`);
  if (typeof effect.duration !== 'number' || effect.duration <= 0 || effect.duration > 60) throw new Error(`Effect ${effect.id}: duration must be 0–60 seconds`);
  await stat(path.join(options.effects, effect.url));
}
await mkdir(options.out, { recursive: true });
await mkdir(path.join(options.out, 'runtime'), { recursive: true });
for (const name of ['effekseer.js', 'effekseer.wasm', 'LICENSE']) {
  await cp(path.join(options.runtime, name), path.join(options.out, 'runtime', name));
}
await cp(threeLicense, path.join(options.out, 'runtime/THREE-LICENSE.txt'));
// Only exported playback ingredients are served, never the runtime root or editor source.
const permitted = new Set(['.efkefc', '.efk', '.efkmodel', '.efkmat', '.png', '.jpg', '.jpeg', '.dds', '.wav', '.ogg']);
const isNotice = name => /^(ATTRIBUTION\.txt|LICENSE(?:\.txt)?|COPYING(?:\.txt)?)$/i.test(name);
async function copyPlayback(source, destination) {
  await mkdir(destination, { recursive: true });
  for (const item of await readdir(source, { withFileTypes: true })) {
    if (item.isSymbolicLink()) throw new Error(`Effect bundles must not contain symlinks: ${item.name}`);
    const from = path.join(source, item.name), to = path.join(destination, item.name);
    if (item.isDirectory()) await copyPlayback(from, to);
    else if (permitted.has(path.extname(item.name).toLowerCase()) || isNotice(item.name)) await cp(from, to);
  }
}
await copyPlayback(path.join(options.effects, 'effects'), path.join(options.out, 'effects'));
await writeFile(path.join(options.out, 'effects.json'), JSON.stringify(manifest, null, 2) + '\n');
await cp(path.join(here, 'index.html'), path.join(options.out, 'index.html'));
await cp(path.join(here, 'style.css'), path.join(options.out, 'style.css'));
await build({
  absWorkingDir: here, entryPoints: ['main.js'], bundle: true, format: 'esm', minify: true,
  outfile: path.join(options.out, 'app.js'), nodePaths: [path.join(repo, 'web/node_modules')], logLevel: 'info',
});
console.log(`Effekseer gallery built: ${options.out}`);
