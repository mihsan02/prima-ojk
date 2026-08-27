function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function showPage(id, el) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('page-' + id).classList.add('active');
  if (el) el.classList.add('active');
  if (id === 'stresstest') loadStressTest();
  if (id === 'auditlog') loadAudit();
  if (id === 'pengaturan') loadPengaturan();
  if (id === 'detail') populateDetailSelect();
  if (id === 'kustodian') loadKustodian();
  if (id === 'ereporting') loadEreportingEntities();
  if (typeof clearVpChallenge === 'function' && document.getElementById('vp-challenge-box')) clearVpChallenge();
}

function formatIDR(n) {
  return 'Rp ' + Math.round(n).toLocaleString('id-ID');
}

function statusClass(s) {
  if (s === 'Aman') return 'aman';
  if (s === 'Deviasi') return 'deviasi';
  if (s === 'Data Tidak Lengkap') return 'tidak-lengkap';
  if (s === 'Surplus Tidak Wajar') return 'surplus-tw';
  return 'kritis';
}

function deviDisplay(d) {
  if (d.status === 'Data Tidak Lengkap' || d.deviasi_pct === null || d.deviasi_pct === undefined) {
    if (d.deviasi_pct_indikatif !== null && d.deviasi_pct_indikatif !== undefined) {
      const pctInd = d.deviasi_pct_indikatif;
      const colorInd = pctInd >= 0 ? 'var(--green)' : (d.status_indikatif === 'Deviasi' ? 'var(--amber)' : 'var(--red)');
      const sign = pctInd >= 0 ? '+' : '';
      return `<span style="color:${colorInd};font-family:'JetBrains Mono',monospace;font-size:12px;font-weight:600" title="Indikatif, data belum lengkap">${sign}${pctInd.toFixed(2)}%*</span>`;
    }
    return '<span style="color:var(--txt3);font-family:\'JetBrains Mono\',monospace;font-size:12px;font-weight:600">\u2014</span>';
  }
  const pct = d.deviasi_pct;
  if (d.surplus) {
    return `<span style="color:var(--green);font-family:'JetBrains Mono',monospace;font-size:12px;font-weight:600">+${pct.toFixed(2)}%</span>`;
  }
  const color = d.status === 'Deviasi' ? 'var(--amber)' : 'var(--red)';
  return `<span style="color:${color};font-family:'JetBrains Mono',monospace;font-size:12px;font-weight:600">${pct.toFixed(2)}%</span>`;
}

