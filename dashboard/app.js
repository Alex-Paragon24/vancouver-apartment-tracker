const SHEET_ID = '1BcxczxXsZZ4dMaPEgBmRekdFCLiObSkp1kGaUXF_UB8';
const SHEET_URL = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv`;
const BACCHUS = [49.2793, -123.1234]; // Bacchus Restaurant, 845 Hornby St

// ── Map setup ──────────────────────────────────────────────────────────────
const map = L.map('map').setView([49.283, -123.121], 14);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© OpenStreetMap contributors',
  maxZoom: 19,
}).addTo(map);

// Bacchus marker (work target)
L.marker(BACCHUS, {
  icon: L.divIcon({
    className: '',
    html: '<div style="background:#1a2b4a;color:#fff;padding:4px 8px;border-radius:8px;font-size:11px;font-weight:600;white-space:nowrap;box-shadow:0 2px 6px rgba(0,0,0,.3)">🍷 Bacchus</div>',
    iconAnchor: [40, 10],
  }),
}).addTo(map);

// ── Geo cache ──────────────────────────────────────────────────────────────
const geoCache = JSON.parse(localStorage.getItem('geoCache') || '{}');
const saveGeoCache = () => localStorage.setItem('geoCache', JSON.stringify(geoCache));

const delay = ms => new Promise(r => setTimeout(r, ms));

async function geocode(address) {
  if (!address) return null;

  // Already lat,lon
  const ll = address.match(/^(-?\d+\.\d+),\s*(-?\d+\.\d+)$/);
  if (ll) return [parseFloat(ll[1]), parseFloat(ll[2])];

  const key = address.toLowerCase().trim();
  if (geoCache[key]) return geoCache[key];

  try {
    await delay(1100); // Nominatim rate limit: 1 req/s
    const resp = await fetch(
      `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(address + ', Vancouver, BC')}&format=json&limit=1`,
      { headers: { 'Accept-Language': 'en-CA' } }
    );
    const data = await resp.json();
    if (data.length) {
      const coords = [parseFloat(data[0].lat), parseFloat(data[0].lon)];
      geoCache[key] = coords;
      saveGeoCache();
      return coords;
    }
  } catch (_) {}
  return null;
}

// ── CSV parser ─────────────────────────────────────────────────────────────
function parseCSV(text) {
  const rows = [];
  let cur = '', inQ = false, row = [];
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQ) {
      if (c === '"' && text[i + 1] === '"') { cur += '"'; i++; }
      else if (c === '"') inQ = false;
      else cur += c;
    } else if (c === '"') {
      inQ = true;
    } else if (c === ',') {
      row.push(cur); cur = '';
    } else if (c === '\n') {
      row.push(cur); rows.push(row); row = []; cur = '';
    } else if (c !== '\r') {
      cur += c;
    }
  }
  if (cur || row.length) { row.push(cur); rows.push(row); }
  return rows;
}

// ── Data parsing ───────────────────────────────────────────────────────────
// Columns: A=Date Found, B=Price, C=Address, D=Neighborhood,
//          E=Walking Time, F=Posted, G=Bedrooms, H=Available From,
//          I=Link, J=Status, K=Draft ID
function rowToListing(row, idx) {
  const g = i => (row[i] || '').trim();
  const price = parseFloat(g(1).replace(/[^0-9.]/g, '')) || null;
  const bedrooms = parseInt(g(6)) || null;
  const link = g(8);
  const source = link.includes('kijiji') ? 'kijiji' : 'craigslist';
  return {
    _idx: idx,
    dateFound: g(0),
    price,
    address: g(2),
    neighborhood: g(3),
    walkTime: g(4),
    posted: g(5),
    bedrooms,
    availableFrom: g(7),
    link,
    status: g(9) || 'New',
    source,
  };
}

function priceColor(price) {
  if (!price) return 'orange';
  if (price <= 2500) return 'green';
  if (price <= 3000) return 'orange';
  return 'red';
}

function markerColor(price) {
  if (!price) return '#FF9800';
  if (price <= 2500) return '#2e7d32';
  if (price <= 3000) return '#e65100';
  return '#b71c1c';
}

function circleIcon(color) {
  return L.divIcon({
    className: '',
    html: `<div style="width:14px;height:14px;background:${color};border:2.5px solid #fff;border-radius:50%;box-shadow:0 1px 4px rgba(0,0,0,.35)"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

// ── State ──────────────────────────────────────────────────────────────────
let allListings = [];
let markers = {};
let activeId = null;
let filters = { br: 'all', status: 'all', maxPrice: 3500 };

// ── Render ─────────────────────────────────────────────────────────────────
function filtered() {
  return allListings.filter(l => {
    if (filters.br !== 'all' && l.bedrooms !== parseInt(filters.br)) return false;
    if (filters.status !== 'all' && l.status !== filters.status) return false;
    if (l.price && l.price > filters.maxPrice) return false;
    return true;
  });
}

