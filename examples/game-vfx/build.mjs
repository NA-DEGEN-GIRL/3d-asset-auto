import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { mkdir, copyFile, writeFile, stat } from 'node:fs/promises';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../..');
const require = createRequire(path.join(root, 'web/package.json'));
const { build } = require('esbuild');
const output = path.join(root, '.work/game-vfx');
const testing = process.argv.includes('--test');
const mediaIndex = process.argv.indexOf('--media-dir');
const config = { version: 1, available: false, resources: null, references: {} };

// Publish a fixed list into an isolated preview directory, never the workspace.
let mediaDir = null;
if (!testing && mediaIndex !== -1) {
  const argument = process.argv[mediaIndex + 1];
  if (!argument || argument.startsWith('--')) throw new Error('--media-dir requires a directory');
  mediaDir = path.resolve(argument);
  for (const name of ['noise.png', 'recipes.json', 'ice.glb', 'fire.png', 'ice.png', 'lightning.png']) {
    if (!(await stat(path.join(mediaDir, name))).isFile()) throw new Error(`Required VFX media is missing: ${name}`);
  }
  config.resources = { noise: 'noise.png', recipes: 'recipes.json', ice: 'ice.glb' };
  for (const id of ['fire', 'ice', 'lightning']) {
    const name = `${id}.mp4`;
    let video = null;
    try { if ((await stat(path.join(mediaDir, name))).isFile()) video = name; }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    config.references[id] = { image: `${id}.png`, video };
  }
  config.available = true;
}

await mkdir(path.join(output, 'site'), { recursive: true });
await build({
  absWorkingDir: root,
  entryPoints: [path.join(here, testing ? 'effects.test.mjs' : 'preview.js')],
  outfile: path.join(output, testing ? 'effects.test.cjs' : 'site/preview.js'),
  nodePaths: [path.join(root, 'web/node_modules')],
  bundle: true, platform: testing ? 'node' : 'browser',
  format: testing ? 'cjs' : 'esm', target: testing ? 'node20' : 'es2022',
  minify: !testing, logLevel: 'info',
});
if (!testing) {
  for (const name of ['index.html', 'style.css']) await copyFile(path.join(here, name), path.join(output, 'site', name));
  await copyFile(path.join(here, 'LICENSE.txt'), path.join(output, 'site/LICENSE.txt'));
  await copyFile(path.join(root, 'web/node_modules/three/LICENSE'), path.join(output, 'site/THREE-LICENSE.txt'));
  if (mediaDir) {
    const names = ['noise.png', 'recipes.json', 'ice.glb', ...Object.values(config.references).flatMap((ref) => [ref.image, ref.video].filter(Boolean))];
    for (const name of names) await copyFile(path.join(mediaDir, name), path.join(output, 'site', name));
  }
  await writeFile(path.join(output, 'site/config.json'), `${JSON.stringify(config, null, 2)}\n`);
}
