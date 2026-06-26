path = '/workspaces/prima-ojk/prima-frontend/index.html'
with open(path, encoding='utf-8') as f: src = f.read()
R = []
def rep(label, old, new):
    global src
    if old not in src: R.append('FAIL: '+label); return
    src = src.replace(old, new, 1); R.append('OK:   '+label)

rep('css',
    ".stress-count{font-family:'JetBrains Mono',monospace;font-size:13px;font-weight:600;flex:0 0 80px;text-align:right}",
    ".stress-count{font-family:'JetBrains Mono',monospace;font-size:13px;font-weight:600;flex:0 0 80px;text-align:right}\n.stress-desc{font-size:12px;color:var(--txt3);margin-bottom:12px;line-height:1.6}\n.stress-threshold-pill{display:inline-flex;align-items:center;gap:6px;background:var(--bg2);border:1px solid var(--txt4);border-radius:20px;padding:4px 10px;font-size:11px;color:var(--txt3);margin-bottom:10px}\n.stress-threshold-pill strong{color:var(--txt1);font-weight:600}\n.entity-chips-row{display:flex;gap:6px;flex-wrap:wrap;padding:6px 0 4px}\n.entity-chip{font-size:11px;font-weight:600;padding:3px 8px;border-radius:20px;display:inline-flex;align-items:center;gap:4px}\n.entity-chip.pass{background:var(--green-bg);color:var(--green);border:1px solid var(--green-border)}\n.entity-chip.fail{background:var(--red-bg);color:var(--red);border:1px solid var(--red-border)}\n.entity-card-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;padding:8px 0}\n.entity-card-st{border:1px solid var(--txt4);border-radius:var(--r);padding:8px 10px}\n.entity-card-st.pass{border-color:var(--green-border);background:var(--green-bg)}\n.entity-card-st.fail{border-color:var(--red-border);background:var(--red-bg)}\n.entity-card-st-name{font-size:12px;font-weight:700;display:flex;align-items:center;gap:4px;margin-bottom:6px}\n.entity-card-st-name.pass{color:var(--green)}\n.entity-card-st-name.fail{color:var(--red)}\n.entity-card-st-row{display:flex;justify-content:space-between;font-size:11px;margin-bottom:2px}\n.entity-card-st-lbl{color:var(--txt3)}\n.entity-card-st-val{color:var(--txt1);font-weight:600}\n.entity-card-st-val.red{color:var(--red)}\n.entity-card-st-val.green{color:var(--green)}\n.alert-banner-stress{display:none;align-items:flex-start;gap:10px;padding:12px 16px;background:var(--red-bg);border:1px solid var(--red-border);border-radius:var(--r);margin-bottom:16px;font-size:13px;color:var(--red);line-height:1.5}\n.legal-toggle-btn{background:none;border:none;font-size:11px;color:var(--txt2);cursor:pointer;text-decoration:underline;padding:0;margin-bottom:10px}\n.legal-detail-box{font-size:11px;color:var(--txt3);background:var(--bg2);border-radius:var(--r);padding:10px 12px;margin-bottom:12px;line-height:1.6;display:none}\n.legal-detail-box.open{display:block}")

rep('subtitle',
    'Simulasi ketahanan aset PAKD terhadap penurunan harga kripto',
    'Simulasi ketahanan solvabilitas PAKD terhadap krisis pasar dan insiden siber')

rep('kpi-grid',
'''    <div class="kpi-grid">
      <div class="kpi-card green">
        <div class="kpi-label">P50 Lulus Mild (\u221225%)</div>
        <div class="kpi-value green" id="st-kpi-p50-mild">\u2014</div>
        <div class="kpi-sub">Pasal 50 \u00b7 Risiko Pasar</div>
      </div>
      <div class="kpi-card red">
        <div class="kpi-label">P50 Lulus Severe (\u221280%)</div>
        <div class="kpi-value red" id="st-kpi-p50-severe">\u2014</div>
        <div class="kpi-sub">Pasal 50 \u00b7 Risiko Pasar</div>
      </div>
      <div class="kpi-card amber">
        <div class="kpi-label">P91 Lulus Moderate (\u221250%)</div>
        <div class="kpi-value amber" id="st-kpi-p91-moderate">\u2014</div>
        <div class="kpi-sub">Pasal 91 \u00b7 Risiko Siber</div>
      </div>
      <div class="kpi-card blue">
        <div class="kpi-label">Harga ETH Live</div>
        <div class="kpi-value blue" id="st-kpi-eth" style="font-size:22px;margin-top:6px">\u2014</div>
        <div class="kpi-sub" id="st-kpi-eth-sub">sumber: CoinGecko</div>
      </div>
    </div>''',
'''    <div class="alert-banner-stress" id="st-alert-banner">
      <span style="font-size:16px">\u26a0</span>
      <span id="st-alert-text"></span>
    </div>
    <div class="kpi-grid">
      <div class="kpi-card red">
        <div class="kpi-label">Risiko Pasar \u2014 Severe</div>
        <div class="kpi-value red" id="st-kpi-p50-severe">\u2014</div>
        <div class="kpi-sub" style="margin-bottom:8px">Pasal 50 \u00b7 ekuitas pasca-stress</div>
        <div class="entity-chips-row" id="kpi-chips-p50-severe"></div>
      </div>
      <div class="kpi-card amber">
        <div class="kpi-label">Risiko Siber \u2014 Moderate</div>
        <div class="kpi-value amber" id="st-kpi-p91-moderate">\u2014</div>
        <div class="kpi-sub" style="margin-bottom:8px">Pasal 91 \u00b7 ekuitas pasca-kehilangan</div>
        <div class="entity-chips-row" id="kpi-chips-p91-moderate"></div>
      </div>
      <div class="kpi-card red">
        <div class="kpi-label">Risiko Siber \u2014 Severe</div>
        <div class="kpi-value red" id="st-kpi-p91-severe">\u2014</div>
        <div class="kpi-sub" style="margin-bottom:8px">Pasal 91 \u00b7 skenario Mt. Gox</div>
        <div class="entity-chips-row" id="kpi-chips-p91-severe"></div>
      </div>
      <div class="kpi-card blue">
        <div class="kpi-label">Harga ETH Live</div>
        <div class="kpi-value blue" id="st-kpi-eth" style="font-size:22px;margin-top:6px">\u2014</div>
        <div class="kpi-sub" id="st-kpi-eth-sub">sumber: CoinGecko</div>
      </div>
    </div>''')