async function loadData() {
  const tbody = document.getElementById('pakd-tbody');
  tbody.innerHTML = '<tr class="loading-row"><td colspan="8">Mengambil data dari blockchain...</td></tr>';
  try {
    const res = await apiFetch('/api/reconciliation');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const json = await res.json();
    const data = json.data;
    _pakdCache = data;
    const now = new Date().toLocaleString('id-ID', {day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'});
    document.getElementById('last-update').textContent = now;
    document.getElementById('footer-time').textContent = 'Rekonsiliasi terakhir: ' + now;
    document.getElementById('live-badge').textContent = 'LIVE';
    const fallbackNotice = document.getElementById('eth-fallback-notice');
    if (json.harga_fallback) {
      fallbackNotice.style.display = 'block';
      document.getElementById('kpi-blockchain-sub').textContent = 'Etherscan V2 · CoinGecko (fallback)';
    } else {
      fallbackNotice.style.display = 'none';
      document.getElementById('kpi-blockchain-sub').textContent = 'Etherscan V2 · CoinGecko';
    }
    const aman = data.filter(d => d.status === 'Aman').length;
    const kritis = data.filter(d => d.status === 'Kritis').length;
    const peringatan = data.filter(d => d.status === 'Deviasi').length;
    document.getElementById('kpi-aman').textContent = data.length - aman;
    document.getElementById('kpi-total-label').textContent = aman + ' entitas dalam status aman';
    const _sub = document.getElementById('kpi-alert-sub');
    if (_sub) _sub.textContent = kritis + ' kritis · ' + peringatan + ' peringatan';
    const _snap = document.getElementById('kpi-snapshot-val');
    if (_snap) { const _n = new Date(); _snap.textContent = _n.getDate() + ' ' + ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Ags','Sep','Okt','Nov','Des'][_n.getMonth()] + ' ' + _n.getFullYear() + ', ' + String(_n.getHours()).padStart(2,'0') + '.' + String(_n.getMinutes()).padStart(2,'0'); }
    document.getElementById('kpi-alert').textContent = data.length - aman;
    const defisits = data.filter(d => !d.surplus).map(d => Math.abs(d.deviasi_pct));
    document.getElementById('kpi-max-dev').textContent = defisits.length ? Math.max(...defisits).toFixed(2) + '%' : '0%';
    tbody.innerHTML = data.map((d, i) => `
      <tr style="background:${d.status==='Kritis'?'rgba(192,57,43,0.03)':d.status==='Deviasi'?'rgba(194,124,26,0.03)':''};cursor:pointer" onclick="toggleDetail(${escapeAttr(JSON.stringify('det-' + d.id))})">
        <td class="num-row" style="vertical-align:top;padding-top:18px">${String(i+1).padStart(2,'0')}</td>
        <td style="vertical-align:top;padding-top:14px;min-width:220px">
          <span class="pakd-name">${escapeHtml(d.nama)}</span>
          <span class="pakd-id">${escapeHtml(d.id)} · Berizin</span>
        </td>
        <td style="vertical-align:top;padding-top:18px">${
          d.status_indikatif
            ? ('<span class="status-badge ' + statusClass(d.status_indikatif) + '">' + escapeHtml(d.status_indikatif) + '*</span><br><span style="color:var(--txt4);font-size:11px">Data Tidak Lengkap</span>')
            : ('<span class="status-badge ' + statusClass(d.status) + '">' + d.status + '</span>')
        }</td>
        <td class="mono-val" style="color:var(--txt1);vertical-align:top;padding-top:18px">${
          d.status === 'Data Tidak Lengkap'
            ? (d.subtotal_diketahui_idr != null
                ? formatIDR(d.subtotal_diketahui_idr) + '<br><span style="color:var(--txt4);font-size:11px">parsial, cek status wallet</span>'
                : '<span style="color:var(--txt3)">\u2014</span>')
            : formatIDR(d.aset_onchain_idr_final ?? d.aset_onchain_idr)
        }</td>
        <td class="mono-val" style="color:var(--txt2);vertical-align:top;padding-top:18px">${formatIDR(d.aset_dilaporkan_idr)}</td>
        <td style="vertical-align:top;padding-top:18px">${deviDisplay(d)}</td>
        <td style="vertical-align:top;padding-top:14px">${renderWalletBadges(d)}</td>
        <td style="vertical-align:top;padding-top:16px">
          <div style="display:flex;gap:6px;align-items:center">
            <button onclick="event.stopPropagation();openEditModal('${escapeHtml(d.id)}')"
              class="crud-action"
              style="background:none;border:none;cursor:pointer;color:#64748b;border-radius:6px;padding:6px 8px;transition:all 0.15s"
              onmouseover="this.style.background='#eff6ff';this.style.color='#2563eb'"
              onmouseout="this.style.background='none';this.style.color='#64748b'"
              title="Edit PAKD">✏️</button>
            <button onclick="event.stopPropagation();deletePakd('${escapeHtml(d.id)}')"
              class="crud-action"
              style="background:none;border:none;cursor:pointer;color:#64748b;border-radius:6px;padding:6px 8px;transition:all 0.15s"
              onmouseover="this.style.background='#fef2f2';this.style.color='#dc2626'"
              onmouseout="this.style.background='none';this.style.color='#64748b'"
              title="Hapus PAKD">🗑️</button>
            <span id="icon-det-${escapeAttr(d.id)}" style="color:#94a3b8;font-size:11px;margin-left:2px">▼</span>
          </div>
        </td>
      </tr>
      <tr id="det-${escapeAttr(d.id)}" class="detail-expand-row" style="display:none">
        <td colspan="8" style="padding:0">
          <div class="det-inner-grid">
            <div>
              <div class="det-section-lbl">Alamat Wallet Terdaftar</div>
              ${renderWalletsCell(d)}
            </div>
            <div>
              <div class="det-section-lbl">Breakdown Aset On-Chain</div>
              ${renderBreakdown(d)}
            </div>
          </div>
        </td>
      </tr>`).join('');
    applyRoleUI();
  } catch (err) {
    tbody.innerHTML = '<tr class="error-row"><td colspan="8">Gagal mengambil data: ' + escapeHtml(err.message) + '</td></tr>';
    const badge = document.getElementById('live-badge');
    if (badge) { badge.textContent = 'OFFLINE'; badge.style.background = 'var(--red)'; }
  }
}

function renderP91Cards(cid, perPakd) {
  var el = document.getElementById(cid);
  if (!el || !perPakd) return;
  el.innerHTML = perPakd.map(function(p) {
    var cls = p.lulus ? 'pass' : 'fail';
    var icon = p.lulus ? '✓' : '✕';
    var eqVal = p.equity_post;
    var eqCls = eqVal >= 0 ? 'green' : 'red';
    var eqStr = (eqVal < 0 ? '−' : '') + formatIDR(Math.abs(eqVal));
    return '<div class="entity-card-st ' + cls + '">' +
      '<div class="entity-card-st-name ' + cls + '">' + icon + ' ' + escapeHtml(p.nama) + '</div>' +
      '<div class="entity-card-st-row"><span class="entity-card-st-lbl">AKD hilang</span><span class="entity-card-st-val red">−' + formatIDR(p.loss_idr) + '</span></div>' +
      '<div class="entity-card-st-row"><span class="entity-card-st-lbl">Sisa ekuitas</span><span class="entity-card-st-val ' + eqCls + '">' + eqStr + '</span></div>' +
      '</div>';
  }).join('');
}

async function loadStressTest() {
  try {
    const user = AUTH.getUser();
    const scopedId = (user && (user.role === 'pakd' || user.role === 'kustodian') && user.entity_id) ? user.entity_id : '';
    const res = await apiFetch('/api/stress-test' + (scopedId ? ('?pakd_id=' + scopedId) : ''));
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const json = await res.json();
    const p50 = json.pasal50;
    const p91 = json.pasal91;
    const ethPrice = json.eth_price_idr;
    const btcPrice = json.btc_price_idr || 0;
    const solPrice = json.sol_price_idr || 0;

    var bannerEl = document.getElementById('st-alert-banner');
    var bannerTextEl = document.getElementById('st-alert-text');
    var failedP50 = (p50.severe.per_pakd || []).filter(function(p) { return !p.lulus; }).map(function(p) { return p.nama; });
    var failedP91sv = (p91.severe.per_pakd || []).filter(function(p) { return !p.lulus; });
    var parts = [];
    if (failedP50.length > 0) parts.push(failedP50.join(', ') + ' tidak memenuhi ekuitas minimum pada skenario pasar severe (−80%)');
    if (failedP91sv.length > 0 && failedP91sv.length === p91.severe.total) parts.push('seluruh PAKD tidak mampu mengkompensasi kehilangan total AKD konsumen (skenario Mt. Gox)');
    else if (failedP91sv.length > 0) parts.push(failedP91sv.map(function(p){return p.nama;}).join(', ') + ' tidak mampu mengkompensasi kehilangan total AKD konsumen');
    if (parts.length > 0) {
      bannerEl.style.display = 'flex';
      bannerTextEl.innerHTML = '<strong>Perhatian pengawas:</strong> ' + escapeHtml(parts.join('. ')) + '. Tindak lanjut diperlukan.';
    } else {
      bannerEl.style.display = 'none';
    }

    document.getElementById('stress-price-note').innerHTML =
      'ETH ' + formatIDR(ethPrice) + ' · BTC ' + formatIDR(btcPrice) + ' · SOL ' + formatIDR(solPrice) + ' · Basis: ' + p50.mild.total + ' PAKD';
    var riskCount = {}; var riskNames = {};
    ['mild','moderate','severe'].forEach(function(k) {
      (p50[k].per_pakd||[]).forEach(function(p){if(!p.lulus){riskCount[p.id]=(riskCount[p.id]||0)+1;riskNames[p.id]=p.nama;}});
      (p91[k].per_pakd||[]).forEach(function(p){if(!p.lulus){riskCount[p.id]=(riskCount[p.id]||0)+1;riskNames[p.id]=p.nama;}});
    });
    var highRisk = Object.keys(riskCount).filter(function(id){return riskCount[id]>=2;});
    document.getElementById('st-kpi-high-risk').textContent = highRisk.length + '/' + p50.mild.total;
    document.getElementById('st-kpi-high-risk-sub').textContent = highRisk.length > 0 ? 'gagal di 2+ skenario' : 'semua PAKD dalam batas aman';
    renderChips('kpi-chips-high-risk', highRisk.map(function(id){return {lulus:false,nama:riskNames[id]};}), false);

    document.getElementById('st-kpi-p50-severe').textContent = p50.severe.lulus + '/' + p50.severe.total;
    document.getElementById('st-kpi-p91-moderate').textContent = p91.moderate.lulus + '/' + p91.moderate.total;
    document.getElementById('st-kpi-p91-severe').textContent = p91.severe.lulus + '/' + p91.severe.total;
    renderChips('kpi-chips-p50-severe', p50.severe.per_pakd, false);
    renderChips('kpi-chips-p91-moderate', p91.moderate.per_pakd, false);
    renderChips('kpi-chips-p91-severe', p91.severe.per_pakd, false);

    [['mild','var(--green)'],['moderate','var(--amber)'],['severe','var(--red)']].forEach(function(pair) {
      var key = pair[0]; var color = pair[1];
      var row = document.getElementById('stress-' + key);
      var bar = row.querySelector('.stress-bar');
      var count = row.querySelector('.stress-count');
      var pct = p50[key].total > 0 ? p50[key].lulus / p50[key].total * 100 : 0;
      bar.style.width = pct + '%';
      count.innerHTML = p50[key].lulus + '/' + p50[key].total + '<span style="font-size:9px;color:var(--txt3)"> lulus</span>';
      count.style.color = color;
      var subEl = document.getElementById('p50-' + key + '-sub');
      if (subEl) subEl.innerHTML = 'ETH <span style="color:var(--txt1)">' + formatIDR(p50[key].eth_stressed) + '</span> · BTC <span style="color:var(--txt1)">' + formatIDR(p50[key].btc_stressed) + '</span> · SOL <span style="color:var(--txt1)">' + formatIDR(p50[key].sol_stressed) + '</span>';
      renderChips('p50-chips-' + key, p50[key].per_pakd, true);
    });

    var noteEl = document.getElementById('stress-note');
    if (p50.severe.gagal > 0) {
      var names50 = (p50.severe.per_pakd || []).filter(function(p){return !p.lulus;}).map(function(p){return p.nama;}).join(', ');
      noteEl.style.borderLeftColor = 'var(--amber)'; noteEl.style.color = 'var(--amber)';
      noteEl.textContent = '⚠ ' + names50 + ' tidak memenuhi ekuitas minimum Rp 50 miliar (POJK 23 Tahun 2025, Pasal 50) pada skenario severe (−80%).';
    } else {
      noteEl.style.borderLeftColor = 'var(--green)'; noteEl.style.color = 'var(--green)';
      noteEl.textContent = '✓ Seluruh PAKD memenuhi ekuitas minimum Rp 50 miliar pada semua skenario Pasal 50.';
    }

    [['mild','var(--green)'],['moderate','var(--amber)'],['severe','var(--red)']].forEach(function(pair) {
      var key = pair[0]; var color = pair[1];
      var row = document.getElementById('p91-' + key);
      var bar = row.querySelector('.stress-bar');
      var count = row.querySelector('.stress-count');
      var pct = p91[key].total > 0 ? p91[key].lulus / p91[key].total * 100 : 0;
      bar.style.width = pct + '%';
      count.innerHTML = p91[key].lulus + '/' + p91[key].total + '<span style="font-size:9px;color:var(--txt3)"> lulus</span>';
      count.style.color = color;
      renderP91Cards('p91-cards-' + key, p91[key].per_pakd);
    });

    var p91noteEl = document.getElementById('p91-note');
    if (p91.severe.gagal > 0) {
      var names91 = (p91.severe.per_pakd || []).filter(function(p){return !p.lulus;}).map(function(p){return p.nama;}).join(', ');
      p91noteEl.style.borderLeftColor = 'var(--red)'; p91noteEl.style.color = 'var(--red)';
      p91noteEl.textContent = '⚠ ' + names91 + ' tidak mampu mengkompensasi kehilangan total AKD konsumen (skenario Mt. Gox). Evaluasi cadangan ekuitas diperlukan sesuai POJK 23 Tahun 2025.';
    } else {
      p91noteEl.style.borderLeftColor = 'var(--green)'; p91noteEl.style.color = 'var(--green)';
      p91noteEl.textContent = '✓ Seluruh PAKD memiliki ekuitas cukup untuk menanggung skenario kehilangan AKD severe.';
    }

    // Cyber 30/70
    const c37 = json.cyber_3070;
    if (c37) {
      [['pakd_only','cyber3070-pakd','cyber3070-chips-pakd','var(--amber)'],
       ['kustodian_only','cyber3070-kustodian','cyber3070-chips-kustodian','var(--amber)'],
       ['both','cyber3070-both','cyber3070-chips-both','var(--red)']].forEach(function(t) {
        var d = c37[t[0]];
        if (!d) return;
        var row = document.getElementById(t[1]);
        var bar = row.querySelector('.stress-bar');
        var count = row.querySelector('.stress-count');
        var pct = d.total > 0 ? d.lulus / d.total * 100 : 0;
        bar.style.width = pct + '%';
        count.innerHTML = d.lulus + '/' + d.total + '<span style="font-size:9px;color:var(--txt3)"> lulus</span>';
        count.style.color = t[3];
        renderChips(t[2], d.per_pakd, true);
      });
      var c37note = document.getElementById('cyber3070-note');
      var pakdOnly = c37.pakd_only;
      var kustOnly = c37.kustodian_only;
      if (pakdOnly && kustOnly && pakdOnly.lulus > kustOnly.lulus) {
        c37note.style.borderLeftColor = 'var(--green)'; c37note.style.color = 'var(--green)';
        c37note.textContent = '✓ Segregasi penempatan AKD pada kustodian efektif: breach di PAKD saja memiliki dampak lebih kecil dibanding breach di Kustodian.';
      } else if (pakdOnly && kustOnly && pakdOnly.gagal === 0 && kustOnly.gagal === 0) {
        c37note.style.borderLeftColor = 'var(--green)'; c37note.style.color = 'var(--green)';
        c37note.textContent = '✓ Seluruh PAKD tahan terhadap breach tunggal (PAKD atau Kustodian).';
      } else {
        c37note.style.borderLeftColor = 'var(--amber)'; c37note.style.color = 'var(--amber)';
        c37note.textContent = '⚠ Beberapa PAKD rentan terhadap breach tunggal. Evaluasi segregasi aset diperlukan.';
      }
    }
  } catch (err) {
    document.getElementById('stress-note').textContent = 'Gagal memuat stress test: ' + err.message;
  }
}

const WALLET_RE = {
  ethereum: /^0x[0-9a-fA-F]{40}$/,
  bitcoin:  /^(bc1[a-zA-Z0-9]{6,87}|[13][a-km-zA-HJ-NP-Z0-9]{25,34})$/,
  solana:   /^[1-9A-HJ-NP-Za-km-z]{32,44}$/,
};
const WALLET_PLACEHOLDER = {
  ethereum: '0x...',
  bitcoin:  'bc1q... atau 1... atau 3...',
  solana:   '5K... (base58, 32-44 karakter)',
};
let walletRowCount = 0;

function addWalletRow(defaultNetwork = 'ethereum') {
  const container = document.getElementById('wallet-rows');
  const idx = walletRowCount++;
  const row = document.createElement('div');
  row.id = 'wrow-' + idx;
  row.style.cssText = 'display:grid;grid-template-columns:140px 1fr auto;gap:8px;align-items:center;margin-bottom:6px';
  row.innerHTML = ` 
    <select id="wnet-${idx}" class="form-input" onchange="updateWalletPlaceholder(${idx})" style="font-size:13px;padding:9px 12px">
      <option value="ethereum"${defaultNetwork==='ethereum'?' selected':''}>Ethereum</option>
      <option value="bitcoin"${defaultNetwork==='bitcoin'?' selected':''}>Bitcoin</option>
      <option value="solana"${defaultNetwork==='solana'?' selected':''}>Solana</option>
    </select>
    <input id="waddr-${idx}" class="form-input mono" type="text" placeholder="${WALLET_PLACEHOLDER[defaultNetwork]}" style="font-size:11px">
    <button onclick="removeWalletRow(${idx})" style="background:var(--red-bg);border:1px solid var(--red-border);color:var(--red);font-size:11px;padding:7px 10px;border-radius:var(--r);cursor:pointer">✕</button>
  `;
  container.appendChild(row);
}

function removeWalletRow(idx) {
  const row = document.getElementById('wrow-' + idx);
  if (row) row.remove();
}

function updateWalletPlaceholder(idx) {
  const net = document.getElementById('wnet-' + idx).value;
  document.getElementById('waddr-' + idx).placeholder = WALLET_PLACEHOLDER[net] || '...';
}

function collectWallets() {
  const rows = document.querySelectorAll('[id^="wrow-"]');
  if (rows.length === 0) return { wallets: null, err: 'Tambahkan minimal satu wallet address.' };
  const wallets = [];
  for (const row of rows) {
    const idx = row.id.replace('wrow-', '');
    const network = document.getElementById('wnet-' + idx).value;
    const address = document.getElementById('waddr-' + idx).value.trim();
    if (!address) return { wallets: null, err: 'Semua baris wallet harus diisi.' };
    if (!WALLET_RE[network] || !WALLET_RE[network].test(address))
      return { wallets: null, err: 'Alamat tidak valid untuk network ' + network + ': ' + address };
    wallets.push({ network, address });
  }
  return { wallets, err: null };
}

function resetForm() {
  ['f-nama','f-id','f-aset'].forEach(fid => { const el = document.getElementById(fid); if (el) el.value = ''; });
  document.getElementById('wallet-rows').innerHTML = '';
  walletRowCount = 0;
  addWalletRow('ethereum');
}

async function submitManual() {
  const nama = document.getElementById('f-nama').value.trim();
  const id   = document.getElementById('f-id').value.trim();
  const aset = parseInt(document.getElementById('f-aset').value) || 0;
  const msg  = document.getElementById('form-msg');
  const { wallets, err: walletErr } = collectWallets();
  if (!nama || !id) {
    msg.style.display = 'block'; msg.style.background = 'var(--red-bg)'; msg.style.color = 'var(--red)';
    msg.textContent = 'Nama dan ID PAKD wajib diisi.'; return;
  }
  if (walletErr) {
    msg.style.display = 'block'; msg.style.background = 'var(--red-bg)'; msg.style.color = 'var(--red)';
    msg.textContent = walletErr; return;
  }
  try {
    const res = await apiFetch('/api/input-manual', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        nama,
        id,
        wallets,
        aset_dilaporkan: aset,
        ...(document.getElementById('f-equity').value    ? {equity_idr:                 parseInt(document.getElementById('f-equity').value)}    : {}),
        ...(document.getElementById('f-persediaan').value ? {persediaan_akd_idr:         parseInt(document.getElementById('f-persediaan').value)} : {}),
        ...(document.getElementById('f-simpanan').value   ? {simpanan_pedagang_akd_idr:  parseInt(document.getElementById('f-simpanan').value)}   : {}),
        ...(document.getElementById('f-customer').value   ? {customer_akd_idr:           parseInt(document.getElementById('f-customer').value)}   : {}),
      })
    });
    const json = await res.json();
    if (!res.ok) {
      msg.style.background = 'var(--red-bg)'; msg.style.color = 'var(--red)'; msg.textContent = json.message;
    } else {
      msg.style.background = 'var(--green-bg)'; msg.style.color = 'var(--green)';
      msg.textContent = json.message + ' - rekonsiliasi diperbarui.';
      resetForm(); loadAll();
    }
    msg.style.display = 'block';
  } catch (err) {
    msg.style.background = 'var(--red-bg)'; msg.style.color = 'var(--red)';
    msg.style.display = 'block'; msg.textContent = 'Gagal menghubungi server: ' + err.message;
  }
}

