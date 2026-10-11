'use strict';

// Test-only loopback server. It never edits the build, sources, or external services.
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const HOST = '127.0.0.1';
const PORT = 4175;
const ORIGIN = 'http://' + HOST + ':' + PORT;
const ROOT = path.resolve(__dirname, '..');
const OUT = fs.realpathSync(path.join(ROOT, 'out'));
const ORIGINAL_CACHE = 'foodsave-shell-v1-20261009';
const NEXT_CACHE = 'foodsave-shell-v2-qa-20261011';
const original = fs.readFileSync(path.join(ROOT, 'public', 'sw.js'));
const originalText = original.toString('utf8');

if (!Buffer.from(originalText, 'utf8').equals(original)) {
  throw new Error('The original service worker must be valid UTF-8.');
}
if (originalText.split(ORIGINAL_CACHE).length !== 2 ||
    !originalText.includes("const CACHE='" + ORIGINAL_CACHE + "';")) {
  throw new Error('The expected service-worker cache token must occur exactly once.');
}
if (!fs.readFileSync(path.join(OUT, 'sw.js')).equals(original)) {
  throw new Error('out/sw.js must match public/sw.js before PWA validation.');
}
const successor = Buffer.from(originalText.replace(ORIGINAL_CACHE, NEXT_CACHE), 'utf8');
const variants = {1: original, 2: successor};
let version = 1;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.mjs': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.webmanifest': 'application/manifest+json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.txt': 'text/plain; charset=utf-8',
  '.map': 'application/json; charset=utf-8'
};

function send(request, response, status, body, type) {
  const bytes = Buffer.isBuffer(body) ? body : Buffer.from(body);
  response.writeHead(status, {
    'Content-Type': type || 'text/plain; charset=utf-8',
    'Content-Length': bytes.length,
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff'
  });
  response.end(request.method === 'HEAD' ? undefined : bytes);
}

function json(request, response, status, value) {
  send(request, response, status, JSON.stringify(value), 'application/json; charset=utf-8');
}

function control(request, response) {
  if (request.headers.origin !== undefined && request.headers.origin !== ORIGIN) {
    send(request, response, 403, 'Origin rejected.');
    return;
  }
  if (request.headers['sec-fetch-site'] === 'cross-site') {
    send(request, response, 403, 'Cross-site access rejected.');
    return;
  }
  if (request.method === 'GET' || request.method === 'HEAD') {
    json(request, response, 200, {version});
    return;
  }
  if (request.method !== 'POST') {
    send(request, response, 405, 'Method not allowed.');
    return;
  }
  if (!/^application\/json(?:\s*;\s*charset=utf-8)?$/i.test(request.headers['content-type'] || '')) {
    send(request, response, 415, 'Use application/json.');
    request.resume();
    return;
  }
  let size = 0;
  let rejected = false;
  const chunks = [];
  request.on('data', chunk => {
    size += chunk.length;
    if (size > 64) {
      if (!rejected) send(request, response, 413, 'Body too large.');
      rejected = true;
      return;
    }
    chunks.push(chunk);
  });
  request.on('end', () => {
    if (rejected) return;
    let value;
    try {
      value = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    } catch {
      send(request, response, 400, 'Invalid JSON.');
      return;
    }
    if (!value || Array.isArray(value) || Object.keys(value).length !== 1 ||
        !Object.prototype.hasOwnProperty.call(value, 'version') ||
        (value.version !== 1 && value.version !== 2)) {
      send(request, response, 400, 'Expected exactly {"version":1} or {"version":2}.');
      return;
    }
    version = value.version;
    json(request, response, 200, {version});
  });
  request.on('error', () => {
    if (!response.headersSent) send(request, response, 400, 'Request failed.');
  });
}

const server = http.createServer((request, response) => {
  // Reject absolute-form proxy requests as well as unrecognized Host headers.
  if (request.headers.host !== HOST + ':' + PORT ||
      !request.url || !request.url.startsWith('/') || request.url.startsWith('//')) {
    send(request, response, 403, 'Host or request target rejected.');
    return;
  }
  let pathname;
  try {
    pathname = decodeURIComponent(new URL(request.url, ORIGIN).pathname);
  } catch {
    send(request, response, 400, 'Invalid path.');
    return;
  }
  if (pathname === '/__pwa_qa__/version') {
    control(request, response);
    return;
  }
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    send(request, response, 405, 'Method not allowed.');
    return;
  }
  if (pathname === '/sw.js') {
    send(request, response, 200, variants[version], MIME['.js']);
    return;
  }
  if (pathname.startsWith('/__pwa_qa__/') ||
      pathname.includes('\0') || pathname.includes('\\') ||
      pathname.split('/').some(segment => segment.startsWith('.'))) {
    send(request, response, 404, 'Not found.');
    return;
  }
  try {
    let target = path.resolve(OUT, '.' + pathname);
    if (target !== OUT && !target.startsWith(OUT + path.sep)) {
      send(request, response, 403, 'Path rejected.');
      return;
    }
    if (fs.statSync(target).isDirectory()) target = path.join(target, 'index.html');
    const resolved = fs.realpathSync(target);
    if (!resolved.startsWith(OUT + path.sep) || !fs.statSync(resolved).isFile()) {
      send(request, response, 403, 'Path rejected.');
      return;
    }
    send(request, response, 200, fs.readFileSync(resolved),
      MIME[path.extname(resolved).toLowerCase()] || 'application/octet-stream');
  } catch {
    send(request, response, 404, 'Not found.');
  }
});

// Chromium may use this same loopback endpoint as a deny-all outbound proxy.
// Same-origin traffic bypasses the proxy; remote HTTPS tunnels are never opened.
server.on('connect', (_request, socket) => {
  socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n');
});
server.on('upgrade', (_request, socket) => {
  socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n');
});
server.on('clientError', (_error, socket) => {
  socket.end('HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n');
});
server.requestTimeout = 5000;
server.headersTimeout = 5000;
server.listen(PORT, HOST, () => {
  process.stdout.write('PWA validation server listening at ' + ORIGIN + '\n');
});