rep('p50-title',
    '<div class="section-title"><div class="section-title-bar"></div>Pasal 50 \u2014 Risiko Pasar</div>',
    '<div class="section-title"><div class="section-title-bar"></div>Uji ketahanan ekuitas terhadap volatilitas harga aset</div>')

rep('p50-panel',
'''          <div class="info-chip" id="stress-price-note">Memuat harga live...</div>
          <div style="font-size:11px;color:var(--txt3);margin-bottom:10px;padding:6px 0">
            Threshold: ekuitas pasca-stress \u2265 Rp 50.000.000.000 \u00b7 POJK No. 27 Tahun 2024, Pasal 50 ayat (1) huruf o
          </div>
          <div id="stress-mild" class="stress-row mild">
            <div class="stress-label-wrap"><div class="stress-name mild">Mild</div><div class="stress-pct-label" id="p50-mild-sub">\u221225% volatile \u00b7 \u22123% stable</div></div>
            <div class="stress-bar-wrap"><div class="stress-bar mild" style="width:0%"></div></div>
            <div class="stress-count" style="color:var(--green)">\u2014<span style="font-size:9px;color:var(--txt3)"> lulus</span></div>
          </div>
          <div id="stress-moderate" class="stress-row moderate">
            <div class="stress-label-wrap"><div class="stress-name moderate">Moderate</div><div class="stress-pct-label" id="p50-moderate-sub">\u221250% volatile \u00b7 \u22128% stable</div></div>
            <div class="stress-bar-wrap"><div class="stress-bar moderate" style="width:0%"></div></div>
            <div class="stress-count" style="color:var(--amber)">\u2014<span style="font-size:9px;color:var(--txt3)"> lulus</span></div>
          </div>
          <div id="stress-severe" class="stress-row severe">
            <div class="stress-label-wrap"><div class="stress-name severe">Severe</div><div class="stress-pct-label" id="p50-severe-sub">\u221280% volatile \u00b7 \u221213% stable</div></div>
            <div class="stress-bar-wrap"><div class="stress-bar severe" style="width:0%"></div></div>
            <div class="stress-count" style="color:var(--red)">\u2014<span style="font-size:9px;color:var(--txt3)"> lulus</span></div>
          </div>
          <div id="stress-note" style="margin-top:14px;padding:12px 16px;background:var(--bg2);border-radius:var(--r);border-left:3px solid var(--txt4);font-size:13px;color:var(--txt3)">Memuat hasil stress test...</div>''',
'''          <div class="stress-desc">Mengukur kemampuan setiap PAKD mempertahankan ekuitas minimum ketika harga Aset Keuangan Digital turun bersamaan. Ekuitas minimum wajib dijaga setiap saat sesuai ketentuan OJK.</div>
          <div class="stress-threshold-pill">\u25cf Batas lulus: <strong>Ekuitas pasca-stress \u2265 Rp 50 miliar</strong> \u00b7 POJK 23 Tahun 2025, Pasal 50 ayat (1)</div>
          <button class="legal-toggle-btn" onclick="toggleLegal('l-p50')">&#9662; Metodologi lengkap</button>
          <div class="legal-detail-box" id="l-p50">Skenario penurunan: Mild -25%, Moderate -50%, Severe -80%. Referensi: BTC -64% sepanjang 2022 (Chainalysis 2024); BTC -84% siklus 2017-2018 (CoinMarketCap). Stablecoin USDT/USDC haircut -3%/-8%/-13% (USDC depeg USD 0,87 kolaps SVB Maret 2023, Reuters). POJK 23 Tahun 2025, Pasal 50 ayat (1).</div>
          <div class="info-chip" id="stress-price-note">Memuat harga live...</div>
          <div id="stress-mild" class="stress-row mild">
            <div class="stress-label-wrap"><div class="stress-name mild">Mild</div><div class="stress-pct-label" id="p50-mild-sub">\u221225% volatile \u00b7 \u22123% stable</div></div>
            <div class="stress-bar-wrap"><div class="stress-bar mild" style="width:0%"></div></div>
            <div class="stress-count" style="color:var(--green)">\u2014<span style="font-size:9px;color:var(--txt3)"> lulus</span></div>
          </div>
          <div class="entity-chips-row" id="p50-chips-mild"></div>
          <div id="stress-moderate" class="stress-row moderate">
            <div class="stress-label-wrap"><div class="stress-name moderate">Moderate</div><div class="stress-pct-label" id="p50-moderate-sub">\u221250% volatile \u00b7 \u22128% stable</div></div>
            <div class="stress-bar-wrap"><div class="stress-bar moderate" style="width:0%"></div></div>
            <div class="stress-count" style="color:var(--amber)">\u2014<span style="font-size:9px;color:var(--txt3)"> lulus</span></div>
          </div>
          <div class="entity-chips-row" id="p50-chips-moderate"></div>
          <div id="stress-severe" class="stress-row severe">
            <div class="stress-label-wrap"><div class="stress-name severe">Severe</div><div class="stress-pct-label" id="p50-severe-sub">\u221280% volatile \u00b7 \u221213% stable</div></div>
            <div class="stress-bar-wrap"><div class="stress-bar severe" style="width:0%"></div></div>
            <div class="stress-count" style="color:var(--red)">\u2014<span style="font-size:9px;color:var(--txt3)"> lulus</span></div>
          </div>
          <div class="entity-chips-row" id="p50-chips-severe"></div>
          <div id="stress-note" style="margin-top:14px;padding:12px 16px;background:var(--bg2);border-radius:var(--r);border-left:3px solid var(--txt4);font-size:13px;color:var(--txt3)">Memuat hasil stress test...</div>''')

