import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { mkdir, copyFile, writeFile, readFile, stat } from 'node:fs/promises';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../..');
const require = createRequire(path.join(root, 'web/package.json'));
const { build } = require('esbuild');
const output = path.join(root, '.work/vfx-web');
const testing = process.argv.includes('--test');
await mkdir(path.join(output, 'site'), { recursive: true });
await build({
  absWorkingDir: root,
  entryPoints: [path.join(here, testing ? 'effect.test.mjs' : 'preview.js')],
  outfile: path.join(output, testing ? 'effect.test.cjs' : 'site/preview.js'),
  nodePaths: [path.join(root, 'web/node_modules')],
  bundle: true,
  platform: testing ? 'node' : 'browser',
  format: testing ? 'cjs' : 'esm',
  target: testing ? 'node20' : 'es2022',
  minify: !testing,
  logLevel: 'info',
});
if (!testing) {
  for (const name of ['index.html', 'style.css']) {
    await copyFile(path.join(here, name), path.join(output, 'site', name));
  }
  const mediaIndex = process.argv.indexOf('--media-dir');
  const config = { soul: null, ice: null };
  if (mediaIndex !== -1) {
    const argument = process.argv[mediaIndex + 1];
    if (!argument || argument.startsWith('--')) throw new Error('--media-dir requires a directory');
    const mediaDir = path.resolve(argument);
    const names = ['soul-flame.png', 'soul-flame.mp4', 'soul-atlas.png'];
    for (const name of names) {
      if (!(await stat(path.join(mediaDir, name))).isFile()) throw new Error(`Missing media: ${name}`);
    }
    for (const name of names) await copyFile(path.join(mediaDir, name), path.join(output, 'site', name));
    config.soul = { image: 'soul-flame.png', video: 'soul-flame.mp4', atlas: 'soul-atlas.png',
      columns: 8, rows: 12, frames: 96, fps: 16 };
  }
  const iceIndex = process.argv.indexOf('--ice-dir');
  if (iceIndex !== -1) {
    const argument = process.argv[iceIndex + 1];
    if (!argument || argument.startsWith('--')) throw new Error('--ice-dir requires a directory');
    const directory = path.resolve(argument);
    const events = JSON.parse(await readFile(path.join(directory, 'ice-events.json'), 'utf8'));
    if (!events.clip || !Number.isFinite(events.duration) || events.duration <= 0
        || !Number.isFinite(events.impact) || events.impact < 0 || events.impact >= events.duration
        || !Number.isFinite(events.start_offset ?? 0) || (events.start_offset ?? 0) < 0
        || !Array.isArray(events.moments) || events.moments.length !== 4
        || !events.moments.every((time) => Number.isFinite(time) && time >= 0 && time <= events.duration)) {
      throw new Error('Invalid ice playback contract');
    }
    for (const name of ['ice.glb', 'ice.png', 'ice.mp4']) {
      await copyFile(path.join(directory, name), path.join(output, 'site', name));
    }
    config.ice = { model: 'ice.glb', image: 'ice.png', video: 'ice.mp4', events };
  }
  await writeFile(path.join(output, 'site/config.json'), JSON.stringify(config, null, 2));
}
