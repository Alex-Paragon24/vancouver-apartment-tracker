const SHEET_ID  = '1BcxczxXsZZ4dMaPEgBmRekdFCLiObSkp1kGaUXF_UB8';
const SHEET_URL = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv`;
const BACCHUS   = [49.27905, -123.12338]; // 845 Hornby St

// ── Map ────────────────────────────────────────────────────────────
const map = L.map('map').setView([49.283, -123.121], 14);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© OpenStreetMap contributors', maxZoom: 19,
}).addTo(map);

L.marker(BACCHUS, {
  icon: L.divIcon({
    className: '',
    html: '<div style="background:#1a2b4a;color:#fff;padding:4px 9px;border-radius:8px;font-size:11px;font-weight:700;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.4)">🍷 Bacchus</div>',
    iconAnchor: [44, 10],
  }),
}).addTo(map);

// ── Geocode ────────────────────────────────────────────────────────
const geoCache = JSON.parse(localStorage.getItem('geoCache') || '{}');
const saveGeo  = () => localStorage.setItem('geoCache', JSON.stringify(geoCache));
const delay    = ms => new Promise(r => setTimeout(r, ms));

async function geocode(address) {
  if (!address) return null;
  const ll = address.match(/^(-?\d+\.\d+),\s*(-?\d+\.\d+)$/);
  if (ll) return [parseFloat(ll[1]), parseFloat(ll[2])];
  const key = address.toLowerCase().trim();
  if (geoCache[key]) return geoCache[key];
  try {
    await delay(1100);
    const r = await fetch(
      `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(address + ', Vancouver, BC')}&format=json&limit=1`,
      { headers: { 'Accept-Language': 'en-CA' } }
    );
    const d = await r.json();
    if (d.length) {
      const c = [parseFloat(d[0].lat), parseFloat(d[0].lon)];
      geoCache[key] = c; saveGeo(); return c;
    }
  } catch (_) {}
  return null;
}

// ── CSV ────────────────────────────────────────────────────────────
function parseCSV(text) {
  const rows = []; let cur = '', inQ = false, row = [];
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQ) {
      if (c === '"' && text[i+1] === '"') { cur += '"'; i++; }
      else if (c === '"') inQ = false;
      else cur += c;
    } else if (c === '"') { inQ = true; }
    else if (c === ',')   { row.push(cur); cur = ''; }
    else if (c === '\n')  { row.push(cur); rows.push(row); row = []; cur = ''; }
    else if (c !== '\r')  { cur += c; }
  }
  if (row.length) { row.push(cur); rows.push(row); }
  return rows;
}

// ── Helpers ────────────────────────────────────────────────────────
const isLatLon = s => /^-?\d+\.\d+,\s*-?\d+\.\d+$/.test((s||'').trim());

function displayAddress(l) {
  if (!isLatLon(l.address) && l.address) return l.address;
  return l.neighborhood || 'Vancouver, BC';
}

function priceColor(p) {
  return !p ? 'orange' : p <= 2500 ? 'green' : p <= 3000 ? 'orange' : 'red';
}
function markerColor(p) {
  return !p ? '#FF9800' : p <= 2500 ? '#2e7d32' : p <= 3000 ? '#e65100' : '#b71c1c';
}
function circleIcon(color, big = false) {
  const s = big ? 18 : 13;
  return L.divIcon({
    className: '',
    html: `<div style="width:${s}px;height:${s}px;background:${color};border:2.5px solid #fff;border-radius:50%;box-shadow:0 1px 5px rgba(0,0,0,.4)"></div>`,
    iconSize: [s, s], iconAnchor: [s/2, s/2],
  });
}

// ── Data ───────────────────────────────────────────────────────────
function rowToListing(row, idx) {
  const g = i => (row[i] || '').trim();
  const price = parseFloat(g(1).replace(/[^0-9.]/g, '')) || null;
  const link  = g(8);
  return {
    _idx: idx, dateFound: g(0), price,
    address: g(2), neighborhood: g(3),
    walkTime: g(4), posted: g(5),
    bedrooms: parseInt(g(6)) || null,
    availableFrom: g(7), link,
    status: g(9) || 'New',
    source: link.includes('kijiji') ? 'kijiji' : 'craigslist',
  };
}

// ── State ──────────────────────────────────────────────────────────
let allListings = [], markers = {}, activeId = null;
let filters = { br: 'all', status: 'all', maxPrice: 3500 };

function filtered() {
  return allListings.filter(l => {
    if (filters.br !== 'all' && l.bedrooms !== parseInt(filters.br)) return false;
    if (filters.status !== 'all' && l.status !== filters.status) return false;
    if (l.price && l.price > filters.maxPrice) return false;
    return true;
  });
}

// ── Render ─────────────────────────────────────────────────────────
function render() {
  const list = filtered();
  document.getElementById('count').textContent =
    `${list.length} listing${list.length !== 1 ? 's' : ''}`;

  const visIds = new Set(list.map(l => l._idx));
  Object.entries(markers).forEach(([id, m]) => {
    const vis = visIds.has(parseInt(id));
    if (vis) m.addTo(map); else map.removeLayer(m);
    const l = allListings.find(x => x._idx === parseInt(id));
    if (l) m.setIcon(circleIcon(markerColor(l.price), activeId === l._idx));
  });

  const container = document.getElementById('listings');
  const empty     = document.getElementById('empty');
  container.innerHTML = '';
  if (!list.length) { empty.classList.remove('hidden'); return; }
  empty.classList.add('hidden');

  list.forEach(l => {
    const card = document.createElement('div');
    card.className = 'card' + (activeId === l._idx ? ' active' : '');
    card.dataset.id = l._idx;

    const priceStr = l.price ? `$${l.price.toLocaleString()}` : 'N/A';
    const addr     = displayAddress(l);
    const srcLabel = l.source === 'kijiji' ? 'Kijiji' : 'CL';

    const meta = [
      l.bedrooms      ? `🛏 ${l.bedrooms}BR`   : '',
      l.walkTime      ? `🚶 ${l.walkTime}`      : '',
      l.posted        ? `🕐 ${l.posted}`        : '',
      l.availableFrom ? `📅 ${l.availableFrom}` : '',
    ].filter(Boolean).join('  ·  ');

    card.innerHTML = `
      <div class="card-top">
        <span class="price ${priceColor(l.price)}">${priceStr}<span class="per-mo">/mo</span></span>
        <div class="badges">
          <span class="source-tag source-${l.source}">${srcLabel}</span>
          <span class="status-badge status-${l.status}">${l.status}</span>
        </div>
      </div>
      <div class="card-address" title="${addr}">${addr}</div>
      ${meta ? `<div class="card-meta">${meta}</div>` : ''}
      <div class="card-actions">
        <a class="btn btn-primary" href="${l.link}" target="_blank" rel="noopener">View listing ↗</a>
        <a class="btn btn-green"   href="https://mail.google.com/mail/u/0/#drafts" target="_blank" rel="noopener">✉ Drafts</a>
      </div>
    `;
    card.addEventListener('click', e => {
      if (e.target.closest('a')) return;
      setActive(l._idx);
    });
    container.appendChild(card);
  });
}

function setActive(id) {
  activeId = id;
  render();
  const m = markers[id];
  if (m) { map.setView(m.getLatLng(), 16, { animate: true }); m.openPopup(); }
  document.querySelector(`.card[data-id="${id}"]`)
    ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  if (window.innerWidth <= 700) switchTab('map');
}

function addMarker(l, coords) {
  const m = L.marker(coords, { icon: circleIcon(markerColor(l.price)) });
  const addr = displayAddress(l);
  const priceStr = l.price ? `$${l.price.toLocaleString()}` : 'N/A';
  m.bindPopup(`
    <div class="popup-price ${priceColor(l.price)}">${priceStr}/mo</div>
    <div class="popup-addr">${addr}</div>
    <div class="popup-meta">${l.bedrooms ? l.bedrooms + 'BR · ' : ''}${l.walkTime || ''}</div>
    <a class="popup-link" href="${l.link}" target="_blank" rel="noopener">View listing →</a>
  `);
  m.on('click', () => setActive(l._idx));
  markers[l._idx] = m;
  if (filtered().some(x => x._idx === l._idx)) m.addTo(map);
}

// ── Load ───────────────────────────────────────────────────────────
async function load() {
  document.getElementById('count').textContent = 'Loading…';
  try {
    const resp = await fetch(SHEET_URL + '&t=' + Date.now());
    const text = await resp.text();
    const rows = parseCSV(text).slice(1);
    Object.values(markers).forEach(m => map.removeLayer(m));
    markers = {};
    allListings = rows.filter(r => r.length > 8 && r[8]).map(rowToListing);
    render();
    for (const l of allListings) {
      if (markers[l._idx]) continue;
      const coords = await geocode(l.address);
      if (coords) addMarker(l, coords);
    }
  } catch (err) {
    document.getElementById('count').textContent = 'Error — check sheet is public';
    console.error(err);
  }
}

// ── Mobile tab ─────────────────────────────────────────────────────
const appContent = document.getElementById('app-content');

function switchTab(tab) {
  if (tab === 'map') {
    appContent.classList.add('show-map');
    setTimeout(() => map.invalidateSize(), 10);
  } else {
    appContent.classList.remove('show-map');
  }
  document.querySelectorAll('.tab-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.tab === tab)
  );
}

document.querySelectorAll('.tab-btn').forEach(btn =>
  btn.addEventListener('click', () => switchTab(btn.dataset.tab))
);

// ── Filter events ──────────────────────────────────────────────────
function setActiveButtons(attr, val) {
  document.querySelectorAll(`[${attr}]`).forEach(b =>
    b.classList.toggle('active', b.getAttribute(attr) === val)
  );
}

document.querySelectorAll('[data-br]').forEach(btn =>
  btn.addEventListener('click', () => {
    filters.br = btn.dataset.br;
    setActiveButtons('data-br', filters.br);
    render();
  })
);

document.querySelectorAll('[data-status]').forEach(btn =>
  btn.addEventListener('click', () => {
    filters.status = btn.dataset.status;
    setActiveButtons('data-status', filters.status);
    render();
  })
);

function syncPrice(val) {
  filters.maxPrice = parseInt(val);
  document.getElementById('price-val-d').textContent = `$${filters.maxPrice.toLocaleString()}`;
  document.getElementById('price-val-m').textContent = `$${filters.maxPrice.toLocaleString()}`;
  document.getElementById('price-slider-d').value = val;
  document.getElementById('price-slider-m').value = val;
  render();
}

document.getElementById('price-slider-d').addEventListener('input', e => syncPrice(e.target.value));
document.getElementById('price-slider-m').addEventListener('input', e => syncPrice(e.target.value));
document.getElementById('refresh-btn-d').addEventListener('click', load);
document.getElementById('refresh-btn-m').addEventListener('click', load);

document.getElementById('filter-toggle').addEventListener('click', () => {
  document.getElementById('mobile-drawer').classList.toggle('open');
});

// ── Init ───────────────────────────────────────────────────────────
load();