async function loadAudit() {
  const tbody = document.getElementById('audit-tbody');
  try {
    const res = await apiFetch('/api/audit-log');
    const json = await res.json();
    if (!json.data.length) {
      tbody.innerHTML = '<tr class="loading-row"><td colspan="4">Belum ada aktivitas tercatat.</td></tr>'; return;
    }
    tbody.innerHTML = json.data.map(log => {
      const aktor = log.aktor
        ? `<span style="color:var(--txt2)">${escapeHtml(log.aktor)}</span>${log.aktor_role ? `<br><span style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--txt3)">${escapeHtml(log.aktor_role)}</span>` : ''}`
        : '<span style="color:var(--txt4)">—</span>';
      return `
      <tr>
        <td class="mono-val" style="color:var(--txt3);white-space:nowrap">${log.waktu}</td>
        <td><span style="font-family:'JetBrains Mono',monospace;font-size:11px;padding:3px 10px;border-radius:4px;background:var(--blue-bg);color:var(--blue);border:1px solid var(--blue-border);font-weight:600">${log.aksi}</span></td>
        <td style="white-space:nowrap">${aktor}</td>
        <td style="color:var(--txt2)">${escapeHtml(log.detail)}</td>
      </tr>`;
    }).join('');
    applyRoleUI();
  } catch(e) {
    tbody.innerHTML = '<tr class="loading-row"><td colspan="4">Gagal memuat audit log.</td></tr>';
  }
}

function renderBreakdown(d) {
  const parts = [];
  if (d.eth_balance_idr > 0) {
    let s = `<div style="margin-bottom:3px"><span style="color:var(--blue);font-family:'JetBrains Mono',monospace;font-size:9px;margin-right:4px;letter-spacing:0.05em">ETH</span>`;
    s += `<span style="color:var(--txt2)">${formatIDR(d.eth_native_idr)}</span>`;
    if (d.eth_usdt_idr > 0) s += `<span style="color:var(--txt3)"> · USDT ${formatIDR(d.eth_usdt_idr)}</span>`;
    if (d.eth_usdc_idr > 0) s += `<span style="color:var(--txt3)"> · USDC ${formatIDR(d.eth_usdc_idr)}</span>`;
    if (d.eth_other_token_idr > 0) s += `<span style="color:var(--txt3)"> · OTHER ${formatIDR(d.eth_other_token_idr)}</span>`;
    if (d.eth_unvalued_count > 0) s += `<span style="color:var(--amber);font-size:9px;margin-left:4px" title="Token terdeteksi tanpa harga di CoinGecko">⚠ ${d.eth_unvalued_count} unvalued</span>`;
    parts.push(s + '</div>');
  }
  if (d.btc_balance_idr > 0) {
    parts.push(`<div style="margin-bottom:3px"><span style="color:var(--amber);font-family:'JetBrains Mono',monospace;font-size:9px;margin-right:4px;letter-spacing:0.05em">BTC</span><span style="color:var(--txt2)">${formatIDR(d.btc_balance_idr)}</span></div>`);
  }
  if (d.sol_balance_idr > 0) {
    let s = `<div><span style="color:var(--green);font-family:'JetBrains Mono',monospace;font-size:9px;margin-right:4px;letter-spacing:0.05em">SOL</span>`;
    s += `<span style="color:var(--txt2)">${formatIDR(d.sol_native_idr)}</span>`;
    if (d.sol_usdt_idr > 0) s += `<span style="color:var(--txt3)"> · USDT ${formatIDR(d.sol_usdt_idr)}</span>`;
    if (d.sol_usdc_idr > 0) s += `<span style="color:var(--txt3)"> · USDC ${formatIDR(d.sol_usdc_idr)}</span>`;
    if (d.sol_other_token_idr > 0) s += `<span style="color:var(--txt3)"> · OTHER ${formatIDR(d.sol_other_token_idr)}</span>`;
    if (d.sol_unvalued_count > 0) s += `<span style="color:var(--amber);font-size:9px;margin-left:4px" title="Mint terdeteksi tanpa harga di Jupiter">⚠ ${d.sol_unvalued_count} unvalued</span>`;
    parts.push(s + '</div>');
  }
  return parts.length ? parts.join('') : '<span style="color:var(--txt4)">—</span>';
}

const CHAIN_LABEL = { ethereum: 'ETH', bitcoin: 'BTC', solana: 'SOL' };
const CHAIN_CSS   = { ethereum: 'eth', bitcoin: 'btc', solana: 'sol' };
const PROOF_SUPPORTED = new Set(['ethereum', 'solana', 'bitcoin']);

function shortAddr(a) {
  if (!a) return '';
  return a.length > 14 ? a.slice(0, 8) + '…' + a.slice(-6) : a;
}

function chainTagHtml(network) {
  const label = CHAIN_LABEL[network] || network.toUpperCase();
  const cls   = CHAIN_CSS[network]   || 'eth';
  return `<span class="wallet-chain-tag ${cls}">${label}</span>`;
}

function formatVerifyTimestamp(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: '2-digit' });
  } catch (e) { return ''; }
}

function verifyBadgeHtml(wallet) {
  if (wallet.verified) {
    const ts = formatVerifyTimestamp(wallet.verified_at);
    const title = wallet.verified_at ? `Diverifikasi ${wallet.verified_at}` : 'Verified';
    return `<span class="verify-badge verified" title="${escapeAttr(title)}">✓ Verified${ts ? ' ' + ts : ''}</span>`;
  }
  if (!PROOF_SUPPORTED.has(wallet.network)) {
    return `<span class="verify-badge unsupported" title="Proof of ownership untuk network ini belum diimplementasikan">N/A</span>`;
  }
  return `<span class="verify-badge unverified">Unverified</span>`;
}

