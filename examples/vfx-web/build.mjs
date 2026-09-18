import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { mkdir, copyFile, writeFile, stat } from 'node:fs/promises';

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
  const config = { soul: null };
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
  await writeFile(path.join(output, 'site/config.json'), JSON.stringify(config, null, 2));
}
