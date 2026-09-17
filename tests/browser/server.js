/* Static file server for the browser tests.
 *
 * Serves docs/ as GitHub Pages would, but with the finder's data files
 * swapped for the fixtures in tests/browser/fixtures/. The committed
 * docs/finder/data/{policies,grants}.json are refreshed weekly by the
 * finder-data workflow, so asserting against them would make CI fail every
 * time the EU corpus moves. The fixtures are frozen, so every assertion here
 * is about the app's behaviour rather than the state of the EU.
 */
'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
};

/** Start a server for `docsDir`, with `overrides` mapping URL path → file. */
function startServer(docsDir, overrides = {}) {
  const server = http.createServer((req, res) => {
    const urlPath = decodeURIComponent(req.url.split('?')[0]);
    const override = overrides[urlPath];
    const filePath = override || path.join(docsDir, urlPath);

    // Never serve outside the served roots, even if a test is miswritten.
    const resolved = path.resolve(filePath);
    const allowed = override
      ? resolved === path.resolve(override)
      : resolved.startsWith(path.resolve(docsDir) + path.sep);
    if (!allowed) {
      res.writeHead(403).end('forbidden');
      return;
    }

    fs.readFile(resolved, (err, body) => {
      if (err) {
        res.writeHead(404, { 'content-type': 'text/plain' }).end('not found');
        return;
      }
      res.writeHead(200, {
        'content-type': TYPES[path.extname(resolved)] || 'application/octet-stream',
        'cache-control': 'no-store',
      }).end(body);
    });
  });

  return new Promise(resolve => {
    // Port 0 → the OS picks a free one, so parallel runs never collide.
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      resolve({
        baseUrl: `http://127.0.0.1:${port}`,
        close: () => new Promise(done => server.close(done)),
      });
    });
  });
}

module.exports = { startServer };
