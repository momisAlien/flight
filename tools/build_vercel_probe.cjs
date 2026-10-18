const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'probe-dist');
fs.mkdirSync(output, {recursive: true});
fs.copyFileSync(path.join(root, 'deploy/vercel-probe/public/index.html'), path.join(output, 'index.html'));
console.log('Runtime verification page built; flight search remains unconnected.');