function escapeAttr(s) {
  if (s === null || s === undefined) return "";
  return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function render3070Badge(d) {
  if (!d.has_kustodian) return '<span class="badge-na">N/A</span>';
  if (d.compliance_30_70) return '<span class="badge-compliant">✓ COMPLIANT</span>';
  const pct = d.ratio_at_pakd != null ? (d.ratio_at_pakd * 100).toFixed(1) + '% di PAKD' : '';
  return '<span class="badge-violation">✗ VIOLATION</span>' + (pct ? '<div style="font-size:9px;color:var(--red);margin-top:2px">' + pct + '</div>' : '');
}

const FETCH_STATUS_LABEL = {sukses: 'Sukses', partial: 'Partial', gagal: 'Gagal'};

function renderWalletsCell(d) {
  if (!d.wallets || !d.wallets.length) return '';
  // T2.3 (D6): d.breakdown adalah hasil fetch per-wallet (punya fetch_status);
  // d.wallets adalah konfigurasi mentah. Dipetakan sekali di sini, bukan
  // per-wallet di dalam .map(), supaya lookup-nya O(1) per wallet.
  const breakdownByKey = {};
  (d.breakdown || []).forEach(e => { breakdownByKey[e.address + '|' + e.network] = e; });
  return d.wallets.map(w => {
    const canVerify = PROOF_SUPPORTED.has(w.network) && !w.verified;
    const action = canVerify
      ? `<button class="verify-mini-btn" onclick="openVerifyModal('${escapeAttr(w.address)}','${w.network}','${escapeAttr(d.id)}')">Verify</button>`
      : '';
    // Tanpa entry padanan (PAKD belum pernah direkonsiliasi), tidak ada
    // badge status yang dirender -- bukan default ke salah satu nilai.
    const matchedEntry = breakdownByKey[w.address + '|' + w.network];
    const fetchStatusBadge = (matchedEntry && matchedEntry.fetch_status)
      ? `<span class="fetch-status-badge ${matchedEntry.fetch_status}">${FETCH_STATUS_LABEL[matchedEntry.fetch_status] || matchedEntry.fetch_status}</span>`
      : '';
    return `<div class="wallet-mini-row" data-addr="${escapeAttr(w.address)}" data-net="${w.network}">${chainTagHtml(w.network)}<span class="wallet-addr" title="${escapeAttr(w.address)}">${shortAddr(w.address)}</span>${fetchStatusBadge}${verifyBadgeHtml(w)}${action}</div>`;
  }).join('');
}

function renderWalletToggle(d) {
  const count = (d.wallets || []).length;
  if (!count) return '';
  return `<button class="wallet-toggle-btn" data-label="${count} wallet" onclick="toggleWalletBreakdown(this)" style="background:none;border:1px solid var(--border);border-radius:6px;padding:2px 8px;font-size:10px;color:var(--txt3);cursor:pointer;margin-top:4px">&#9656; ${count} wallet</button>
    <div class="wallet-breakdown-panel" style="display:none;margin-top:4px">${renderWalletsCell(d)}</div>`;
}

function toggleWalletBreakdown(btn) {
  const panel = btn.nextElementSibling;
  const open = panel.style.display === 'none';
  panel.style.display = open ? 'block' : 'none';
  btn.innerHTML = (open ? '&#9662; ' : '&#9656; ') + btn.dataset.label;
}

function toggleAllWalletBreakdowns() {
  const btn = document.getElementById('expand-all-btn');
  const shouldOpen = btn.dataset.state !== 'open';
  document.querySelectorAll('.wallet-breakdown-panel').forEach(p => { p.style.display = shouldOpen ? 'block' : 'none'; });
  document.querySelectorAll('.wallet-toggle-btn').forEach(b => { b.innerHTML = (shouldOpen ? '&#9662; ' : '&#9656; ') + b.dataset.label; });
  btn.dataset.state = shouldOpen ? 'open' : 'closed';
  btn.innerHTML = shouldOpen ? '&#9662; Collapse semua' : '&#9656; Expand semua';
}

let modalState = { address: null, network: null, pakdId: null, challenge: null };
let modalOpenSeq = 0; // guards against stale in-flight challenge responses after close/reopen

function onModalBackdrop(ev) {
  if (ev.target && ev.target.id === 'verify-modal') closeVerifyModal();
}

function modalShowError(msg) {
  const el = document.getElementById('verify-modal-error');
  el.textContent = msg;
  el.style.display = 'block';
}

function modalClearError() {
  document.getElementById('verify-modal-error').style.display = 'none';
}

function setModalSubmitState(disabled, label) {
  const btn = document.getElementById('verify-modal-submit');
  btn.disabled = disabled;
  if (label !== undefined) btn.textContent = label;
}

async function openVerifyModal(address, network, pakdId) {
  const mySeq = ++modalOpenSeq;
  modalState = { address, network, pakdId, challenge: null };
  const modal = document.getElementById('verify-modal');
  document.getElementById('verify-modal-sub').textContent = `${(CHAIN_LABEL[network] || network)} · ${address}`;
  document.getElementById('verify-modal-challenge').value = 'Mengambil challenge dari server...';
  document.getElementById('verify-modal-signature').value = '';
  const sigHint = document.getElementById('verify-modal-sig-hint');
  if (network === 'ethereum') {
    sigHint.textContent = 'Ethereum (EIP-191): hex 0x... panjang 132 karakter, hasil personal_sign / MetaMask eth_sign.';
  } else if (network === 'bitcoin') {
    sigHint.textContent = 'Bitcoin (legacy P2PKH, alamat diawali "1"): base64, hasil Bitcoin Signed Message (Electrum Sign/Verify Message atau bitcoin-cli signmessage). Alamat P2WPKH/P2SH/P2TR belum didukung.';
  } else {
    sigHint.textContent = 'Solana (Ed25519): hex 128 karakter atau base64, hasil signMessage Phantom / wallet adapter.';
  }
  setupMetaMaskUI(network);
  modalClearError();
  setModalSubmitState(true, 'Verifikasi');
  modal.classList.add('show');

  try {
    const res = await apiFetch('/api/wallet-challenge', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address, network })
    });
    const json = await res.json();
    if (mySeq !== modalOpenSeq) return; // modal was closed/reopened; discard stale challenge
    if (!res.ok) {
      document.getElementById('verify-modal-challenge').value = '';
      modalShowError(json.message || 'Gagal mengambil challenge.');
      return;
    }
    modalState.challenge = json.challenge;
    document.getElementById('verify-modal-challenge').value = json.challenge;
    if (json.instruction) {
      document.getElementById('verify-modal-instruction').textContent = json.instruction;
    }
    setModalSubmitState(false, 'Verifikasi');
    setTimeout(() => document.getElementById('verify-modal-signature').focus(), 50);
  } catch (err) {
    if (mySeq !== modalOpenSeq) return;
    document.getElementById('verify-modal-challenge').value = '';
    modalShowError('Gagal menghubungi server: ' + err.message);
  }
}

function closeVerifyModal() {
  modalOpenSeq++; // invalidate any in-flight challenge fetch
  document.getElementById('verify-modal').classList.remove('show');
  modalState = { address: null, network: null, pakdId: null, challenge: null };
  // Clear stale nonce/signature so a reopen never shows an expired challenge
  document.getElementById('verify-modal-challenge').value = '';
  document.getElementById('verify-modal-signature').value = '';
  modalClearError();
  setModalSubmitState(true, 'Verifikasi');
}

function markWalletVerifiedLocally(address, network) {
  const now = new Date().toISOString();
  if (Array.isArray(_pakdCache)) {
    _pakdCache.forEach(p => (p.wallets || []).forEach(w => {
      if (w.address === address && (!network || w.network === network)) {
        w.verified = true; w.verified_at = now;
      }
    }));
  }
  document.querySelectorAll('.wallet-mini-row').forEach(row => {
    if (row.getAttribute('data-addr') === address &&
        (!network || row.getAttribute('data-net') === network)) {
      const badge = row.querySelector('.verify-badge');
      if (badge) { badge.className = 'verify-badge verified'; badge.textContent = '\u2713 Verified'; }
      const btn = row.querySelector('.verify-mini-btn');
      if (btn) btn.remove();
    }
  });
}

async function submitVerifyFromModal() {
  const signature = document.getElementById('verify-modal-signature').value.trim();
  if (!signature) {
    modalShowError('Tempel signature dari PAKD terlebih dahulu.');
    return;
  }
  if (!modalState.challenge) {
    modalShowError('Challenge belum siap. Tunggu sampai challenge text muncul.');
    return;
  }
  modalClearError();
  setModalSubmitState(true, 'Memverifikasi...');
  try {
    const res = await apiFetch('/api/wallet-verify', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        address:   modalState.address,
        signature,
        pakd_id:   modalState.pakdId,
      })
    });
    const json = await res.json();
    if (json.verified) {
      markWalletVerifiedLocally(modalState.address, modalState.network);
      closeVerifyModal();
      loadAudit();
    } else {
      modalShowError(json.message || 'Verifikasi gagal.');
      setModalSubmitState(false, 'Verifikasi');
    }
  } catch (err) {
    modalShowError('Gagal menghubungi server: ' + err.message);
    setModalSubmitState(false, 'Verifikasi');
  }
}

function setupMetaMaskUI(network) {
  const btn      = document.getElementById('verify-modal-mm-btn');
  const status   = document.getElementById('verify-modal-mm-status');
  const divider  = document.getElementById('verify-modal-mm-divider');
  if (network !== 'ethereum') {
    btn.style.display = 'none';
    status.style.display = 'none';
    divider.style.display = 'none';
    return;
  }
  btn.style.display = 'block';
  status.style.display = 'block';
  divider.style.display = 'flex';
  if (typeof window.ethereum === 'undefined') {
    btn.disabled = true;
    btn.textContent = 'MetaMask tidak terdeteksi';
    status.textContent = 'Install MetaMask atau gunakan paste manual di bawah.';
  } else {
    btn.disabled = false;
    btn.textContent = 'Sign with MetaMask';
    status.textContent = 'MetaMask terdeteksi. Pastikan account aktif sesuai address yang diverifikasi.';
  }
}

