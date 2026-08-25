// Kosong disengaja. Semua endpoint relatif terhadap origin penyaji
// halaman, supaya dev lokal tidak menulis ke Supabase produksi.
const API = '';  // relatif: ikut origin yang menyajikan halaman

// ── Sprint 1: Auth Session Management ──
// In-memory backup: survives cross-tab localStorage wipes (another tab's idle
// timer calling AUTH.clear()), so a 401-retry can still refresh mid-request.
let _memRefreshToken = null;

const AUTH = {
  TOKEN_KEY: 'prima_access_token',
  REFRESH_KEY: 'prima_refresh_token',
  USER_KEY: 'prima_user',

  save(loginResponse) {
    localStorage.setItem(this.TOKEN_KEY, loginResponse.access_token);
    if (loginResponse.refresh_token) {
      localStorage.setItem(this.REFRESH_KEY, loginResponse.refresh_token);
      _memRefreshToken = loginResponse.refresh_token;
    }
    localStorage.setItem(this.USER_KEY, JSON.stringify(loginResponse.user));
  },

  getToken() { return localStorage.getItem(this.TOKEN_KEY); },

  getUser() {
    try { return JSON.parse(localStorage.getItem(this.USER_KEY) || 'null'); }
    catch(e) { return null; }
  },

  clear() {
    _memRefreshToken = null;
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.REFRESH_KEY);
    localStorage.removeItem(this.USER_KEY);
  },

  isLoggedIn() { return !!this.getToken(); },

  headers() {
    const h = {'Content-Type': 'application/json'};
    const t = this.getToken();
    if (t) h['Authorization'] = 'Bearer ' + t;
    return h;
  },

  jsonHeaders() { return this.headers(); },

  // Headers tanpa Content-Type (untuk GET)
  authOnly() {
    const h = {};
    const t = this.getToken();
    if (t) h['Authorization'] = 'Bearer ' + t;
    return h;
  },
  async refreshToken() {
    // Fall back to the in-memory copy when localStorage was wiped externally
    const rt = localStorage.getItem(this.REFRESH_KEY) || _memRefreshToken;
    if (!rt) return false;
    try {
      const resp = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({refresh_token: rt})
      });
      if (!resp.ok) return false;
      const data = await resp.json();
      if (data.access_token) {
        localStorage.setItem(this.TOKEN_KEY, data.access_token);
        if (data.refresh_token) {
          localStorage.setItem(this.REFRESH_KEY, data.refresh_token);
          _memRefreshToken = data.refresh_token;
        }
        return true;
      }
      return false;
    } catch(e) { return false; }
  }
};

// Cross-tab awareness: another tab clearing auth fires a StorageEvent here.
// Try to recover with the in-memory refresh token instead of failing silently.
window.addEventListener('storage', (e) => {
  if (e.key === AUTH.TOKEN_KEY && e.newValue === null && _memRefreshToken) {
    console.log('[AUTH] Cross-tab auth clear detected, attempting recovery');
    AUTH.refreshToken().then((ok) => {
      if (!ok) console.log('[AUTH] Cross-tab recovery failed');
    }).catch(() => {
      console.log('[AUTH] Cross-tab recovery failed');
    });
  }
});

// --- Idle Timeout (60 menit) ---
let _lastActivity = Date.now();
let _lastRefreshCheck = Date.now();
const IDLE_TIMEOUT_MS = 60 * 60 * 1000;
const REFRESH_THRESHOLD_MS = 45 * 60 * 1000;

function _onUserActivity() {
  _lastActivity = Date.now();
}
['mousemove','keydown','click','scroll','touchstart'].forEach(evt => {
  document.addEventListener(evt, _onUserActivity, {passive: true, capture: true});
});

setInterval(async () => {
  if (!AUTH.isLoggedIn()) return;
  const idle = Date.now() - _lastActivity;
  if (idle > IDLE_TIMEOUT_MS) {
    // Try a refresh first: user may be active in another tab with a valid session
    const stillValid = await AUTH.refreshToken();
    if (stillValid) {
      _lastActivity = Date.now();
      _lastRefreshCheck = Date.now();
      return;
    }
    AUTH.clear();
    showLogin();
    alert('Sesi berakhir karena tidak aktif selama 60 menit.');
    return;
  }
  const sinceRefresh = Date.now() - _lastRefreshCheck;
  if (sinceRefresh > REFRESH_THRESHOLD_MS) {
    const ok = await AUTH.refreshToken();
    if (ok) _lastRefreshCheck = Date.now();
  }
}, 60000);

// ---------------------------------------------------------------------------
// Kustodian Page
// ---------------------------------------------------------------------------
let _kustodianData = [];
let _editKustodianId = null;

async function loadKustodian() {
  const tbody = document.getElementById('kustodian-tbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr class="loading-row"><td colspan="5">Memuat data kustodian...</td></tr>';
  try {
    const resp = await apiFetch(API + '/api/kustodian');
    if (!resp.ok) { tbody.innerHTML = '<tr><td colspan="5">Gagal memuat data</td></tr>'; return; }
    _kustodianData = await resp.json();
    if (_kustodianData.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--txt4)">Belum ada data kustodian</td></tr>';
      return;
    }
    tbody.innerHTML = _kustodianData.map(k => `
      <tr style="cursor:pointer" onclick="showKustodianDetail('${k.id}')">
        <td><span style="font-family:'JetBrains Mono',monospace;font-size:12px">${escapeHtml(k.id)}</span></td>
        <td>${escapeHtml(k.nama)}</td>
        <td>${(k.pakd_ids||[]).length} PAKD</td>
        <td>${(k.wallets||[]).length}</td>
        <td style="text-align:right">
          <button onclick="event.stopPropagation();editKustodian('${k.id}')"
              style="background:none;border:none;cursor:pointer;font-size:14px;padding:4px"
              title="Edit Kustodian" class="crud-action">✏️</button>
          <button onclick="event.stopPropagation();deleteKustodian('${k.id}','${k.nama}')"
              style="background:none;border:none;cursor:pointer;font-size:14px;padding:4px"
              title="Hapus Kustodian" class="crud-action">🗑️</button>
        </td>
      </tr>
    `).join('');
    applyRoleUI();
  } catch (e) {
    tbody.innerHTML = '<tr><td colspan="5">Error: ' + escapeHtml(e.message) + '</td></tr>';
  }
}

function showKustodianDetail(id) {
  renderKustodianMonitoring(id);
}

// --- Sprint 4: Kustodian Monitoring Dashboard ---
let _kustMonitoringData = null;

function kustDeviationColor(pct) {
  if (pct >= -10 && pct <= 50) return 'var(--green)';
  if ((pct >= -20 && pct < -10) || (pct > 50 && pct <= 100)) return 'var(--amber)';
  return 'var(--red)';
}

function kustDeviationCardClass(pct) {
  if (pct >= -10 && pct <= 50) return 'kpi-card green';
  if ((pct >= -20 && pct < -10) || (pct > 50 && pct <= 100)) return 'kpi-card amber';
  return 'kpi-card red';
}

function _populateKustodianSelector(selectedId) {
  const sel = document.getElementById('kustodian-selector');
  if (!sel) return;
  const user = AUTH.getUser();
  const canSelect = user && (user.role === 'super_admin' || user.role === 'pengawas');
  if (!canSelect || _kustodianData.length < 2) { sel.style.display = 'none'; return; }
  sel.innerHTML = _kustodianData.map(k =>
    `<option value="${k.id}" ${k.id === selectedId ? 'selected' : ''}>${escapeHtml(k.nama)} (${escapeHtml(k.id)})</option>`
  ).join('');
  sel.style.display = '';
}

