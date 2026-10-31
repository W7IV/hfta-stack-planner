/* HFTA Stack Planner site-location picker.
 * Slippy-map math and user-click navigation are original code (MIT, W7IV 2026).
 * Tiles: OpenStreetMap, requested on demand only for the visible viewport.
 * No third-party script or automatic geolocation.
 */
(function () {
  "use strict";
  const TILE = 256, MAX_LAT = 85.05112878, MIN_Z = 2, MAX_Z = 19;
  const clampLat = lat => Math.max(-MAX_LAT, Math.min(MAX_LAT, lat));
  const normLon = lon => ((lon + 180) % 360 + 360) % 360 - 180;
  function world(lat, lon, zoom) {
    const size = TILE * 2 ** zoom, rad = clampLat(lat) * Math.PI / 180;
    return {
      x: (normLon(lon) + 180) / 360 * size,
      y: (1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2 * size
    };
  }
  function position(x, y, zoom) {
    const size = TILE * 2 ** zoom, yy = Math.max(0, Math.min(size, y));
    return {
      lat: Math.atan(Math.sinh(Math.PI * (1 - 2 * yy / size))) * 180 / Math.PI,
      lon: normLon(x / size * 360 - 180)
    };
  }
  function create(node, options = {}) {
    const hasPosition = Number.isFinite(options.lat) && Number.isFinite(options.lon);
    let center = { lat: hasPosition ? options.lat : 39.5, lon: hasPosition ? options.lon : -98.35 };
    let selected = hasPosition ? { ...center } : null;
    let zoom = Math.max(MIN_Z, Math.min(MAX_Z, Number(options.zoom) || (hasPosition ? 16 : 4)));
    let drag = null, wheelAt = 0;
    node.classList.add("site-map");
    node.innerHTML = '<div class="site-map-tiles"></div><div class="site-map-pin" hidden aria-hidden="true"></div>' +
      '<div class="site-map-zoom"><button type="button" data-zoom="in" title="Zoom in" aria-label="Zoom in">+</button>' +
      '<button type="button" data-zoom="out" title="Zoom out" aria-label="Zoom out">−</button></div>' +
      '<div class="site-map-credit">© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a></div>';
    const tiles = node.querySelector(".site-map-tiles");
    const pin = node.querySelector(".site-map-pin");
    const marker = () => {
      if (!selected) { pin.hidden = true; return; }
      const bounds = node.getBoundingClientRect(), c = world(center.lat, center.lon, zoom),
        s = world(selected.lat, selected.lon, zoom), period = TILE * 2 ** zoom;
      let dx = s.x - c.x;
      if (dx > period / 2) dx -= period;
      if (dx < -period / 2) dx += period;
      const x = bounds.width / 2 + dx, y = bounds.height / 2 + s.y - c.y;
      pin.hidden = x < 0 || x > bounds.width || y < 0 || y > bounds.height;
      pin.style.left = x + "px"; pin.style.top = y + "px";
    };
    function draw() {
      const rect = node.getBoundingClientRect(), w = rect.width, h = rect.height;
      if (!w || !h) return;
      const c = world(center.lat, center.lon, zoom), n = 2 ** zoom;
      const left = c.x - w / 2, top = c.y - h / 2, right = left + w, bottom = top + h;
      const old = new Map([...tiles.children].map(img => [img.dataset.key, img]));
      const fragment = document.createDocumentFragment();
      for (let ty = Math.floor(top / TILE); ty <= Math.floor((bottom - 1) / TILE); ty++) {
        if (ty < 0 || ty >= n) continue;
        for (let tx = Math.floor(left / TILE); tx <= Math.floor((right - 1) / TILE); tx++) {
          const wrappedX = ((tx % n) + n) % n, key = zoom + "/" + wrappedX + "/" + ty;
          let img = old.get(key);
          if (!img) {
            img = document.createElement("img");
            img.dataset.key = key; img.draggable = false; img.alt = "";
            img.referrerPolicy = "strict-origin-when-cross-origin";
            img.src = "https://tile.openstreetmap.org/" + key + ".png";
          }
          img.style.left = (tx * TILE - left) + "px";
          img.style.top = (ty * TILE - top) + "px";
          fragment.appendChild(img);
        }
      }
      tiles.replaceChildren(fragment);
      tiles.style.transform = "";
      marker();
    }
    function pick(lat, lon, recenter = false) {
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180)
        throw new Error("Enter latitude between -90 and 90 and longitude between -180 and 180.");
      selected = { lat, lon };
      if (recenter) center = { lat: clampLat(lat), lon: normLon(lon) };
      if (typeof options.onChange === "function") options.onChange({ ...selected });
      draw();
    }
    function setZoom(value) {
      const next = Math.max(MIN_Z, Math.min(MAX_Z, value));
      if (next !== zoom) { zoom = next; draw(); }
    }
    node.querySelector('[data-zoom="in"]').onclick = () => setZoom(zoom + 1);
    node.querySelector('[data-zoom="out"]').onclick = () => setZoom(zoom - 1);
    node.addEventListener("wheel", ev => {
      ev.preventDefault();
      const now = Date.now();
      if (now - wheelAt > 170) { setZoom(zoom + (ev.deltaY < 0 ? 1 : -1)); wheelAt = now; }
    }, { passive: false });
    node.addEventListener("pointerdown", ev => {
      if (ev.target.closest("button, a")) return;
      if (ev.button !== 0) return;
      drag = { id: ev.pointerId, x: ev.clientX, y: ev.clientY, dx: 0, dy: 0 };
      node.setPointerCapture(ev.pointerId);
    });
    node.addEventListener("pointermove", ev => {
      if (!drag || drag.id !== ev.pointerId) return;
      drag.dx = ev.clientX - drag.x; drag.dy = ev.clientY - drag.y;
      tiles.style.transform = "translate(" + drag.dx + "px," + drag.dy + "px)";
      pin.style.transform = "translate(" + drag.dx + "px," + drag.dy + "px)";
    });
    node.addEventListener("pointerup", ev => {
      if (!drag || drag.id !== ev.pointerId) return;
      const d = drag; drag = null;
      pin.style.transform = "";
      const centerWorld = world(center.lat, center.lon, zoom);
      if (Math.hypot(d.dx, d.dy) > 7) {
        center = position(centerWorld.x - d.dx, centerWorld.y - d.dy, zoom);
        draw();
      } else {
        const rect = node.getBoundingClientRect();
        const c = position(centerWorld.x + ev.clientX - rect.left - rect.width / 2,
          centerWorld.y + ev.clientY - rect.top - rect.height / 2, zoom);
        pick(c.lat, c.lon);
      }
    });
    node.addEventListener("pointercancel", () => { drag = null; tiles.style.transform = ""; pin.style.transform = ""; draw(); });
    if (typeof ResizeObserver !== "undefined") {
      const observer = new ResizeObserver(draw); observer.observe(node);
      node._pickerCleanup = () => observer.disconnect();
    }
    draw();
    return { getSelected: () => selected ? { ...selected } : null,
      setSelected: (lat, lon) => pick(lat, lon, true),
      setZoom, redraw: draw };
  }
  window.HFTASitePicker = { create, world, position, normLon };
})();
