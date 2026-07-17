// Live SLAM map viewer.
//
// Speaks the rosbridge v2 protocol directly over a WebSocket — no roslib /
// ros2djs dependency, so nothing needs to be vendored or fetched from a CDN
// (the robot may be offline). Subscribes read-only to /map (the rosbridge
// server on the robot restricts access to exactly that topic) and renders the
// nav_msgs/OccupancyGrid onto a <canvas>.
//
// Robot-pose overlay is a planned Phase 2 (needs a map-frame PoseStamped from
// the robot); this file intentionally only draws the map.
(function () {
  'use strict';

  const canvas = document.getElementById('map-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const statusEl = document.getElementById('rosbridge-status');

  // Default to the same host the page came from, port 9090. Override with a
  // data-ws-url attribute on the canvas if rosbridge lives elsewhere.
  const wsUrl = canvas.getAttribute('data-ws-url') ||
    ((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.hostname + ':9090');

  let ws = null;
  let reconnectDelay = 1000; // ms, exponential backoff up to 15 s

  function setStatus(text, cls) {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.className = 'state-badge ' + cls;
  }

  // Render a nav_msgs/OccupancyGrid. data[] is row-major with the origin at the
  // bottom-left and y pointing up; canvas y points down, so we flip vertically.
  // Cell values: -1 unknown, 0 free .. 100 occupied.
  function renderMap(grid) {
    const info = grid.info || {};
    const w = info.width | 0;
    const h = info.height | 0;
    const data = grid.data;
    if (!w || !h || !data || data.length < w * h) return;

    canvas.width = w;
    canvas.height = h;
    const img = ctx.createImageData(w, h);
    const out = img.data;

    for (let row = 0; row < h; row++) {
      const srcRow = h - 1 - row;      // flip Y: grid bottom-up -> canvas top-down
      const srcBase = srcRow * w;
      const dstBase = row * w;
      for (let col = 0; col < w; col++) {
        const v = data[srcBase + col];
        const di = (dstBase + col) * 4;
        let shade;
        if (v < 0) {
          shade = 48;                  // unknown: dark gray, blends with the card
        } else {
          shade = Math.round(230 - (v / 100) * 210); // free ~230 (light) .. occupied ~20 (dark)
        }
        out[di] = shade;
        out[di + 1] = shade;
        out[di + 2] = shade;
        out[di + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }

  function scheduleReconnect() {
    setTimeout(connect, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, 15000);
  }

  function connect() {
    setStatus('connecting…', 'state-initializing');
    try {
      ws = new WebSocket(wsUrl);
    } catch (e) {
      scheduleReconnect();
      return;
    }

    ws.onopen = function () {
      reconnectDelay = 1000;
      setStatus('connected', 'state-moving');
      // rosbridge subscribe op. throttle_rate caps the update rate; queue_length
      // 1 keeps only the newest map so we never fall behind.
      ws.send(JSON.stringify({
        op: 'subscribe',
        topic: '/map',
        type: 'nav_msgs/msg/OccupancyGrid',
        throttle_rate: 1000,
        queue_length: 1,
        compression: 'none'
      }));
    };

    ws.onmessage = function (ev) {
      let msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      if (msg.op === 'publish' && msg.topic === '/map' && msg.msg) {
        renderMap(msg.msg);
      }
    };

    ws.onclose = function () {
      setStatus('disconnected', 'state-emergency');
      scheduleReconnect();
    };

    ws.onerror = function () {
      // onclose fires next and handles reconnect; just make sure we close.
      try { ws.close(); } catch (e) { /* ignore */ }
    };
  }

  connect();
})();