function render() {
  const list = filtered();
  document.getElementById('count').textContent =
    `${list.length} listing${list.length !== 1 ? 's' : ''}`;

  // Show/hide map markers
  Object.entries(markers).forEach(([id, m]) => {
    const visible = list.some(l => l._idx === parseInt(id));
    if (visible) m.addTo(map); else map.removeLayer(m);
  });

  // Cards
  const container = document.getElementById('listings');
  const empty = document.getElementById('empty');
  container.innerHTML = '';

  if (list.length === 0) {
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');

  list.forEach(l => {
    const card = document.createElement('div');
    card.className = 'card' + (activeId === l._idx ? ' active' : '');
    card.dataset.id = l._idx;

    const priceStr = l.price ? `$${l.price.toLocaleString()}` : 'N/A';
    const brStr = l.bedrooms ? `${l.bedrooms}BR` : '';
    const walkStr = l.walkTime ? `🚶 ${l.walkTime}` : '';
    const postedStr = l.posted ? `🕐 ${l.posted}` : '';
    const availStr = l.availableFrom ? `📅 ${l.availableFrom}` : '';

    const sourceClass = `source-${l.source}`;
    const sourceLabel = l.source === 'kijiji' ? 'Kijiji' : 'CL';

    card.innerHTML = `
      <div class="card-top">
        <span class="price ${priceColor(l.price)}">${priceStr}/mo</span>
        <div class="badges">
          <span class="source-tag ${sourceClass}">${sourceLabel}</span>
          <span class="status-badge status-${l.status}">${l.status}</span>
        </div>
      </div>
      <div class="card-address" title="${l.address}">${l.address || l.neighborhood || 'Vancouver'}</div>
      <div class="card-meta">
        ${brStr ? `<span>🛏 ${brStr}</span>` : ''}
        ${walkStr ? `<span>${walkStr}</span>` : ''}
        ${postedStr ? `<span>${postedStr}</span>` : ''}
        ${availStr ? `<span>${availStr}</span>` : ''}
      </div>
      <div class="card-actions">
        <a class="btn btn-primary" href="${l.link}" target="_blank">View listing</a>
        <a class="btn btn-green" href="https://mail.google.com/mail/u/0/#drafts" target="_blank">Gmail drafts</a>
      </div>
    `;

    card.addEventListener('click', e => {
      if (e.target.tagName === 'A') return;
      setActive(l._idx);
    });

    container.appendChild(card);
  });
}

function setActive(id) {
  activeId = id;
  render();
  const m = markers[id];
  if (m) { map.setView(m.getLatLng(), 16); m.openPopup(); }
  const card = document.querySelector(`.card[data-id="${id}"]`);
  if (card) card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── Add marker ─────────────────────────────────────────────────────────────
function addMarker(listing, coords) {
  const color = markerColor(listing.price);
  const m = L.marker(coords, { icon: circleIcon(color) });

  const priceStr = listing.price ? `$${listing.price.toLocaleString()}` : 'N/A';
  const brStr = listing.bedrooms ? `${listing.bedrooms}BR · ` : '';

  m.bindPopup(`
    <div class="popup-price ${priceColor(listing.price)}">${priceStr}/mo</div>
    <div class="popup-addr">${listing.address || listing.neighborhood || ''}</div>
    <div class="popup-meta">${brStr}${listing.walkTime || ''}</div>
    <a class="popup-link" href="${listing.link}" target="_blank">View listing →</a>
  `);

  m.on('click', () => setActive(listing._idx));
  markers[listing._idx] = m;
  if (filtered().some(l => l._idx === listing._idx)) m.addTo(map);
}

// ── Load data ──────────────────────────────────────────────────────────────
async function load() {
  document.getElementById('count').textContent = 'Loading…';
  try {
    const resp = await fetch(SHEET_URL + '&t=' + Date.now());
    const text = await resp.text();
    const rows = parseCSV(text).slice(1); // skip header

    // Clear old markers
    Object.values(markers).forEach(m => map.removeLayer(m));
    markers = {};

    allListings = rows
      .filter(r => r.length > 8 && r[8])
      .map((r, i) => rowToListing(r, i));

    render();

    // Geocode lazily
    for (const l of allListings) {
      if (markers[l._idx]) continue;
      const coords = await geocode(l.address);
      if (coords) addMarker(l, coords);
    }
  } catch (err) {
    document.getElementById('count').textContent = 'Error loading data';
    console.error(err);
  }
}

// ── Filter events ──────────────────────────────────────────────────────────
document.querySelectorAll('[data-br]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('[data-br]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    filters.br = btn.dataset.br;
    render();
  });
});

document.querySelectorAll('[data-status]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('[data-status]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    filters.status = btn.dataset.status;
    render();
  });
});

const slider = document.getElementById('price-slider');
slider.addEventListener('input', () => {
  filters.maxPrice = parseInt(slider.value);
  document.getElementById('price-val').textContent = `$${parseInt(slider.value).toLocaleString()}`;
  render();
});

document.getElementById('refresh-btn').addEventListener('click', load);

// ── Init ───────────────────────────────────────────────────────────────────
load();
