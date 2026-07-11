'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');

const root = process.env.BYRDHOUSE_ROOT || 'E:\\ByrdHouse';
const port = Number(process.env.BYRDHOUSE_PORT || 8787);
const statusPath = path.join(root, 'status.json');

function json(res, code, value) {
  const body = JSON.stringify(value, null, 2);
  res.writeHead(code, { 'content-type': 'application/json; charset=utf-8', 'content-length': Buffer.byteLength(body) });
  res.end(body);
}

function readStatus() {
  try { return JSON.parse(fs.readFileSync(statusPath, 'utf8').replace(/^\uFEFF/, '')); }
  catch (error) { return { overall: 'yellow', role: 'BYRD-GAMING', detail: 'status.json not available yet' }; }
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  if (req.method === 'GET' && url.pathname === '/health') {
    return json(res, 200, { ok: true, service: 'byrdhouse-router', host: process.env.COMPUTERNAME || 'byrd-gaming', odysseus: false });
  }
  if (req.method === 'GET' && url.pathname === '/status') return json(res, 200, readStatus());
  if (req.method === 'GET' && url.pathname === '/') {
    const status = readStatus();
    const body = `<!doctype html><html><meta name="viewport" content="width=device-width,initial-scale=1"><title>ByrdHouse</title><style>body{margin:0;background:#0b1017;color:#edf2f7;font:16px system-ui}.wrap{max-width:900px;margin:60px auto;padding:24px}.brand{color:#f0b94b}.card{background:#151d28;border:1px solid #2b3746;border-radius:14px;padding:24px;margin-top:24px}.state{font-size:44px;text-transform:uppercase;color:${status.overall === 'green' ? '#55d6be' : '#f0b94b'}}code{color:#9fb0c4}</style><div class="wrap"><h1><span class="brand">Byrd</span>House</h1><p>BYRD-GAMING direct command surface</p><div class="card"><div class="state">${status.overall || 'yellow'}</div><p>Router online. Odysseus disabled.</p><code>GET /health &nbsp; GET /status</code></div></div></html>`;
    res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' }); return res.end(body);
  }
  return json(res, 404, { error: 'not_found' });
});

server.listen(port, '0.0.0.0', () => console.log(`ByrdHouse router listening on http://0.0.0.0:${port}`));