async function renderKustodianMonitoring(kustId) {
  const detail = document.getElementById('kustodian-detail');
  detail.style.display = 'block';
  document.getElementById('kustodian-detail-nama').textContent = kustId;
  _populateKustodianSelector(kustId);
  const ctbody = document.getElementById('kust-compliance-tbody');
  ctbody.innerHTML = '<tr class="loading-row"><td colspan="5">Memuat data monitoring...</td></tr>';
  try {
    const resp = await apiFetch(API + '/api/kustodian/' + kustId + '/monitoring');
    if (!resp.ok) {
      ctbody.innerHTML = '<tr><td colspan="5" style="color:var(--red)">Gagal memuat data monitoring (' + resp.status + ')</td></tr>';
      return;
    }
    const data = await resp.json();
    _kustMonitoringData = data;
    const s = data.summary;

    document.getElementById('kustodian-detail-nama').textContent = data.kustodian.nama + ' (' + data.kustodian.id + ')';
    document.getElementById('kust-kpi-onchain').textContent = formatIDR(s.total_onchain_idr || 0);
    document.getElementById('kust-kpi-expected').textContent = formatIDR(s.total_expected_at_ptp_idr || 0);
    const devEl = document.getElementById('kust-kpi-deviasi');
    const dev = s.deviation_pct || 0;
    devEl.textContent = (dev > 0 ? '+' : '') + dev.toFixed(2) + '%';
    devEl.style.color = kustDeviationColor(dev);
    document.getElementById('kust-kpi-dev-card').className = kustDeviationCardClass(dev);
    document.getElementById('kust-kpi-wallet').textContent =
      s.wallet_verified_count + ' / ' + s.wallet_total_count + ' (' + s.verification_rate_pct + '%)';

    // Tabel Status Penempatan AKD per PAKD (POJK 23/2025 Pasal 91)
    const cmpCell = (reported, onchain, onchainLabel, status) => {
      const rep = reported || 0;
      // D34/D35: status hanya dilewatkan untuk kolom kustodian. Kolom
      // tanpa status (PAKD on-chain) tidak berubah sama sekali.
      const takTerukur = status !== undefined && status !== 'terukur';
      if (takTerukur) {
        return `<td class="mono-val">
        <div><span style="font-size:9px;color:var(--txt4);font-weight:600;text-transform:uppercase">Dilaporkan</span><br>${formatIDR(rep)}</div>
        <div style="margin-top:4px;color:var(--txt4)"><span style="font-size:9px;color:var(--txt4);font-weight:600;text-transform:uppercase">${onchainLabel}</span><br>—</div>
      </td>`;
      }
      const oc = onchain || 0;
      // Red only on negative deviation (on-chain below what was reported)
      const ocColor = oc < rep ? 'var(--red)' : 'var(--txt2)';
      return `<td class="mono-val">
        <div><span style="font-size:9px;color:var(--txt4);font-weight:600;text-transform:uppercase">Dilaporkan</span><br>${formatIDR(rep)}</div>
        <div style="margin-top:4px;color:${ocColor}"><span style="font-size:9px;color:var(--txt4);font-weight:600;text-transform:uppercase">${onchainLabel}</span><br>${formatIDR(oc)}</div>
      </td>`;
    };
    ctbody.innerHTML = (data.pakd_compliance || []).map(p => {
      // D33: baris tanpa snapshot bukan pelanggar. Ia tidak mendapat merah
      // maupun hijau, dan rasionya tidak ditampilkan sebagai angka -- 0.0%
      // hijau pada baris tanpa data adalah kebohongan.
      const belumDirekonsiliasi = p.verdict_status === 'BELUM_DIREKONSILIASI';
      const selRasio = belumDirekonsiliasi
        ? '<td class="mono-val" style="color:var(--txt4)">—</td>'
        : `<td class="mono-val" style="color:${p.ratio_at_pakd > 0.3 ? 'var(--red)' : 'var(--green)'};font-weight:600">${((p.ratio_at_pakd || 0) * 100).toFixed(1)}%</td>`;
      // D16: penanda DECLARED. Rasio dihitung dari nilai terlapor, tanpa
      // satu pun angka on-chain.
      const penandaDeclared = p.ratio_provenance === 'declared'
        ? '<div style="font-size:9px;color:var(--txt4);font-weight:600;margin-top:3px" title="Rasio berasal dari laporan mandiri PAKD dan belum diverifikasi on-chain">DECLARED</div>'
        : '';
      const selVerdict = belumDirekonsiliasi
        ? '<td><span style="color:var(--txt4);font-size:10px;font-weight:600;text-transform:uppercase">BELUM DIREKONSILIASI</span></td>'
        : `<td>${p.verdict_status === 'COMPLIANT' ? '<span class="badge-compliant">✓ COMPLIANT</span>' : '<span class="badge-violation">✗ VIOLATION</span>'}${penandaDeclared}</td>`;
      return `
      <tr>
        <td>${escapeHtml(p.nama)}<div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--txt4)">${escapeHtml(p.pakd_id)}</div><div style="font-size:9px;color:var(--txt4);margin-top:2px" title="Waktu snapshot rekonsiliasi terakhir">snapshot: ${p.latest_snapshot_at ? p.latest_snapshot_at.replace('T', ' ').slice(0, 16) : '—'}</div></td>
        ${cmpCell(p.customer_at_pakd_idr, p.pakd_onchain_idr, 'on-chain PAKD')}
        ${cmpCell(p.customer_at_ptp_idr, p.kustodian_onchain_idr, 'on-chain kustodian (dedicated)', p.kustodian_onchain_status)}
        ${selRasio}
        ${selVerdict}
      </tr>
    `;
    }).join('') || '<tr><td colspan="5" style="color:var(--txt4)">Tidak ada PAKD terhubung</td></tr>';

    drawKustodianDonut(data.pakd_compliance || []);
    drawKustodianBubbleMap(data);

    // Tabel wallet dengan aksi edit/hapus (super_admin)
    const wtbody = document.getElementById('kustodian-detail-wallets');
    wtbody.innerHTML = (data.wallets || []).map((w, i) => `
      <tr>
        <td><span style="font-size:11px;background:var(--bg2);padding:2px 8px;border-radius:4px;font-weight:600;text-transform:uppercase">${w.network}</span></td>
        <td style="font-family:'JetBrains Mono',monospace;font-size:11px;word-break:break-all">${escapeHtml(w.address)}</td>
        <td>${w.pakd_id
          ? '<span style="font-family:\'JetBrains Mono\',monospace;font-size:11px">' + escapeHtml(w.pakd_id) + '</span>'
          : '<span style="color:var(--amber);font-size:11px">Unassigned</span>'}
          <button onclick="assignKustWallet(${i})" class="crud-action" title="Tetapkan PAKD"
              style="background:none;border:none;cursor:pointer;font-size:12px;padding:2px">🔗</button></td>
        <td>${w.verified ? '<span style="color:var(--green);font-weight:600">✓ Verified</span>' : '<span style="color:var(--txt4)">Unverified</span>'}</td>
        <td style="text-align:right">
          <button onclick="editKustWallet(${i})" class="crud-action" title="Ganti address"
              style="background:none;border:none;cursor:pointer;font-size:14px;padding:4px">✏️</button>
          <button onclick="removeKustWallet(${i})" class="crud-action" title="Hapus wallet"
              style="background:none;border:none;cursor:pointer;font-size:14px;padding:4px">🗑️</button>
        </td>
      </tr>
    `).join('') || '<tr><td colspan="5" style="color:var(--txt4)">Tidak ada wallet</td></tr>';
    applyRoleUI();
  } catch (e) {
    console.error('[KUSTODIAN] monitoring render failed:', e);
    ctbody.innerHTML = '<tr><td colspan="5" style="color:var(--red)">Error: ' + escapeHtml(e.message) + '</td></tr>';
  }
}

