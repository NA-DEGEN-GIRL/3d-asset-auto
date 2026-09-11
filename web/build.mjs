import { build } from 'esbuild';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root = path.dirname(fileURLToPath(import.meta.url));
await mkdir(path.join(root,'dist'), { recursive: true });
await build({absWorkingDir:root,entryPoints:['src/main.js'],bundle:true,format:'esm',minify:true,
  outfile:'dist/app.js',logLevel:'info',sourcemap:true});
const html=(await readFile(path.join(root,'index.html'),'utf8'))
  .replace('/src/main.js','/app.js').replace('</head>','<link rel="stylesheet" href="/app.css" /></head>');
await writeFile(path.join(root,'dist/index.html'),html);
