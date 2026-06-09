// patch-deployment.cjs — injects a 'single' (single-container) URL mode into a
// COPY of the umbrella UI's deployment.ts during the image build. The repo
// source is never modified; this only runs against the file copied into the
// build stage.
//
// In single mode, resolveAppUrl() returns an in-container path route
// (/a/<app>/) handled by the all-in-one nginx, instead of a localhost:port
// (local mode) or per-app Code Engine URL (remote mode).
//
// Usage: node patch-deployment.cjs <path-to-deployment.ts>
const fs = require('fs');

const file = process.argv[2] || 'src/data/deployment.ts';
let s = fs.readFileSync(file, 'utf8');

if (s.includes("VITE_DEPLOYMENT_TARGET === 'single'")) {
  console.log('patch-deployment: already patched');
  process.exit(0);
}

// Anchor: the first statement of resolveAppUrl(). Insert our branch right after
// it so single mode short-circuits before the local/remote logic.
const anchor = 'if (!uc.appUrl) return null';
if (!s.includes(anchor)) {
  console.error('patch-deployment: anchor not found in ' + file);
  process.exit(1);
}

const inject = anchor +
  '\n  // single-container build: route to /a/<app>/ behind the all-in-one nginx.' +
  '\n  if ((import.meta as any).env && (import.meta as any).env.VITE_DEPLOYMENT_TARGET === \'single\') {' +
  '\n    const _ce = CE_APP_BY_ID[uc.id];' +
  '\n    return _ce ? \'/a/\' + _ce.replace(/^cuga-apps-/, \'\') + \'/\' : null;' +
  '\n  }';

s = s.replace(anchor, inject);
fs.writeFileSync(file, s);
console.log('patch-deployment: injected single mode into ' + file);