function custodyDistribution(pakdCompliance) {
  // Distribusi custody ON-CHAIN per PAKD (porsi PAKD), fallback ke nilai
  // dilaporkan bila belum ada saldo on-chain.
  let valueOf = p => p.kustodian_onchain_idr || 0;
  let centerLabel = 'Under Custody', note = '';
  // D34/D35: baris berstatus bukan "terukur" DIKELUARKAN dari total,
  // bukan dihitung nol -- totalnya tidak boleh bergantung pada jaminan
  // bahwa kunci numerik baris itu sudah None dari backend.
  const terukur = pakdCompliance.filter(p => p.kustodian_onchain_status === 'terukur');
  let total = terukur.reduce((sum, p) => sum + valueOf(p), 0);
  if (total === 0) {
    valueOf = p => p.customer_at_ptp_idr || 0;
    centerLabel = 'Total di PTP';
    note = '<div style="font-size:10px;color:var(--amber);margin-top:6px;text-align:center">Estimasi dari laporan — saldo on-chain kustodian masih 0</div>';
    total = pakdCompliance.reduce((sum, p) => sum + valueOf(p), 0);
  }
  return {valueOf, centerLabel, note, total};
}

function drawKustodianDonut(pakdCompliance) {
  const wrap = document.getElementById('kust-donut-wrap');
  if (!wrap) return;
  const {valueOf, centerLabel, note, total} = custodyDistribution(pakdCompliance);
  if (total === 0) {
    wrap.innerHTML = '<div class="no-data-state">Tidak ada data penempatan</div>';
    return;
  }
  const colors = ['#4a6cf7', '#f59e0b', '#ef4444', '#10b981', '#8b5cf6'];
  const sz = 170, cx = sz / 2, cy = sz / 2, r = 70, ri = 44;
  const seg = (start, sweep, color) => {
    const end = start + Math.min(sweep, 2 * Math.PI - 0.0001);
    const x1 = cx + r * Math.cos(start), y1 = cy + r * Math.sin(start);
    const x2 = cx + r * Math.cos(end), y2 = cy + r * Math.sin(end);
    const xi1 = cx + ri * Math.cos(start), yi1 = cy + ri * Math.sin(start);
    const xi2 = cx + ri * Math.cos(end), yi2 = cy + ri * Math.sin(end);
    const lg = sweep > Math.PI ? 1 : 0;
    return '<path d="M' + xi1 + ' ' + yi1 + ' L' + x1 + ' ' + y1 + ' A' + r + ' ' + r + ' 0 ' + lg + ' 1 ' + x2 + ' ' + y2 +
           ' L' + xi2 + ' ' + yi2 + ' A' + ri + ' ' + ri + ' 0 ' + lg + ' 0 ' + xi1 + ' ' + yi1 + ' Z" fill="' + color + '" opacity="0.85"/>';
  };
  let svg = '<svg width="' + sz + '" height="' + sz + '" viewBox="0 0 ' + sz + ' ' + sz + '">';
  let angle = -Math.PI / 2;
  pakdCompliance.forEach((p, i) => {
    const sweep = (valueOf(p) / total) * 2 * Math.PI;
    if (sweep > 0) svg += seg(angle, sweep, colors[i % colors.length]);
    angle += sweep;
  });
  svg += '<text x="' + cx + '" y="' + (cy - 5) + '" text-anchor="middle" font-size="10" fill="var(--txt3)">' + centerLabel + '</text>';
  svg += '<text x="' + cx + '" y="' + (cy + 11) + '" text-anchor="middle" font-size="11" font-weight="700" fill="var(--txt1)">' + formatIDRShort(total) + '</text>';
  svg += '</svg>';
  let legend = '<div style="display:flex;flex-direction:column;gap:5px;margin-top:10px;font-size:11px;width:100%">';
  pakdCompliance.forEach((p, i) => {
    // D34/D35: dalam mode on-chain, baris bukan "terukur" tetap tampil
    // dengan em dash -- menghilangkan barisnya akan menyembunyikan fakta
    // bahwa custody-nya tidak diketahui. Dalam mode fallback (centerLabel
    // "Total di PTP") persentase berasal dari nilai dilaporkan, yang
    // tersedia untuk semua baris terlepas dari status on-chain.
    const takTerukur = centerLabel !== 'Total di PTP' && p.kustodian_onchain_status !== 'terukur';
    const pctDisplay = takTerukur ? '—' : (valueOf(p) / total * 100).toFixed(1) + '%';
    legend += '<div style="display:flex;align-items:center;gap:6px"><div style="width:9px;height:9px;border-radius:2px;flex-shrink:0;background:' + colors[i % colors.length] + '"></div><span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + escapeHtml(p.nama) + '</span><span class="mono" style="font-weight:600">' + pctDisplay + '</span></div>';
  });
  legend += '</div>';
  wrap.innerHTML = svg + legend + note;
}

function drawKustodianBubbleMap(data) {
  const wrap = document.getElementById('kust-bubble-wrap');
  if (!wrap) return;
  const wallets = data.wallets || [];
  const pakds = data.pakd_compliance || [];
  if (!wallets.length || !pakds.length) {
    wrap.innerHTML = '<div class="no-data-state">Tidak ada wallet atau PAKD terhubung</div>';
    return;
  }
  // 1 wallet = 1 PAKD: setiap hub wallet terhubung ke SATU PAKD dedicated
  const colors = ['#4a6cf7', '#f59e0b', '#ef4444', '#10b981', '#8b5cf6'];
  const colorByPakd = {};
  pakds.forEach((p, i) => { colorByPakd[p.pakd_id] = colors[i % colors.length]; });

  const clusterW = 240;
  const H = 260;
  let svg = '<svg width="' + (clusterW * wallets.length) + '" height="' + H + '" style="min-width:100%">';
  wallets.forEach((w, wi) => {
    const cx = clusterW * wi + clusterW / 2;
    const cy = H - 90;
    const centerR = 52;
    const addrShort = w.address.length > 16 ? w.address.slice(0, 8) + '…' + w.address.slice(-6) : w.address;
    const px = cx, py = 52;
    if (w.pakd_id) {
      const color = colorByPakd[w.pakd_id] || 'var(--txt4)';
      svg += '<line x1="' + cx + '" y1="' + (cy - centerR) + '" x2="' + px + '" y2="' + (py + 30) + '" stroke="var(--txt4)" stroke-dasharray="4 4" stroke-width="1"/>';
      svg += '<circle cx="' + px + '" cy="' + py + '" r="30" fill="' + color + '" opacity="0.9"/>';
      svg += '<text x="' + px + '" y="' + (py + 4) + '" text-anchor="middle" font-size="10" font-weight="700" fill="#fff">100%</text>';
      svg += '<text x="' + px + '" y="' + (py - 38) + '" text-anchor="middle" font-size="10" font-weight="600" fill="var(--txt2)" font-family="JetBrains Mono,monospace">' + w.pakd_id + '</text>';
    } else {
      svg += '<line x1="' + cx + '" y1="' + (cy - centerR) + '" x2="' + px + '" y2="' + (py + 30) + '" stroke="var(--txt4)" stroke-dasharray="2 5" stroke-width="1"/>';
      svg += '<circle cx="' + px + '" cy="' + py + '" r="30" fill="var(--bg2)" stroke="var(--txt4)" stroke-dasharray="4 3" stroke-width="1.5"/>';
      svg += '<text x="' + px + '" y="' + (py + 4) + '" text-anchor="middle" font-size="9" fill="var(--txt4)">belum</text>';
      svg += '<text x="' + px + '" y="' + (py - 38) + '" text-anchor="middle" font-size="10" fill="var(--txt4)">UNASSIGNED</text>';
    }
    // Wallet bubble
    svg += '<circle cx="' + cx + '" cy="' + cy + '" r="' + centerR + '" fill="var(--bg2)" stroke="var(--border)" stroke-width="2"/>';
    svg += '<text x="' + cx + '" y="' + (cy - 8) + '" text-anchor="middle" font-size="11" font-weight="700" fill="var(--txt1)">' + data.kustodian.id + '</text>';
    svg += '<text x="' + cx + '" y="' + (cy + 6) + '" text-anchor="middle" font-size="10" font-weight="600" fill="var(--txt2)" style="text-transform:uppercase">' + w.network + '</text>';
    svg += '<text x="' + cx + '" y="' + (cy + 20) + '" text-anchor="middle" font-size="8" fill="var(--txt4)" font-family="JetBrains Mono,monospace">' + addrShort + '</text>';
  });
  svg += '</svg>';
  wrap.innerHTML = svg;
}