async function signWithMetaMask() {
  modalClearError();
  if (typeof window.ethereum === 'undefined') {
    modalShowError('MetaMask tidak terdeteksi di browser ini.');
    return;
  }
  if (!modalState.challenge) {
    modalShowError('Challenge belum siap. Tunggu sampai challenge text muncul.');
    return;
  }
  const btn = document.getElementById('verify-modal-mm-btn');
  const status = document.getElementById('verify-modal-mm-status');
  const originalLabel = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Menunggu MetaMask...';
  status.textContent = 'Buka MetaMask popup dan setujui signature request.';
  try {
    const chainId = await window.ethereum.request({ method: 'eth_chainId' });
    if (chainId !== '0x1') {
      modalShowError('MetaMask aktif di chain ' + chainId + ' (bukan Ethereum Mainnet 0x1). Switch ke Ethereum Mainnet di MetaMask, lalu klik Sign with MetaMask lagi.');
      btn.disabled = false;
      btn.textContent = originalLabel;
      status.textContent = 'MetaMask terdeteksi. Switch ke Ethereum Mainnet sebelum sign.';
      return;
    }
    const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' });
    if (!accounts || accounts.length === 0) {
      modalShowError('Tidak ada account aktif di MetaMask.');
      btn.disabled = false;
      btn.textContent = originalLabel;
      return;
    }
    const activeAccount = accounts[0].toLowerCase();
    const targetAddress = modalState.address.toLowerCase();
    if (activeAccount !== targetAddress) {
      modalShowError('Account aktif di MetaMask (' + accounts[0] + ') tidak match dengan address yang diverifikasi (' + modalState.address + '). Switch account di MetaMask, lalu klik Sign with MetaMask lagi.');
      btn.disabled = false;
      btn.textContent = originalLabel;
      status.textContent = 'MetaMask terdeteksi. Pastikan account aktif sesuai address yang diverifikasi.';
      return;
    }
    const signature = await window.ethereum.request({
      method: 'personal_sign',
      params: [modalState.challenge, modalState.address],
    });
    document.getElementById('verify-modal-signature').value = signature;
    status.textContent = 'Signature diterima. Mengirim ke server...';
    await submitVerifyFromModal();
  } catch (err) {
    if (err && err.code === 4001) {
      modalShowError('Anda menolak signature di MetaMask. Coba lagi atau gunakan paste manual.');
    } else if (err && err.code === 4900) {
      modalShowError('MetaMask disconnected. Pastikan extension aktif dan unlock vault.');
    } else {
      modalShowError('Gagal sign dengan MetaMask: ' + (err.message || 'unknown error'));
    }
    btn.disabled = false;
    btn.textContent = originalLabel;
    status.textContent = 'MetaMask terdeteksi. Pastikan account aktif sesuai address yang diverifikasi.';
  }
}


function copyChallengeFromModal() {
  const text = document.getElementById('verify-modal-challenge').value;
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.getElementById('verify-modal-copy');
    btn.classList.add('copied');
    btn.textContent = 'Tersalin';
    setTimeout(() => {
      btn.classList.remove('copied');
      btn.textContent = 'Salin Challenge';
    }, 1600);
  }).catch(() => {
    const ta = document.getElementById('verify-modal-challenge');
    ta.select();
    document.execCommand('copy');
  });
}

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape' && document.getElementById('verify-modal').classList.contains('show')) {
    closeVerifyModal();
  }
});

function clearVpChallenge() {
  // Stale nonces expire server-side after 5 minutes; never leave one displayed
  document.getElementById('vp-challenge-text').value = '';
  document.getElementById('vp-challenge-box').style.display = 'none';
  document.getElementById('vp-verify-box').style.display = 'none';
}
// A displayed challenge no longer matches server state once address/network changes
(function() {
  const vpAddr = document.getElementById('vp-address');
  const vpNet  = document.getElementById('vp-network');
  if (vpAddr) vpAddr.addEventListener('input', clearVpChallenge);
  if (vpNet)  vpNet.addEventListener('change', clearVpChallenge);
})();

async function requestChallenge() {
  const network = document.getElementById('vp-network').value;
  const address = document.getElementById('vp-address').value.trim();
  document.getElementById('vp-result').style.display = 'none';
  clearVpChallenge();
  if (!address) { showVpResult(false, 'Isi wallet address terlebih dahulu.'); return; }
  document.getElementById('vp-challenge-text').value = 'Mengambil challenge dari server...';
  try {
    const res = await apiFetch('/api/wallet-challenge', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ address, network })
    });
    const json = await res.json();
    if (!res.ok) { clearVpChallenge(); showVpResult(false, json.message); return; }
    document.getElementById('vp-challenge-text').value = json.challenge;
    document.getElementById('vp-challenge-box').style.display = 'block';
    document.getElementById('vp-verify-box').style.display = 'block';
  } catch (err) {
    clearVpChallenge();
    showVpResult(false, 'Gagal menghubungi server: ' + err.message);
  }
}

async function verifyChallenge() {
  const address   = document.getElementById('vp-address').value.trim();
  const signature = document.getElementById('vp-signature').value.trim();
  const pakd_id   = document.getElementById('vp-pakd-id').value.trim();
  if (!signature) { showVpResult(false, 'Isi signature dari PAKD.'); return; }
  try {
    const res = await apiFetch('/api/wallet-verify', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ address, signature, pakd_id })
    });
    const json = await res.json();
    if (json.verified) {
      showVpResult(true, '✓ ' + json.message);
      document.getElementById('vp-challenge-box').style.display = 'none';
      document.getElementById('vp-verify-box').style.display = 'none';
      if (json.address) markWalletVerifiedLocally(json.address, null);
      loadAudit();
    } else {
      showVpResult(false, '✗ ' + (json.message || 'Verifikasi gagal.'));
    }
  } catch (err) {
    showVpResult(false, 'Gagal menghubungi server: ' + err.message);
  }
}

function showVpResult(success, message) {
  const el = document.getElementById('vp-result');
  el.style.display = 'block';
  el.style.background = success ? 'var(--green-bg)' : 'var(--red-bg)';
  el.style.border = success ? '1px solid var(--green-border)' : '1px solid var(--red-border)';
  el.style.color = success ? 'var(--green)' : 'var(--red)';
  el.textContent = message;
}

async function loadPengaturan() {
  try {
    const resp = await fetch('/api/status');
    const data = await resp.json();
    document.getElementById('versi-sistem').textContent = data.versi || 'N/A';
  } catch (e) {
    document.getElementById('versi-sistem').textContent = 'Tidak dapat dijangkau';
  }
}

function renderWalletBadges(d) {
  if (!d.wallets || d.wallets.length === 0) return '<span style="font-size:11px;color:var(--txt3)">—</span>';
  return d.wallets.map(function(w) {
    var ch = (w.network || 'ETH').toLowerCase().replace('ethereum','eth').replace('bitcoin','btc').replace('solana','sol');
    var cls = ch === 'btc' ? 'btc' : ch === 'sol' ? 'sol' : 'eth';
    var lbl = ch === 'btc' ? 'BTC' : ch === 'sol' ? 'SOL' : 'ETH';
    var dot = w.verified
      ? '<span style="font-size:9px;color:var(--green);margin-left:2px">&#10003;</span>'
      : '<span style="font-size:9px;color:var(--red);margin-left:2px">!</span>';
    return '<span class="wallet-chain-tag ' + cls + '" style="display:inline-block;margin-bottom:3px">' + lbl + '</span>' + dot;
  }).join(' ');
}
function toggleDetail(id) {
  var row = document.getElementById(id);
  if (!row) return;
  var isOpen = row.style.display !== 'none';
  row.style.display = isOpen ? 'none' : 'table-row';
  var icon = document.getElementById('icon-' + id);
  if (icon) icon.textContent = isOpen ? '▼' : '▲';
}
async function triggerManualRefresh() {
  const btn = document.querySelector('button.btn-primary[onclick="triggerManualRefresh()"]');
  const tbody = document.getElementById('pakd-tbody');
  if (btn) { btn.disabled = true; btn.textContent = 'Memuat...'; }
  const pakdList = (_pakdCache && _pakdCache.length) ? _pakdCache.map(d => ({id: d.id, nama: d.nama})) : [];
  if (!pakdList.length) {
    tbody.innerHTML = '<tr class="loading-row"><td colspan="8">Data PAKD belum dimuat. Muat ulang halaman.</td></tr>';
    if (btn) { btn.disabled = false; btn.textContent = '\u27F3 Rekonsiliasi Manual'; }
    return;
  }
  async function pollJob(job_id, label) {
    return new Promise((resolve) => {
      let attempts = 0;
      const poll = setInterval(async () => {
        attempts++;
        try {
          const r = await apiFetch('/api/reconciliation/refresh/' + job_id);
          const job = await r.json();
          if (job.status === 'done' || job.status === 'failed') {
            clearInterval(poll);
            resolve(job.status);
          } else {
            tbody.innerHTML = '<tr class="loading-row"><td colspan="8">Rekonsiliasi ' + escapeHtml(label) + '... (' + attempts * 2 + 's)</td></tr>';
          }
          if (attempts >= 75) { clearInterval(poll); resolve('timeout'); }
        } catch(e) { clearInterval(poll); resolve('error'); }
      }, 2000);
    });
  }
  try {
    for (let i = 0; i < pakdList.length; i++) {
      const pakd = pakdList[i];
      tbody.innerHTML = '<tr class="loading-row"><td colspan="8">(' + (i+1) + '/' + pakdList.length + ') Mengirim job untuk ' + escapeHtml(pakd.nama) + '...</td></tr>';
      const res = await apiFetch('/api/reconciliation/refresh?pakd_id=' + encodeURIComponent(pakd.id), {method: 'POST'});
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const {job_id} = await res.json();
      const result = await pollJob(job_id, '(' + (i+1) + '/' + pakdList.length + ') ' + pakd.nama);
      if (result === 'timeout' || result === 'error') {
        console.warn('Timeout/error pada ' + pakd.nama + ', lanjut ke PAKD berikutnya');
      } else if (result === 'failed') {
        console.warn('Job gagal pada ' + pakd.nama + ', lanjut ke PAKD berikutnya');
      }
    }
    await loadSnapshot();
    if (btn) { btn.disabled = false; btn.textContent = '\u27F3 Rekonsiliasi Manual'; }
  } catch(e) {
    tbody.innerHTML = '<tr class="loading-row"><td colspan="8">Gagal menghubungi server: ' + escapeHtml(e.message) + '</td></tr>';
    if (btn) { btn.disabled = false; btn.textContent = '\u27F3 Rekonsiliasi Manual'; }
  }
}


