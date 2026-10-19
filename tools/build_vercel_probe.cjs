const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const output = path.join(root, 'probe-dist');
fs.mkdirSync(output, {recursive: true});
fs.copyFileSync(path.join(root, 'deploy/vercel-probe/public/cloud.html'), path.join(output, 'index.html'));
for (const name of ['cloud.mjs','cloud.css','ranking.mjs']) fs.copyFileSync(path.join(root,'deploy/vercel-probe/public',name),path.join(output,name));
for (const name of ['airports.json','city-groups.json','favicon.svg']) fs.copyFileSync(path.join(root,'flightcore/web',name),path.join(output,name));
console.log('Journey Note cloud client built. Local FastAPI files remain unchanged.');