async function saveKustodianWallets(newWallets) {
  const data = _kustMonitoringData;
  if (!data) return;
  try {
    const resp = await apiFetch(API + '/api/kustodian/' + data.kustodian.id, {
      method: 'PUT',
      body: JSON.stringify({wallets: newWallets})
    });
    if (!resp.ok) {
      const err = await resp.json();
      alert('Error: ' + (err.message || JSON.stringify(err)));
      return;
    }
    await renderKustodianMonitoring(data.kustodian.id);
    loadKustodian();
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

function _kustWalletPayload(x) {
  return {network: x.network, address: x.address, verified: x.verified, verified_at: x.verified_at, pakd_id: x.pakd_id || null};
}

function editKustWallet(i) {
  const data = _kustMonitoringData;
  if (!data || !data.wallets[i]) return;
  const w = data.wallets[i];
  const addr = prompt('Address baru untuk wallet ' + w.network.toUpperCase() + ':', w.address);
  if (!addr || addr.trim() === w.address) return;
  const wallets = data.wallets.map((x, j) => j === i
    ? Object.assign(_kustWalletPayload(x), {address: addr.trim(), verified: false, verified_at: null})
    : _kustWalletPayload(x));
  saveKustodianWallets(wallets);
}

function removeKustWallet(i) {
  const data = _kustMonitoringData;
  if (!data || !data.wallets[i]) return;
  const w = data.wallets[i];
  if (!confirm('Hapus wallet ' + w.network.toUpperCase() + ' ' + w.address + '?')) return;
  const wallets = data.wallets.filter((_, j) => j !== i).map(_kustWalletPayload);
  saveKustodianWallets(wallets);
}

function assignKustWallet(i) {
  const data = _kustMonitoringData;
  if (!data || !data.wallets[i]) return;
  const w = data.wallets[i];
  const linked = (data.pakd_compliance || []).map(p => p.pakd_id);
  const pid = (prompt('PAKD dedicated untuk wallet ' + w.network.toUpperCase() + ' ' + w.address.slice(0, 12) + '…\n' +
    'Pilihan: ' + (linked.join(', ') || '(tidak ada PAKD terhubung)') + '\n(kosongkan untuk unassign)', w.pakd_id || '') || '').trim();
  if (pid && linked.length && !linked.includes(pid) &&
      !confirm(pid + ' tidak terhubung ke kustodian ini. Tetap tetapkan?')) return;
  const wallets = data.wallets.map((x, j) => j === i
    ? Object.assign(_kustWalletPayload(x), {pakd_id: pid || null})
    : _kustWalletPayload(x));
  saveKustodianWallets(wallets);
}

function addKustWallet() {
  const data = _kustMonitoringData;
  if (!data) { alert('Pilih kustodian terlebih dahulu'); return; }
  const network = (prompt('Network (ethereum / bitcoin / solana):', 'ethereum') || '').trim().toLowerCase();
  if (!['ethereum', 'bitcoin', 'solana'].includes(network)) { if (network) alert('Network tidak dikenal: ' + network); return; }
  const addr = (prompt('Address wallet ' + network.toUpperCase() + ':') || '').trim();
  if (!addr) return;
  const linked = (data.pakd_compliance || []).map(p => p.pakd_id);
  const pid = (prompt('PAKD dedicated untuk wallet ini (1 wallet = 1 PAKD)\nPilihan: ' +
    (linked.join(', ') || '-') + '\n(kosongkan untuk unassigned)', linked[0] || '') || '').trim();
  const wallets = data.wallets.map(_kustWalletPayload)
    .concat([{network, address: addr, verified: false, verified_at: null, pakd_id: pid || null}]);
  saveKustodianWallets(wallets);
}

function formatIDRShort(n) {
  if (n >= 1e12) return 'Rp ' + (n / 1e12).toFixed(1) + ' T';
  if (n >= 1e9) return 'Rp ' + (n / 1e9).toFixed(1) + ' M';
  if (n >= 1e6) return 'Rp ' + (n / 1e6).toFixed(1) + ' Jt';
  return formatIDR(n);
}

function exportKustodianCSV() {
  const data = _kustMonitoringData;
  if (!data) { alert('Pilih kustodian terlebih dahulu'); return; }
  let csv = 'PAKD ID,Nama PAKD,AKD Konsumen di PAKD (Rp),On-Chain PAKD (Rp),AKD Konsumen di PTP (Rp),On-Chain Kustodian Total (Rp),Rasio di PAKD,Status,Asal Rasio\n';
  (data.pakd_compliance || []).forEach(p => {
    // D34/D35: kolom kustodian on-chain kosong, bukan 0, untuk baris
    // yang statusnya bukan "terukur".
    const kustOnchainCsv = p.kustodian_onchain_status === 'terukur' ? (p.kustodian_onchain_idr || 0) : '';
    csv += `${p.pakd_id},"${p.nama}",${p.customer_at_pakd_idr},${p.pakd_onchain_idr || 0},${p.customer_at_ptp_idr},${kustOnchainCsv},${((p.ratio_at_pakd || 0) * 100).toFixed(1)}%,${p.verdict_status},${p.ratio_provenance || ''}\n`;
  });
  csv += '\nWallet Network,Address,Verified\n';
  (data.wallets || []).forEach(w => {
    csv += `${w.network},${w.address},${w.verified}\n`;
  });
  const blob = new Blob([csv], {type: 'text/csv'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'kustodian_' + data.kustodian.id + '_monitoring.csv';
  a.click();
  URL.revokeObjectURL(url);
}

function openAddKustodianModal() {
  _editKustodianId = null;
  document.getElementById('modal-kustodian-title').textContent = 'Tambah Kustodian';
  document.getElementById('kust-form-id').value = '';
  document.getElementById('kust-form-id').disabled = false;
  document.getElementById('kust-form-nama').value = '';
  document.getElementById('kust-form-pakd-ids').value = '';
  document.getElementById('modal-kustodian').style.display = 'flex';
}

function editKustodian(id) {
  const k = _kustodianData.find(x => x.id === id);
  if (!k) return;
  _editKustodianId = id;
  document.getElementById('modal-kustodian-title').textContent = 'Edit Kustodian';
  document.getElementById('kust-form-id').value = k.id;
  document.getElementById('kust-form-id').disabled = true;
  document.getElementById('kust-form-nama').value = k.nama;
  document.getElementById('kust-form-pakd-ids').value = (k.pakd_ids || []).join(', ');
  document.getElementById('modal-kustodian').style.display = 'flex';
}

function closeKustodianModal() {
  document.getElementById('modal-kustodian').style.display = 'none';
}

async function submitKustodian(e) {
  e.preventDefault();
  const id = document.getElementById('kust-form-id').value.trim();
  const nama = document.getElementById('kust-form-nama').value.trim();
  const pakdRaw = document.getElementById('kust-form-pakd-ids').value.trim();
  const pakd_ids = pakdRaw ? pakdRaw.split(',').map(s => s.trim()).filter(Boolean) : [];
  const payload = {id, nama, pakd_ids};

  try {
    let resp;
    if (_editKustodianId) {
      resp = await apiFetch(API + '/api/kustodian/' + _editKustodianId, {method: 'PUT', body: JSON.stringify(payload)});
    } else {
      payload.wallets = [];
      resp = await apiFetch(API + '/api/kustodian', {method: 'POST', body: JSON.stringify(payload)});
    }
    if (!resp.ok) {
      const err = await resp.json();
      alert('Error: ' + (err.message || JSON.stringify(err)));
      return;
    }
    closeKustodianModal();
    loadKustodian();
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

async function deleteKustodian(id, nama) {
  if (!confirm('Hapus kustodian ' + nama + ' (' + id + ')? Data wallet dan link PAKD akan ikut terhapus.')) return;
  try {
    const resp = await apiFetch(API + '/api/kustodian/' + id, {method: 'DELETE'});
    if (!resp.ok) {
      const err = await resp.json();
      alert('Error: ' + (err.message || JSON.stringify(err)));
      return;
    }
    document.getElementById('kustodian-detail').style.display = 'none';
    loadKustodian();
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

// ---------------------------------------------------------------------------
// E-Reporting Page
// ---------------------------------------------------------------------------
let _ereportingPreviewData = null;

async function loadEreportingEntities() {
  const type = document.querySelector('input[name="ereporting-type"]:checked').value;
  const select = document.getElementById('ereporting-entity');
  select.innerHTML = '<option value="">Memuat...</option>';
  try {
    const url = type === 'pakd' ? API + '/api/pakd' : API + '/api/kustodian';
    const resp = await apiFetch(url);
    if (!resp.ok) { select.innerHTML = '<option value="">Gagal memuat entitas</option>'; return; }
    const list = await resp.json();
    if (!list.length) { select.innerHTML = '<option value="">Belum ada data</option>'; return; }
    select.innerHTML = '<option value="">Pilih entitas...</option>' +
      list.map(e => `<option value="${escapeAttr(e.id)}">${escapeHtml(e.id)} — ${escapeHtml(e.nama)}</option>`).join('');
  } catch (e) {
    select.innerHTML = '<option value="">Error: ' + escapeHtml(e.message) + '</option>';
  }
}

function onEreportingTypeChange() {
  cancelEreportingPreview();
  loadEreportingEntities();
}

async function submitEreportingUpload(event) {
  event.preventDefault();
  const type = document.querySelector('input[name="ereporting-type"]:checked').value;
  const entityId = document.getElementById('ereporting-entity').value;
  const periode = document.getElementById('ereporting-periode').value;
  const fileInput = document.getElementById('ereporting-file');
  const errEl = document.getElementById('ereporting-upload-error');
  errEl.style.display = 'none';

  if (!entityId) { errEl.textContent = 'Pilih entitas terlebih dahulu'; errEl.style.display = 'block'; return; }
  if (!periode) { errEl.textContent = 'Pilih periode terlebih dahulu'; errEl.style.display = 'block'; return; }
  if (!fileInput.files.length) { errEl.textContent = 'Pilih file XLSX terlebih dahulu'; errEl.style.display = 'block'; return; }

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  formData.append('type', type);
  formData.append('entity_id', entityId);
  formData.append('periode', periode);

  const btn = document.getElementById('btn-ereporting-upload');
  btn.disabled = true;
  btn.textContent = 'Mengunggah...';
  try {
    const resp = await apiFetch(API + '/api/upload-ereporting', {method: 'POST', body: formData});
    const body = await resp.json();
    if (!resp.ok) {
      errEl.textContent = body.message || 'Gagal mengunggah file';
      errEl.style.display = 'block';
      return;
    }
    renderEreportingPreview(body.data, type);
  } catch (e) {
    errEl.textContent = 'Error: ' + e.message;
    errEl.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Upload & Preview';
  }
}

function renderEreportingPreview(data, type) {
  _ereportingPreviewData = data;
  document.getElementById('ereporting-preview').style.display = 'block';

  const errBox = document.getElementById('ereporting-errors');
  if (data.errors && data.errors.length) {
    errBox.innerHTML = '<b>Peringatan:</b><ul style="margin:6px 0 0 18px">' +
      data.errors.map(e => `<li>${escapeHtml(e)}</li>`).join('') + '</ul>';
    errBox.style.display = 'block';
  } else {
    errBox.style.display = 'none';
  }

  const thead = document.getElementById('ereporting-preview-thead');
  const tbody = document.getElementById('ereporting-preview-tbody');
  const summary = document.getElementById('ereporting-summary');

  if (type === 'pakd') {
    const breakdown = data.aset_breakdown || [];
    thead.innerHTML = '<tr><th>Kode AKD</th><th>Nama AKD</th><th>Unit Konsumen di Pedagang</th><th>Unit Konsumen di PTP</th><th>Unit Pedagang</th><th>Harga/Unit (Rp)</th></tr>';
    tbody.innerHTML = breakdown.map(r => `
      <tr>
        <td>${escapeHtml(r.kode_akd || '')}</td>
        <td>${escapeHtml(r.nama_akd || '')}</td>
        <td>${(r.konsumen_di_pedagang_unit || 0).toLocaleString('id-ID')}</td>
        <td>${(r.konsumen_di_ptp_unit || 0).toLocaleString('id-ID')}</td>
        <td>${(r.pedagang_unit || 0).toLocaleString('id-ID')}</td>
        <td>${formatIDR(r.harga_per_unit_idr || 0)}</td>
      </tr>
    `).join('') || '<tr><td colspan="6" style="text-align:center;color:var(--txt4)">Tidak ada baris aset</td></tr>';

    const totalPakd = breakdown.reduce((s, r) => s + (r.konsumen_di_pedagang_unit || 0) * (r.harga_per_unit_idr || 0), 0);
    const totalPtp = breakdown.reduce((s, r) => s + (r.konsumen_di_ptp_unit || 0) * (r.harga_per_unit_idr || 0), 0);
    const totalPedagang = breakdown.reduce((s, r) => s + (r.pedagang_unit || 0) * (r.harga_per_unit_idr || 0), 0);
    summary.innerHTML = `Total AKD Konsumen di PAKD: <b>${formatIDR(totalPakd)}</b> &nbsp;|&nbsp; di PTP: <b>${formatIDR(totalPtp)}</b> &nbsp;|&nbsp; Milik Pedagang: <b>${formatIDR(totalPedagang)}</b>`;
  } else {
    const wallets = data.wallets || [];
    thead.innerHTML = '<tr><th>Alamat Wallet</th><th>Provider</th><th>Network</th><th>Nama Pedagang</th><th>Nilai AKD (Rp)</th></tr>';
    tbody.innerHTML = wallets.map(w => `
      <tr>
        <td style="font-family:'JetBrains Mono',monospace;font-size:11px;word-break:break-all">${escapeHtml(w.alamat || '')}</td>
        <td>${escapeHtml(w.provider || '')}</td>
        <td>${escapeHtml(w.network || '')}</td>
        <td>${escapeHtml(w.nama_pedagang || '')}</td>
        <td>${formatIDR(w.nilai_akd_idr || 0)}</td>
      </tr>
    `).join('') || '<tr><td colspan="5" style="text-align:center;color:var(--txt4)">Tidak ada wallet</td></tr>';

    const totalNilai = wallets.reduce((s, w) => s + (w.nilai_akd_idr || 0), 0);
    summary.innerHTML = `Total Nilai AKD pada ${wallets.length} wallet: <b>${formatIDR(totalNilai)}</b>`;
  }

  document.getElementById('ereporting-confirm-feedback').style.display = 'none';
}

function cancelEreportingPreview() {
  _ereportingPreviewData = null;
  document.getElementById('ereporting-preview').style.display = 'none';
}

async function submitEreportingConfirm() {
  if (!_ereportingPreviewData) return;
  const btn = document.getElementById('btn-ereporting-confirm');
  const feedback = document.getElementById('ereporting-confirm-feedback');
  btn.disabled = true;
  btn.textContent = 'Menyimpan...';
  try {
    const resp = await apiFetch(API + '/api/confirm-ereporting', {
      method: 'POST',
      body: JSON.stringify(_ereportingPreviewData)
    });
    const body = await resp.json();
    feedback.style.display = 'block';
    if (!resp.ok) {
      feedback.style.color = 'var(--red)';
      feedback.textContent = body.message || 'Gagal menyimpan data';
      return;
    }
    feedback.style.color = 'var(--green)';
    feedback.textContent = `Tersimpan: ${body.entity_id} periode ${body.periode}`;
    document.getElementById('form-ereporting-upload').reset();
    _ereportingPreviewData = null;
    setTimeout(() => { document.getElementById('ereporting-preview').style.display = 'none'; }, 2000);
  } catch (e) {
    feedback.style.display = 'block';
    feedback.style.color = 'var(--red)';
    feedback.textContent = 'Error: ' + e.message;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Konfirmasi dan Simpan';
  }
}

function applyRoleUI() {
  const user = AUTH.getUser();
  if (!user) return;

  // Update user badge
  const badge = document.getElementById('user-badge');
  const btnLogout = document.getElementById('btn-logout');
  if (badge) {
    const roleLabel = {
      super_admin: 'Super Admin', pengawas: 'Pengawas',
      pakd: 'PAKD', kustodian: 'Kustodian'
    }[user.role] || user.role;
    badge.textContent = user.display_name + ' · ' + roleLabel;
    badge.style.display = 'flex';
  }
  if (btnLogout) btnLogout.style.display = 'inline-block';

  // Tampilkan CRUD actions hanya untuk super_admin
  const isSuperAdmin = user.role === 'super_admin';
  document.querySelectorAll('.crud-action').forEach(el => {
    el.style.display = isSuperAdmin ? (el.tagName === 'BUTTON' ? 'inline-flex' : 'block') : 'none';
  });
  // Nav items visible hanya untuk super_admin (mis. E-Reporting)
  document.querySelectorAll('.superadmin-only').forEach(el => {
    el.style.display = isSuperAdmin ? 'flex' : 'none';
  });
  // Pengawas = read-only: hide write actions (rekon trigger, wallet verification)
  const isPengawas = user.role === 'pengawas';
  document.querySelectorAll('button').forEach(el => {
    const txt = el.textContent.trim();
    if (txt.includes('Rekonsiliasi Manual') || txt.includes('Minta Challenge')) {
      el.style.display = isPengawas ? 'none' : '';
    }
  });
  // Hide Verifikasi Wallet section for pengawas
  const vpSection = document.querySelector('#vp-address');
  if (vpSection && isPengawas) {
    vpSection.closest('.card, section, div[style]').style.display = 'none';
  }
}

// ── Login v3: vision quotes rotation ──
const LOGIN_QUOTES = [
  {
    eyebrow: "Our Vision",
    text: "A robust and transparent digital asset ecosystem for Indonesia.",
    sub: "Building supervisory infrastructure that protects consumers, strengthens market integrity, and positions Indonesia as a trusted digital economy."
  },
  {
    eyebrow: "Consumer Protection",
    text: "Every Indonesian investor deserves full visibility into where their assets are held.",
    sub: "Real-time multichain monitoring ensures that licensed exchanges maintain verifiable reserves, protecting millions of retail participants."
  },
  {
    eyebrow: "National Sovereignty",
    text: "Indonesia's digital asset market, supervised by Indonesian regulators, on Indonesian terms.",
    sub: "PRIMA gives OJK direct on-chain oversight capability, reducing reliance on foreign compliance tools and third-party attestations."
  },
  {
    eyebrow: "Responsible Growth",
    text: "Regulation is not the enemy of innovation. It is the foundation of trust.",
    sub: "Clear rules and transparent supervision attract legitimate capital, deter bad actors, and accelerate Indonesia's participation in the global crypto economy."
  },
  {
    eyebrow: "Accountability",
    text: "If it can be verified on-chain, it should be verified on-chain.",
    sub: "Cryptographic proof of reserves, wallet ownership, and asset placement compliance, all reconciled against licensed entity reports in a single system."
  }
];

let loginQuoteIntervalId = null;
let loginCurrentQ = 0;

function loginGoToQuote(idx) {
  const container = document.getElementById('loginQuoteContainer');
  const indicators = document.getElementById('loginQuoteIndicators');
  const blocks = container.querySelectorAll('.login-quote-block');
  const dots = indicators.querySelectorAll('.login-q-dot');
  if (!blocks.length) return;
  blocks[loginCurrentQ].classList.remove('active');
  dots[loginCurrentQ].classList.remove('active');
  loginCurrentQ = idx;
  blocks[loginCurrentQ].classList.add('active');
  dots[loginCurrentQ].classList.add('active');
}

function startQuoteRotation() {
  const container = document.getElementById('loginQuoteContainer');
  const indicators = document.getElementById('loginQuoteIndicators');
  if (!container || !indicators) return;
  stopQuoteRotation();
  container.innerHTML = '';
  indicators.innerHTML = '';
  loginCurrentQ = 0;
  LOGIN_QUOTES.forEach((q, i) => {
    const block = document.createElement('div');
    block.className = 'login-quote-block' + (i === 0 ? ' active' : '');
    const eyebrow = document.createElement('div');
    eyebrow.className = 'login-quote-eyebrow';
    eyebrow.textContent = q.eyebrow;
    const text = document.createElement('div');
    text.className = 'login-quote-text';
    text.textContent = q.text;
    const sub = document.createElement('div');
    sub.className = 'login-quote-sub';
    sub.textContent = q.sub;
    block.append(eyebrow, text, sub);
    container.appendChild(block);

    const dot = document.createElement('div');
    dot.className = 'login-q-dot' + (i === 0 ? ' active' : '');
    dot.addEventListener('click', () => loginGoToQuote(i));
    indicators.appendChild(dot);
  });
  loginQuoteIntervalId = setInterval(() => loginGoToQuote((loginCurrentQ + 1) % LOGIN_QUOTES.length), 6000);
}

function stopQuoteRotation() {
  if (loginQuoteIntervalId) {
    clearInterval(loginQuoteIntervalId);
    loginQuoteIntervalId = null;
  }
}

// ── Login v3: Chainalysis-style grid animation ──
let loginAnimationId = null;
let loginResizeInited = false;
let loginResizeFn = null;

function startLoginAnimation() {
  const canvas = document.getElementById('loginNetCanvas');
  if (!canvas) return;
  stopLoginAnimation();

  const ctx = canvas.getContext('2d');
  let W, H, cols, rows;
  const CELL = 90;          // grid spacing
  const DOT = 'rgba(169,214,239,0.4)';
  const BLUE = [169, 214, 239];
  const DEEP = [125, 187, 230];
  const GOLD = [212, 196, 154];
  let shapes = [];
  let lastSpawn = 0;

  function resize() {
    W = canvas.width = canvas.offsetWidth;
    H = canvas.height = canvas.offsetHeight;
    cols = Math.floor(W / CELL);
    rows = Math.floor(H / CELL);
    shapes = [];
  }
  loginResizeFn = resize;

  function gx(c) { return (W - (cols - 1) * CELL) / 2 + c * CELL; }
  function gy(r) { return (H - (rows - 1) * CELL) / 2 + r * CELL; }
  function rndCell() {
    return { c: Math.floor(Math.random() * cols), r: Math.floor(Math.random() * rows) };
  }
  function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }

  // Each shape lives through: draw-in (grow), hold, fade-out
  function spawnShape() {
    const kind = pick(['pulse', 'pulse', 'rect', 'arc', 'arc', 'square']);
    const col = Math.random() < 0.18 ? GOLD : (Math.random() < 0.5 ? BLUE : DEEP);
    const cell = rndCell();
    const s = { kind, col, t: 0, drawT: 90, holdT: 140, fadeT: 90, cell };
    if (kind === 'rect') {
      s.w = 1 + Math.floor(Math.random() * 2);
      s.h = 1 + Math.floor(Math.random() * 2);
      s.cell.c = Math.min(s.cell.c, Math.max(0, cols - 1 - s.w));
      s.cell.r = Math.min(s.cell.r, Math.max(0, rows - 1 - s.h));
      s.drawT = 130;
    } else if (kind === 'arc') {
      s.rad = CELL * (1 + Math.floor(Math.random() * 2));
      s.q = Math.floor(Math.random() * 4); // quadrant
      s.drawT = 110;
    } else if (kind === 'square') {
      s.cell.c = Math.min(s.cell.c, Math.max(0, cols - 2));
      s.cell.r = Math.min(s.cell.r, Math.max(0, rows - 2));
      s.holdT = 100;
    }
    shapes.push(s);
  }

  function alphaOf(s, base) {
    if (s.t < s.drawT) return base;
    const tf = s.t - s.drawT - s.holdT;
    if (tf <= 0) return base;
    return base * Math.max(0, 1 - tf / s.fadeT);
  }
  function progressOf(s) { return Math.min(1, s.t / s.drawT); }

  function drawShape(s) {
    const [r, g, b] = s.col;
    const p = progressOf(s);
    const x = gx(s.cell.c), y = gy(s.cell.r);

    if (s.kind === 'pulse') {
      const a = alphaOf(s, 0.9);
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${r},${g},${b},${a})`;
      ctx.fill();
      ctx.beginPath();
      ctx.arc(x, y, 7 + 3 * p, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(${r},${g},${b},${alphaOf(s, 0.55)})`;
      ctx.lineWidth = 1.2;
      ctx.stroke();
    } else if (s.kind === 'rect') {
      const w = s.w * CELL, h = s.h * CELL;
      const perim = 2 * (w + h);
      const len = perim * p;
      ctx.strokeStyle = `rgba(${r},${g},${b},${alphaOf(s, 0.55)})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      let remaining = len, cx = x, cy = y;
      const legs = [[w, 0], [0, h], [-w, 0], [0, -h]];
      ctx.moveTo(cx, cy);
      for (const [dx, dy] of legs) {
        const legLen = Math.abs(dx) + Math.abs(dy);
        const f = Math.min(1, remaining / legLen);
        cx += dx * f; cy += dy * f;
        ctx.lineTo(cx, cy);
        remaining -= legLen;
        if (remaining <= 0) break;
      }
      ctx.stroke();
      // corner dots
      ctx.fillStyle = `rgba(${r},${g},${b},${alphaOf(s, 0.8)})`;
      for (const [px, py] of [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]) {
        ctx.beginPath(); ctx.arc(px, py, 2, 0, Math.PI * 2); ctx.fill();
      }
    } else if (s.kind === 'arc') {
      const start = s.q * Math.PI / 2;
      ctx.beginPath();
      ctx.arc(x, y, s.rad, start, start + (Math.PI / 2) * p);
      ctx.strokeStyle = `rgba(${r},${g},${b},${alphaOf(s, 0.5)})`;
      ctx.lineWidth = 1.2;
      ctx.stroke();
    } else if (s.kind === 'square') {
      ctx.fillStyle = `rgba(${r},${g},${b},${alphaOf(s, 0.12 * p)})`;
      ctx.fillRect(x, y, CELL, CELL);
      ctx.strokeStyle = `rgba(${r},${g},${b},${alphaOf(s, 0.35)})`;
      ctx.lineWidth = 1;
      ctx.strokeRect(x, y, CELL, CELL);
    }
  }

  function frame(ts) {
    ctx.clearRect(0, 0, W, H);

    // static dot grid
    ctx.fillStyle = DOT;
    for (let c = 0; c < cols; c++) {
      for (let r = 0; r < rows; r++) {
        ctx.beginPath();
        ctx.arc(gx(c), gy(r), 1.6, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // spawn a new shape roughly every 1.1s, cap concurrency
    if (!lastSpawn || ts - lastSpawn > 1100) {
      if (shapes.length < 7) spawnShape();
      lastSpawn = ts;
    }

    for (const s of shapes) { s.t++; drawShape(s); }
    shapes = shapes.filter(s => s.t < s.drawT + s.holdT + s.fadeT);

    loginAnimationId = requestAnimationFrame(frame);
  }

  if (!loginResizeInited) {
    window.addEventListener('resize', () => {
      if (loginResizeFn && document.getElementById('login-overlay').style.display !== 'none') loginResizeFn();
    });
    loginResizeInited = true;
  }

  resize();
  loginAnimationId = requestAnimationFrame(frame);
}

function stopLoginAnimation() {
  if (loginAnimationId) {
    cancelAnimationFrame(loginAnimationId);
    loginAnimationId = null;
  }
}

async function doLogin() {
  const email = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;
  const errEl = document.getElementById('login-error');
  const btn = document.getElementById('btn-login');

  if (!email || !password) {
    errEl.textContent = 'Email dan password wajib diisi';
    errEl.style.display = 'block';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Memproses...';
  errEl.style.display = 'none';

  try {
    const resp = await fetch('/api/auth/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({email, password})
    });
    const data = await resp.json();
    if (!resp.ok) {
      errEl.textContent = data.error || 'Login gagal. Periksa email dan password.';
      errEl.style.display = 'block';
      return;
    }
    AUTH.save(data);
    showDashboard();
    loadAll();
  } catch(e) {
    errEl.textContent = 'Koneksi gagal. Periksa jaringan internet.';
    errEl.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Masuk';
  }
}

function doLogout() {
  AUTH.clear();
  showLogin();
}

function showLogin() {
  document.getElementById('login-overlay').style.display = 'flex';
  document.getElementById('login-email').value = '';
  document.getElementById('login-password').value = '';
  document.getElementById('login-error').style.display = 'none';
  startLoginAnimation();
  startQuoteRotation();
  const badge = document.getElementById('user-badge');
  const btnLogout = document.getElementById('btn-logout');
  if (badge) badge.style.display = 'none';
  if (btnLogout) btnLogout.style.display = 'none';
}

function showDashboard() {
  document.getElementById('login-overlay').style.display = 'none';
  stopLoginAnimation();
  stopQuoteRotation();
  applyRoleUI();
}

async function handleAuthError(resp) {
  if (resp.status === 401) {
    AUTH.clear();
    showLogin();
    return true;
  }
  return false;
}

async function apiFetch(url, options = {}) {
  const h = {...AUTH.authOnly(), ...(options.headers || {})};
  let resp = await fetch(url, {...options, headers: h});
  if (resp.status === 401) {
    const refreshed = await AUTH.refreshToken();
    if (refreshed) {
      const h2 = {...AUTH.authOnly(), ...(options.headers || {})};
      resp = await fetch(url, {...options, headers: h2});
    }
    if (resp.status === 401) { AUTH.clear(); showLogin(); throw new Error('Session expired'); }
  }
  return resp;
}

// Enter key di login form
document.addEventListener('DOMContentLoaded', () => {
  const pwInput = document.getElementById('login-password');
  if (pwInput) pwInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') doLogin(); });
  const emailInput = document.getElementById('login-email');
  if (emailInput) emailInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') doLogin(); });

  // Password visibility toggle
  const togglePw = document.getElementById('loginTogglePw');
  if (togglePw && pwInput) {
    togglePw.addEventListener('click', () => {
      const show = pwInput.type === 'password';
      pwInput.type = show ? 'text' : 'password';
      togglePw.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
      togglePw.innerHTML = show
        ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>'
        : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
    });
  }

  if (AUTH.isLoggedIn()) {
    showDashboard();
    loadAll();
  } else {
    showLogin();
  }
});

let _adminToken = '';
function getAdminToken() {
  const token = AUTH.getToken();
  if (token) return token;
  // fallback legacy
  const field = document.getElementById('edit-admin-token');
  if (field && field.value.trim()) _adminToken = field.value.trim();
  if (!_adminToken) _adminToken = prompt('PRIMA Admin Token diperlukan untuk operasi ini:') || '';
  return _adminToken;
}
let _editPakdId = null;
let _pakdCache = [];

function openAddModal() {
  _editPakdId = null;
  document.getElementById('modal-pakd-title').textContent = 'Tambah PAKD Baru';
  const idField = document.getElementById('edit-pakd-id');
  idField.value = '';
  idField.removeAttribute('readonly');
  idField.style.opacity = '1';
  document.getElementById('edit-pakd-nama').value = '';
  document.getElementById('edit-pakd-aset').value = '';
  ['edit-equity','edit-persediaan','edit-simpanan','edit-customer'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  _editingWallets = null;
  renderWalletRows([]);
  document.getElementById('modal-pakd').style.display = 'flex';
}
async function openEditModal(pakdId) {
  _editPakdId = pakdId;
  document.getElementById('modal-pakd-title').textContent = 'Edit PAKD: ' + pakdId;
  document.getElementById('modal-pakd').style.display = 'flex';
  let pakd = null;
  try {
    const resp = await apiFetch('/api/pakd');
    const list = await resp.json();
    pakd = list.find(p => p.id === pakdId);
  } catch(e) { pakd = _pakdCache.find(p => p.id === pakdId); }
  if (!pakd) return alert('Data PAKD tidak ditemukan');
  const idField = document.getElementById('edit-pakd-id');
  idField.value = pakd.id;
  idField.setAttribute('readonly', 'readonly');
  idField.style.opacity = '0.6';
  document.getElementById('edit-pakd-nama').value = pakd.nama || '';
  document.getElementById('edit-pakd-aset').value = pakd.aset_dilaporkan || '';
  const _ef = ['edit-equity','edit-persediaan','edit-simpanan','edit-customer'];
  const _ev = [pakd.equity_idr, pakd.persediaan_akd_idr, pakd.simpanan_pedagang_akd_idr, pakd.customer_akd_idr];
  _ef.forEach((id,i) => { const el = document.getElementById(id); if (el) el.value = _ev[i] || ''; });
  _editingWallets = pakd.wallets || [];
  renderWalletRows(pakd.wallets || []);
}

function closeEditModal() {
  document.getElementById('modal-pakd').style.display = 'none';
  _editPakdId = null;
}

function renderWalletRows(wallets) {
  const container = document.getElementById('edit-wallets-container');
  container.innerHTML = wallets.map((w, i) => `
    <div style="display:flex;gap:8px;margin-bottom:8px;align-items:center" id="wallet-row-${i}">
      <select style="padding:6px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--txt1)">
        <option ${w.network==='ethereum'?'selected':''}>ethereum</option>
        <option ${w.network==='bitcoin'?'selected':''}>bitcoin</option>
        <option ${w.network==='solana'?'selected':''}>solana</option>
      </select>
      <input value="${escapeHtml(w.address)}" placeholder="Alamat wallet" style="flex:1;padding:6px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--txt1)">
      <button onclick="removeEditWalletRow(${i})" style="background:var(--red);color:#fff;border:none;border-radius:6px;padding:6px 10px;cursor:pointer">✕</button>
    </div>`).join('');
}

function addEditWalletRow() {
  const container = document.getElementById('edit-wallets-container');
  const i = container.children.length;
  const div = document.createElement('div');
  div.id = 'wallet-row-' + i;
  div.style = 'display:flex;gap:8px;margin-bottom:8px;align-items:center';
  div.innerHTML = `
    <select style="padding:6px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--txt1)">
      <option>ethereum</option><option>bitcoin</option><option>solana</option>
    </select>
    <input placeholder="Alamat wallet" style="flex:1;padding:6px;border-radius:6px;border:1px solid var(--border);background:var(--bg);color:var(--txt1)">
    <button onclick="this.parentElement.remove()" style="background:var(--red);color:#fff;border:none;border-radius:6px;padding:6px 10px;cursor:pointer">✕</button>`;
  container.appendChild(div);
}

function removeEditWalletRow(i) {
  document.getElementById('wallet-row-' + i).remove();
}

let _editingWallets = null;
function getWalletsFromModal() {
  const rows = document.getElementById('edit-wallets-container').children;
  return Array.from(rows).map(row => {
    const address = row.querySelector('input').value.trim();
    const network = row.querySelector('select').value;
    const existing = _editingWallets ? _editingWallets.find(
      w => w.address.toLowerCase() === address.toLowerCase() && w.network === network
    ) : null;
    return {
      network,
      address,
      verified: existing ? existing.verified : false,
      verified_at: existing ? existing.verified_at : null
    };
  }).filter(w => w.address);
}

async function saveEditModal() {
  const nama = document.getElementById('edit-pakd-nama').value.trim();
  const aset = parseInt(document.getElementById('edit-pakd-aset').value) || 0;
  const wallets = getWalletsFromModal();
  const equity_idr = parseInt(document.getElementById('edit-equity').value) || null;
  const persediaan_akd_idr = parseInt(document.getElementById('edit-persediaan').value) || null;
  const simpanan_pedagang_akd_idr = parseInt(document.getElementById('edit-simpanan').value) || null;
  const customer_akd_idr = parseInt(document.getElementById('edit-customer').value) || null;
  try {
    let resp;
    if (_editPakdId === null) {
      const newId = document.getElementById('edit-pakd-id').value.trim();
      if (!newId) return alert('ID PAKD wajib diisi');
      if (!nama) return alert('Nama PAKD wajib diisi');
      resp = await apiFetch('/api/input-manual', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: newId, nama: nama, aset_dilaporkan: aset, wallets: wallets, equity_idr, persediaan_akd_idr, simpanan_pedagang_akd_idr, customer_akd_idr})
      });
    } else {
      resp = await apiFetch('/api/pakd/' + _editPakdId, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({nama: nama, aset_dilaporkan: aset, wallets: wallets, equity_idr, persediaan_akd_idr, simpanan_pedagang_akd_idr, customer_akd_idr})
      });
    }
    if (resp.status === 401) { AUTH.clear(); showLogin(); return; }
    if (!resp.ok) throw new Error(await resp.text());
    const saveBtn = document.querySelector('#edit-modal button[onclick="saveEditModal()"]');
    const _savedPakdId = _editPakdId;
    closeEditModal();
    const tbody = document.getElementById('pakd-tbody');
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:20px;color:var(--blue)">Memperbarui snapshot...</td></tr>';
    if (_savedPakdId) {
      await apiFetch('/api/pakd/' + _savedPakdId + '/recalc-snapshot', {method:'POST'}).catch(() => {});
    }
    loadSnapshot();
  } catch(e) {
    alert('Gagal menyimpan: ' + e.message);
  }
}

async function deletePakd(pakdId) {
  if (!confirm('Hapus PAKD ' + pakdId + '? Tindakan ini tidak dapat dibatalkan.')) return;
  try {
    const resp = await apiFetch('/api/pakd/' + pakdId, {method: 'DELETE'});
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      loadSnapshot();
      throw new Error(body.error || 'Gagal menghapus');
    }
    loadSnapshot();
  } catch(e) {
    alert('Gagal menghapus: ' + e.message);
  }
}