async function loadSnapshot() {
  const tbody = document.getElementById('pakd-tbody');
  tbody.innerHTML = '<tr class="loading-row"><td colspan="8">Memuat data snapshot...</td></tr>';
  try {
    const res = await apiFetch('/api/reconciliation/latest');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const json = await res.json();
    if (!json.data || json.data.length === 0) { tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#e74c3c">Snapshot kosong. Jalankan Rekonsiliasi Manual.</td></tr>'; return; }
    const statusMap = {'NORMAL':'Aman','WARNING':'Deviasi','KRITIS':'Kritis'};
    const data = json.data.map(r => {
      const nb = r.network_breakdown || [];
      const eth = nb.find(w => w.network === 'ethereum') || {};
      const btc = nb.find(w => w.network === 'bitcoin') || {};
      const sol = nb.find(w => w.network === 'solana') || {};
      return Object.assign({}, r, {
        status: statusMap[r.status] || r.status,
        deviasi_pct: Number(r.deviasi_pct) || 0,
        surplus: (Number(r.deviasi_pct) || 0) >= 0,
        breakdown: nb,
        wallets: nb,
        eth_native_idr: eth.eth_native_idr || 0,
        eth_usdt_idr: eth.usdt_idr || 0,
        eth_usdc_idr: eth.usdc_idr || 0,
        eth_other_token_idr: eth.eth_other_token_idr || 0,
        eth_unvalued_count: eth.eth_unvalued_count || 0,
        btc_balance_idr: btc.balance_idr || 0,
        sol_native_idr: sol.sol_native_idr || 0,
        sol_usdt_idr: sol.sol_usdt_idr || 0,
        sol_usdc_idr: sol.sol_usdc_idr || 0,
        sol_other_token_idr: sol.sol_other_token_idr || 0,
        sol_unvalued_count: sol.sol_unvalued_count || 0,
      });
    });
    _pakdCache = data;
    const asOf = json.as_of ? new Date(json.as_of).toLocaleString('id-ID', {day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}) : '-';
    document.getElementById('last-update').textContent = asOf + ' (snapshot)';
    document.getElementById('footer-time').textContent = 'Snapshot terakhir: ' + asOf;
    document.getElementById('live-badge').textContent = 'SNAPSHOT';
    const subtitleEl = document.getElementById('page-subtitle-overview');
    if (subtitleEl) subtitleEl.textContent = 'Data dari snapshot Supabase · Terakhir diperbarui: ' + asOf;
    const fallbackNotice = document.getElementById('eth-fallback-notice');
    if (fallbackNotice) fallbackNotice.style.display = 'none';
    const aman = data.filter(d => d.status === 'Aman').length;
    const kritis = data.filter(d => d.status === 'Kritis').length;
    const peringatan = data.filter(d => d.status === 'Deviasi').length;
    document.getElementById('kpi-aman').textContent = data.length - aman;
    document.getElementById('kpi-total-label').textContent = aman + ' entitas dalam status aman';
    const _sub = document.getElementById('kpi-alert-sub');
    if (_sub) _sub.textContent = kritis + ' kritis · ' + peringatan + ' peringatan';
    const _snap = document.getElementById('kpi-snapshot-val');
    if (_snap) { const _n = new Date(); _snap.textContent = _n.getDate() + ' ' + ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Ags','Sep','Okt','Nov','Des'][_n.getMonth()] + ' ' + _n.getFullYear() + ', ' + String(_n.getHours()).padStart(2,'0') + '.' + String(_n.getMinutes()).padStart(2,'0'); }
    document.getElementById('kpi-alert').textContent = data.length - aman;
    const defisits = data.filter(d => !d.surplus).map(d => Math.abs(d.deviasi_pct));
    document.getElementById('kpi-max-dev').textContent = defisits.length ? Math.max(...defisits).toFixed(2) + '%' : '0%';
    tbody.innerHTML = data.map((d, i) => `
      <tr style="background:${d.status==='Kritis'?'rgba(192,57,43,0.03)':d.status==='Deviasi'?'rgba(194,124,26,0.03)':''}">
        <td class="num-row" style="vertical-align:top;padding-top:18px">${String(i+1).padStart(2,'0')}</td>
        <td style="vertical-align:top;padding-top:14px;min-width:280px">
          <span class="pakd-name">${escapeHtml(d.nama)}</span>
          <span class="pakd-id">${escapeHtml(d.id)} · Berizin</span><br>
          ${renderWalletToggle(d)}
        </td>
        <td style="vertical-align:top;padding-top:18px"><span style="font-size:9px;color:var(--txt4);text-transform:uppercase;letter-spacing:0.03em">AKD Onchain</span><br>${
          d.status_indikatif
            ? ('<span class="status-badge ' + statusClass(d.status_indikatif) + '">' + escapeHtml(d.status_indikatif) + '*</span><br><span style="color:var(--txt4);font-size:11px">Data Tidak Lengkap</span>')
            : ('<span class="status-badge ' + statusClass(d.status) + '">' + d.status + '</span>')
        }<br>${deviDisplay(d)}<br><span style="font-size:9px;color:var(--txt4);text-transform:uppercase;letter-spacing:0.03em">Porsi AKD pada Kustodian</span><br>${render3070Badge(d)}</td>
        <td class="mono-val" style="color:var(--txt2);vertical-align:top;padding-top:18px">${formatIDR(d.aset_dilaporkan_idr)}</td>
        <td class="mono-val" style="color:var(--txt1);vertical-align:top;padding-top:18px">${
          d.status === 'Data Tidak Lengkap'
            ? (d.subtotal_diketahui_idr != null
                ? formatIDR(d.subtotal_diketahui_idr) + '<br><span style="color:var(--txt4);font-size:11px">parsial, cek status wallet</span>'
                : '<span style="color:var(--txt3)">\u2014</span>')
            : formatIDR(d.aset_onchain_idr_final ?? d.aset_onchain_idr)
        }</td>
        <td class="mono-val" style="color:var(--txt2);vertical-align:top;padding-top:18px">${d.has_kustodian ? (d.kustodian_onchain_status === 'terukur' ? formatIDR(d.kustodian_onchain_idr || 0) : '<span style="color:var(--txt4)">—</span>') : '<span style="color:var(--txt4)">—</span>'}</td>
        <td style="line-height:1.6;vertical-align:top;padding-top:14px">${renderBreakdown(d)}</td>
        <td style="vertical-align:top;padding-top:16px">
          <div style="display:flex;gap:6px">
            <button onclick="openEditModal('${escapeHtml(d.id)}')"
              style="background:none;border:none;cursor:pointer;color:#64748b;border-radius:6px;padding:6px 8px;transition:all 0.15s"
              onmouseover="this.style.background='#eff6ff';this.style.color='#2563eb'"
              onmouseout="this.style.background='none';this.style.color='#64748b'"
              title="Edit PAKD" class="crud-action">✏️</button>
            <button onclick="deletePakd('${escapeHtml(d.id)}')"
              style="background:none;border:none;cursor:pointer;color:#64748b;border-radius:6px;padding:6px 8px;transition:all 0.15s"
              onmouseover="this.style.background='#fef2f2';this.style.color='#dc2626'"
              onmouseout="this.style.background='none';this.style.color='#64748b'"
              title="Hapus PAKD" class="crud-action">🗑️</button>
          </div>
        </td>
      </tr>`).join('');
    applyRoleUI();
  } catch(e) {
    console.warn('Snapshot gagal, fallback ke live fetch:', e);
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#e74c3c">Gagal memuat snapshot. Refresh halaman.</td></tr>';
  }
}

function loadAll() { loadSnapshot(); loadAudit(); }

async function populateDetailSelect() {
  if (!AUTH.isLoggedIn()) return;
  try {
    const res = await apiFetch('/api/reconciliation-history?limit=100');
    const d = await res.json();
    const seen = {};
    d.data.forEach(r => { seen[r.pakd_id] = r.pakd_nama; });
    const sel = document.getElementById('detail-pakd-select');
    const count = Object.keys(seen).length;
    sel.innerHTML = '<option value="">Pilih PAKD... (' + count + ' entitas)</option>';
    Object.entries(seen).forEach(([id, nama]) => {
      const o = document.createElement('option');
      o.value = id; o.textContent = nama + ' (' + id + ')';
      sel.appendChild(o);
    });
    const user = AUTH.getUser();
    if (user && user.role === 'pakd' && user.entity_id && seen[user.entity_id]) {
      sel.value = user.entity_id;
      loadDetailPakd();
    }
  } catch(e) {}
}

async function _downloadCsv(url, fallbackFilename) {
  try {
    const response = await apiFetch(url);
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const blob = await response.blob();
    const disposition = response.headers.get('Content-Disposition') || '';
    const match = disposition.match(/filename=([^;]+)/);
    const filename = match ? match[1].trim() : fallbackFilename;
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = objectUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(objectUrl);
  } catch (e) {
    alert('Export gagal: ' + e.message);
  }
}

function exportCsvOverview() {
  _downloadCsv('/api/export-csv-overview', 'prima-overview.csv');
}

function exportCsv() {
  const pakdId = document.getElementById('detail-pakd-select').value;
  const url = pakdId ? `/api/export-csv?pakd_id=${pakdId}` : '/api/export-csv';
  _downloadCsv(url, 'prima-export.csv');
}

async function loadDetailPakd() {
  const pakdId = document.getElementById('detail-pakd-select').value;
  const limit = document.getElementById('detail-limit-select').value;
  if (!pakdId) return;
  try {
    const res = await apiFetch('/api/reconciliation-history?pakd_id=' + pakdId + '&limit=' + limit);
    const d = await res.json();
    const rows = d.data || [];
    renderDetailKpi(rows);
    renderDetailChart(rows);
    renderDetailDonut(rows);
    renderDetail3070(rows);
    renderDetailTable(rows);
    document.getElementById('detail-kpi-grid').style.display = 'grid';
    const selEl = document.getElementById('detail-pakd-select');
    const pakdNama = selEl.options[selEl.selectedIndex].text;
    document.getElementById('detail-subtitle').textContent = pakdNama + ' · Riwayat rekonsiliasi tersimpan di Supabase';
  } catch(e) { console.error('loadDetailPakd:', e); }
}

function renderDetailKpi(rows) {
  if (!rows.length) return;
  const devs = rows.map(r => parseFloat(r.deviasi_persen) || 0);
  const avg = devs.reduce((a,b) => a+b, 0) / devs.length;
  const maxDev = Math.max(...devs.map(Math.abs));
  const last = rows[0];
  document.getElementById('d-total').textContent = rows.length;
  document.getElementById('d-avg-dev').textContent = avg.toFixed(2) + '%';
  document.getElementById('d-max-dev').textContent = maxDev.toFixed(2) + '%';
  document.getElementById('d-last-status').textContent = last.status;
  const lastCard = document.getElementById('d-last-card');
  const lastVal = document.getElementById('d-last-status');
  const colorMap = {Aman:'green', Deviasi:'amber', Kritis:'red'};
  const c = colorMap[last.status] || 'green';
  lastCard.className = 'kpi-card ' + c;
  lastVal.className = 'kpi-value ' + c;
  document.getElementById('d-last-time').textContent = new Date(last.captured_at).toLocaleString('id-ID');
}

function renderDetailDonut(rows) {
  const wrap = document.getElementById('donut-wrap');
  if (!wrap) return;
  const latest = rows.find(r => r.network_breakdown && r.network_breakdown.length > 0);
  if (!latest) { wrap.innerHTML = '<div class="no-data-state">Tidak ada data komposisi</div>'; return; }
  const wallets = latest.network_breakdown;
  const segments = [
    { label: 'Bitcoin (BTC)',   color: '#f7931a', value: wallets.filter(w=>w.native_unit==='BTC').reduce((s,w)=>s+(w.balance_idr||0),0) },
    { label: 'Ethereum (ETH)', color: '#627eea', value: wallets.filter(w=>w.native_unit==='ETH').reduce((s,w)=>s+(w.eth_native_idr||0),0) },
    { label: 'Tether USDT - ETH', color: '#26a17b', value: wallets.filter(w=>w.native_unit==='ETH').reduce((s,w)=>s+(w.usdt_idr||0),0) },
    { label: 'USD Coin USDC - ETH', color: '#2775ca', value: wallets.filter(w=>w.native_unit==='ETH').reduce((s,w)=>s+(w.usdc_idr||0),0) },
    { label: 'AKD Lain - ETH', color: '#a78bfa', value: wallets.filter(w=>w.native_unit==='ETH').reduce((s,w)=>s+(w.eth_other_token_idr||0),0) },
    { label: 'Solana (SOL)',    color: '#9945ff', value: wallets.filter(w=>w.native_unit==='SOL').reduce((s,w)=>s+(w.sol_native_idr||0),0) },
    { label: 'Tether USDT - SOL', color: '#19ac8c', value: wallets.filter(w=>w.native_unit==='SOL').reduce((s,w)=>s+(w.sol_usdt_idr||0),0) },
    { label: 'USD Coin USDC - SOL', color: '#1a5fad', value: wallets.filter(w=>w.native_unit==='SOL').reduce((s,w)=>s+(w.sol_usdc_idr||0),0) },
    { label: 'AKD Lain - SOL', color: '#c084fc', value: wallets.filter(w=>w.native_unit==='SOL').reduce((s,w)=>s+(w.sol_other_token_idr||0),0) },
  ].filter(s => s.value > 0);
  const total = segments.reduce((s,x)=>s+x.value,0);
  if (total === 0) { wrap.innerHTML = '<div class="no-data-state">Aset on-chain Rp 0</div>'; return; }
  const size = 180; const cx = size/2; const cy = size/2; const r = 70; const ri = 42;
  let angle = -Math.PI/2;
  let slices = '';
  segments.forEach(seg => {
    const sweep = (seg.value/total)*2*Math.PI;
    const x1=cx+r*Math.cos(angle); const y1=cy+r*Math.sin(angle);
    angle+=sweep;
    const x2=cx+r*Math.cos(angle); const y2=cy+r*Math.sin(angle);
    const xi1=cx+ri*Math.cos(angle-sweep); const yi1=cy+ri*Math.sin(angle-sweep);
    const xi2=cx+ri*Math.cos(angle); const yi2=cy+ri*Math.sin(angle);
    const lg = sweep>Math.PI?1:0;
    slices += '<path d="M'+xi1+' '+yi1+' L'+x1+' '+y1+' A'+r+' '+r+' 0 '+lg+' 1 '+x2+' '+y2+' L'+xi2+' '+yi2+' A'+ri+' '+ri+' 0 '+lg+' 0 '+xi1+' '+yi1+' Z" fill="'+seg.color+'" opacity="0.9"/>';
  });
  const fmt = v => 'Rp '+Math.round(v).toLocaleString('id-ID');
  const legend = segments.map(s=>'<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px"><div style="width:10px;height:10px;border-radius:2px;background:'+s.color+';flex-shrink:0"></div><span style="font-size:11px;color:var(--txt2)">'+s.label+'</span><span class="mono" style="font-size:11px;margin-left:auto">'+((s.value/total*100).toFixed(1))+'%</span></div>').join('');
  wrap.innerHTML = '<svg width="'+size+'" height="'+size+'" viewBox="0 0 '+size+' '+size+'">'+slices+'<text x="'+cx+'" y="'+(cy-6)+'" text-anchor="middle" font-size="10" fill="var(--txt2)">Total</text><text x="'+cx+'" y="'+(cy+10)+'" text-anchor="middle" font-size="9" fill="var(--txt1)" font-weight="600">'+fmt(total)+'</text></svg><div style="width:100%;margin-top:8px">'+legend+'</div>';
}

function renderDetail3070(rows) {
  const panel = document.getElementById('detail-3070-panel');
  if (!panel) return;
  const latest = rows[0];
  if (!latest || !latest.has_kustodian) { panel.style.display = 'none'; return; }
  panel.style.display = '';
  const pakdVal = latest.pakd_onchain_idr || 0;
  const kustVal = latest.kustodian_onchain_idr || 0;
  const total = pakdVal + kustVal;
  const rPakd = latest.ratio_at_pakd != null ? latest.ratio_at_pakd : (total > 0 ? pakdVal / total : 0);
  const rKust = latest.ratio_at_ptp != null ? latest.ratio_at_ptp : (total > 0 ? kustVal / total : 0);
  const compliant = latest.compliance_30_70;
  const fmtR = v => 'Rp ' + Math.round(v).toLocaleString('id-ID');
  document.getElementById('detail-3070-badge').innerHTML = compliant
    ? '<span class="badge-compliant" style="font-size:13px;padding:5px 14px">✓ COMPLIANT — Rasio sesuai POJK 23/2025</span>'
    : '<span class="badge-violation" style="font-size:13px;padding:5px 14px">✗ VIOLATION — ' + (rPakd * 100).toFixed(1) + '% aset di PAKD (maks 30%)</span>';
  document.getElementById('detail-3070-pakd-val').textContent = fmtR(pakdVal);
  document.getElementById('detail-3070-pakd-pct').innerHTML = '<span style="color:' + (rPakd > 0.3 ? 'var(--red)' : 'var(--green)') + ';font-weight:600">' + (rPakd * 100).toFixed(1) + '%</span> dari total on-chain';
  document.getElementById('detail-3070-kust-val').textContent = fmtR(kustVal);
  document.getElementById('detail-3070-kust-pct').innerHTML = '<span style="color:' + (rKust >= 0.7 ? 'var(--green)' : 'var(--red)') + ';font-weight:600">' + (rKust * 100).toFixed(1) + '%</span> dari total on-chain';
  // Mini donut
  const sz = 140, cx = sz/2, cy = sz/2, r = 55, ri = 35;
  const pAngle = rPakd * 2 * Math.PI;
  const startA = -Math.PI/2;
  const seg = (start, sweep, color) => {
    const x1=cx+r*Math.cos(start), y1=cy+r*Math.sin(start);
    const end=start+sweep;
    const x2=cx+r*Math.cos(end), y2=cy+r*Math.sin(end);
    const xi1=cx+ri*Math.cos(start), yi1=cy+ri*Math.sin(start);
    const xi2=cx+ri*Math.cos(end), yi2=cy+ri*Math.sin(end);
    const lg=sweep>Math.PI?1:0;
    return '<path d="M'+xi1+' '+yi1+' L'+x1+' '+y1+' A'+r+' '+r+' 0 '+lg+' 1 '+x2+' '+y2+' L'+xi2+' '+yi2+' A'+ri+' '+ri+' 0 '+lg+' 0 '+xi1+' '+yi1+' Z" fill="'+color+'" opacity="0.85"/>';
  };
  const pakdColor = rPakd > 0.3 ? '#e74c3c' : '#f39c12';
  const kustColor = '#27ae60';
  let svg = '<svg width="'+sz+'" height="'+sz+'" viewBox="0 0 '+sz+' '+sz+'">';
  if (total > 0) {
    svg += seg(startA, pAngle, pakdColor);
    svg += seg(startA + pAngle, 2*Math.PI - pAngle, kustColor);
  }
  svg += '<text x="'+cx+'" y="'+(cy-4)+'" text-anchor="middle" font-size="9" fill="var(--txt3)">PAKD / PTP</text>';
  svg += '<text x="'+cx+'" y="'+(cy+10)+'" text-anchor="middle" font-size="10" font-weight="700" fill="var(--txt1)">'+(rPakd*100).toFixed(0)+'% / '+(rKust*100).toFixed(0)+'%</text>';
  svg += '</svg>';
  svg += '<div style="display:flex;gap:12px;margin-top:6px;font-size:10px">';
  svg += '<div style="display:flex;align-items:center;gap:4px"><div style="width:8px;height:8px;border-radius:2px;background:'+pakdColor+'"></div>PAKD</div>';
  svg += '<div style="display:flex;align-items:center;gap:4px"><div style="width:8px;height:8px;border-radius:2px;background:'+kustColor+'"></div>Kustodian</div>';
  svg += '</div>';
  document.getElementById('detail-3070-donut').innerHTML = svg;
}

function renderDetailChart(rows) {
  const wrap = document.getElementById('trend-chart-wrap');
  if (!rows.length) { wrap.innerHTML = '<div class="no-data-state">Belum ada data tren. Jalankan rekonsiliasi minimal 2 kali untuk melihat tren.</div>'; return; }
  const sorted = [...rows].reverse();
  const onchain = sorted.map(r => r.aset_onchain_idr || 0);
  const dilap  = sorted.map(r => r.aset_dilaporkan_idr || 0);
  const times  = sorted.map(r => r.captured_at);
  const allVals = [...onchain, ...dilap];
  const minV = Math.min(...allVals); const maxV = Math.max(...allVals);
  const range = maxV - minV || 1;

  const W = 820; const H = 200;
  const PADL = 90; const PADR = 16; const PADT = 16; const PADB = 40;
  const cW = W - PADL - PADR; const cH = H - PADT - PADB;

  const toY = v => PADT + (1 - (v - minV) / range) * cH;
  const toX = (i, len) => PADL + (i / (len - 1 || 1)) * cW;

  const fmtRp = v => 'Rp ' + Math.round(v).toLocaleString('id-ID');
  const fmtTime = iso => {
    const d = new Date(iso);
    return d.toLocaleString('id-ID', {day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'});
  };

  const YTICKS = 4;
  let gridLines = '';
  let yLabels = '';
  for (let i = 0; i <= YTICKS; i++) {
    const v = minV + (range * i / YTICKS);
    const y = toY(v).toFixed(1);
    gridLines += '<line x1="' + PADL + '" y1="' + y + '" x2="' + (W - PADR) + '" y2="' + y + '" stroke="#E5E7EB" stroke-width="1"/>';
    yLabels  += '<text x="' + (PADL - 6) + '" y="' + y + '" text-anchor="end" dominant-baseline="middle" font-size="9" fill="#9CA3AF" font-family="JetBrains Mono,monospace">' + fmtRp(v) + '</text>';
  }

  const n = times.length;
  const maxXTicks = 6;
  const step = Math.max(1, Math.ceil(n / maxXTicks));
  let xLabels = '';
  for (let i = 0; i < n; i += step) {
    const x = toX(i, n).toFixed(1);
    xLabels += '<text x="' + x + '" y="' + (H - PADB + 14) + '" text-anchor="middle" font-size="9" fill="#9CA3AF" font-family="JetBrains Mono,monospace">' + fmtTime(times[i]) + '</text>';
  }
  if ((n - 1) % step !== 0) {
    const x = toX(n - 1, n).toFixed(1);
    xLabels += '<text x="' + x + '" y="' + (H - PADB + 14) + '" text-anchor="middle" font-size="9" fill="#9CA3AF" font-family="JetBrains Mono,monospace">' + fmtTime(times[n - 1]) + '</text>';
  }

  const makePath = arr => arr.map((v,i) => (i===0?'M':'L') + toX(i,arr.length).toFixed(1) + ',' + toY(v).toFixed(1)).join(' ');
  const makeDots = (arr, color) => arr.map((v,i) => '<circle cx="' + toX(i,arr.length).toFixed(1) + '" cy="' + toY(v).toFixed(1) + '" r="3" fill="' + color + '" stroke="#fff" stroke-width="1.5"/>').join('');

  const axisColor = '#D1D5DB';
  wrap.innerHTML =
    '<svg class="trend-svg" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none">' +
    gridLines +
    '<line x1="' + PADL + '" y1="' + PADT + '" x2="' + PADL + '" y2="' + (H - PADB) + '" stroke="' + axisColor + '" stroke-width="1"/>' +
    '<line x1="' + PADL + '" y1="' + (H - PADB) + '" x2="' + (W - PADR) + '" y2="' + (H - PADB) + '" stroke="' + axisColor + '" stroke-width="1"/>' +
    yLabels + xLabels +
    '<text x="' + (PADL - 6) + '" y="' + (PADT - 4) + '" text-anchor="end" font-size="8" fill="#9CA3AF" font-family="JetBrains Mono,monospace">IDR</text>' +
    '<path d="' + makePath(dilap)   + '" fill="none" stroke="var(--amber)" stroke-width="1.5" stroke-dasharray="5,3" stroke-linejoin="round"/>' +
    '<path d="' + makePath(onchain) + '" fill="none" stroke="var(--blue)"  stroke-width="2"   stroke-linejoin="round"/>' +
    makeDots(dilap,   'var(--amber)') +
    makeDots(onchain, 'var(--blue)')  +
    '</svg>';
}

function renderDetailTable(rows) {
  const tbody = document.getElementById('detail-history-tbody');
  if (!rows.length) { tbody.innerHTML = '<tr><td colspan="7" class="no-data-state">Tidak ada data</td></tr>'; return; }
  tbody.innerHTML = rows.map((r, idx) => {
    const dev = parseFloat(r.deviasi_persen) || 0;
    const devColor = r.status === 'Aman' ? 'var(--green)' : r.status === 'Deviasi' ? 'var(--amber)' : 'var(--red)';
    const badgeClass = r.status === 'Aman' ? 'aman' : r.status === 'Deviasi' ? 'deviasi' : 'kritis';
    const hasBreakdown = r.network_breakdown && r.network_breakdown.length > 0;
    const mainRow = '<tr>' +
      '<td class="mono" style="font-size:11px">' + new Date(r.captured_at).toLocaleString('id-ID') + '</td>' +
      '<td class="mono">Rp ' + (r.aset_onchain_idr||0).toLocaleString('id-ID') + '</td>' +
      '<td class="mono">Rp ' + (r.aset_dilaporkan_idr||0).toLocaleString('id-ID') + '</td>' +
      '<td class="mono" style="color:' + devColor + ';font-weight:600">' + dev.toFixed(2) + '%</td>' +
      '<td><span class="status-badge ' + badgeClass + '">' + r.status + '</span></td>' +
      '<td style="color:' + (r.harga_fallback ? 'var(--amber)' : 'var(--green)') + ';font-size:11px">' + (r.harga_fallback ? 'Ya' : 'Tidak') + '</td>' +
      '<td>' + (hasBreakdown ? '<button onclick="toggleBreakdown(' + idx + ')" style="font-size:11px;padding:2px 8px;border-radius:4px;border:1px solid var(--border);background:var(--bg);cursor:pointer;color:var(--blue)" id="btn-breakdown-' + idx + '">Lihat</button>' : '-') + '</td>' +
    '</tr>';
    const breakdownRow = hasBreakdown ? '<tr id="breakdown-row-' + idx + '" style="display:none"><td colspan="7" style="padding:0">' + buildBreakdownHtml(r.network_breakdown) + '</td></tr>' : '';
    return mainRow + breakdownRow;
  }).join('');
}

function buildBreakdownHtml(wallets) {
  const fmt = v => 'Rp ' + Math.round(v||0).toLocaleString('id-ID');
  let rows = '';
  wallets.forEach(w => {
    const net = w.native_unit || '?';
    if (net === 'ETH') {
      rows += '<tr style="background:var(--bg)"><td style="padding:4px 12px;font-size:11px;color:var(--txt2)">' + (w.address||'').slice(0,10) + '...</td><td style="font-size:11px">Ethereum (ETH)</td><td class="mono" style="font-size:11px">' + fmt(w.eth_native_idr) + '</td></tr>';
      if (w.usdt_idr) rows += '<tr style="background:var(--bg)"><td style="padding:4px 12px;font-size:11px;color:var(--txt2)"></td><td style="font-size:11px">Tether USDT - Jaringan Ethereum</td><td class="mono" style="font-size:11px">' + fmt(w.usdt_idr) + '</td></tr>';
      if (w.usdc_idr) rows += '<tr style="background:var(--bg)"><td style="padding:4px 12px;font-size:11px;color:var(--txt2)"></td><td style="font-size:11px">USD Coin USDC - Jaringan Ethereum</td><td class="mono" style="font-size:11px">' + fmt(w.usdc_idr) + '</td></tr>';
      if (w.eth_other_token_idr) rows += '<tr style="background:var(--bg)"><td style="padding:4px 12px;font-size:11px;color:var(--txt2)"></td><td style="font-size:11px">AKD Lain - Jaringan Ethereum</td><td class="mono" style="font-size:11px">' + fmt(w.eth_other_token_idr) + '</td></tr>';
    } else if (net === 'BTC') {
      rows += '<tr style="background:var(--bg)"><td style="padding:4px 12px;font-size:11px;color:var(--txt2)">' + (w.address||'').slice(0,10) + '...</td><td style="font-size:11px">BTC</td><td class="mono" style="font-size:11px">' + fmt(w.balance_idr) + '</td></tr>';
    } else if (net === 'SOL') {
      rows += '<tr style="background:var(--bg)"><td style="padding:4px 12px;font-size:11px;color:var(--txt2)">' + (w.address||'').slice(0,10) + '...</td><td style="font-size:11px">Solana (SOL)</td><td class="mono" style="font-size:11px">' + fmt(w.sol_native_idr) + '</td></tr>';
      if (w.sol_usdt_idr) rows += '<tr style="background:var(--bg)"><td style="padding:4px 12px;font-size:11px;color:var(--txt2)"></td><td style="font-size:11px">Tether USDT - Jaringan Solana</td><td class="mono" style="font-size:11px">' + fmt(w.sol_usdt_idr) + '</td></tr>';
      if (w.sol_usdc_idr) rows += '<tr style="background:var(--bg)"><td style="padding:4px 12px;font-size:11px;color:var(--txt2)"></td><td style="font-size:11px">USD Coin USDC - Jaringan Solana</td><td class="mono" style="font-size:11px">' + fmt(w.sol_usdc_idr) + '</td></tr>';
      if (w.sol_other_token_idr) rows += '<tr style="background:var(--bg)"><td style="padding:4px 12px;font-size:11px;color:var(--txt2)"></td><td style="font-size:11px">AKD Lain - Jaringan Solana</td><td class="mono" style="font-size:11px">' + fmt(w.sol_other_token_idr) + '</td></tr>';
    }
  });
  return '<table style="width:100%;border-top:1px solid var(--border);border-collapse:collapse"><thead><tr style="background:var(--bg2)"><th style="font-size:11px;padding:4px 12px;text-align:left;color:var(--txt2)">Wallet</th><th style="font-size:11px;padding:4px 12px;text-align:left;color:var(--txt2)">Aset</th><th style="font-size:11px;padding:4px 12px;text-align:left;color:var(--txt2)">Nilai IDR</th></tr></thead><tbody>' + rows + '</tbody></table>';
}

function toggleBreakdown(idx) {
  const row = document.getElementById('breakdown-row-' + idx);
  const btn = document.getElementById('btn-breakdown-' + idx);
  if (!row) return;
  const visible = row.style.display !== 'none';
  row.style.display = visible ? 'none' : 'table-row';
  btn.textContent = visible ? 'Lihat' : 'Tutup';
}

document.addEventListener('DOMContentLoaded', populateDetailSelect);
addWalletRow('ethereum');

function toggleLegal(id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.style.display = (el.style.display === 'none' ? 'block' : 'none');
}

function renderChips(containerId, items, showPass) {
    var container = document.getElementById(containerId);
    if (!container) return;
    var filtered = showPass ? items : items.filter(function(x) { return !x.lulus; });
    if (!filtered || filtered.length === 0) {
        container.innerHTML = '<span style="color:#888;font-size:12px">-</span>';
        return;
    }
    container.innerHTML = filtered.map(function(x) {
        var bg = x.lulus ? '#d1fae5' : '#fee2e2';
        var col = x.lulus ? '#065f46' : '#991b1b';
        var prefix = x.lulus ? '\u2713 ' : '\u00d7 ';
        var label = x.nama || x.id || '-';
        var val = x.equity_post != null ? x.equity_post : (x.aset_stressed != null ? x.aset_stressed : null);
        var valStr = '';
        if (val != null) {
            valStr = ' <span style="opacity:0.75">Rp ' + Math.round(val).toLocaleString('id-ID') + '</span>';
        }
        return '<span style="background:' + bg + ';color:' + col + ';padding:3px 10px;border-radius:12px;font-size:11px;margin:2px;display:inline-block">' + prefix + escapeHtml(label) + valStr + '</span>';
    }).join('');
}