rep('p91-title',
    '<div class="section-title"><div class="section-title-bar"></div>Pasal 91 \u2014 Risiko Siber</div>',
    '<div class="section-title"><div class="section-title-bar"></div>Uji kemampuan mengkompensasi kehilangan aset digital konsumen akibat insiden siber</div>')

rep('p91-threshold',
'''          <div style="font-size:11px;color:var(--txt3);margin-bottom:10px;padding:6px 0">
            Threshold: ekuitas pasca-kehilangan \u2265 Rp 50.000.000.000 \u00b7 POJK No. 27 Tahun 2024, Pasal 91 ayat (1)
          </div>
          <div id="p91-mild"''',
'''          <div class="stress-desc">Mengukur apakah seluruh aset PAKD setelah dikurangi nilai AKD konsumen yang hilang masih memenuhi batas ekuitas minimum. Jika ekuitas jatuh di bawah Rp 50 miliar, PAKD tidak mampu memenuhi kewajiban penggantian kepada konsumen.</div>
          <div class="stress-threshold-pill">\u25cf Batas lulus: <strong>Ekuitas pasca-kehilangan \u2265 Rp 50 miliar</strong> \u00b7 POJK 23 Tahun 2025, Pasal 91 ayat (1)</div>
          <button class="legal-toggle-btn" onclick="toggleLegal('l-p91')">&#9662; Metodologi lengkap</button>
          <div class="legal-detail-box" id="l-p91">Skenario kehilangan: Mild -23% (GDAC April 2023, Chainalysis 2024), Moderate -50% (WazirX Juli 2024, Elliptic/Reuters), Severe -100% (Mt. Gox 2014). Formula: ekuitas pasca-kehilangan = ekuitas awal - nilai AKD konsumen hilang. POJK 23 Tahun 2025, Pasal 91 ayat (1).</div>
          <div id="p91-mild"''')

rep('p91-card-mild',
    '</div>\n          <div id="p91-moderate"',
    '</div>\n          <div class="entity-card-grid" id="p91-cards-mild"></div>\n          <div id="p91-moderate"')

rep('p91-card-moderate',
    '</div>\n          <div id="p91-severe"',
    '</div>\n          <div class="entity-card-grid" id="p91-cards-moderate"></div>\n          <div id="p91-severe"')

rep('p91-card-severe',
    '</div>\n          <div id="p91-note"',
    '</div>\n          <div class="entity-card-grid" id="p91-cards-severe"></div>\n          <div id="p91-note"')

rep('metodologi-pojk', 'POJK 27/2024)', 'POJK 23 Tahun 2025)')

with open(path, 'w', encoding='utf-8') as f: f.write(src)
for r in R: print(r)
print('Lines:', src.count('\n'))
