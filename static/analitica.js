/* Panel analítico interactivo.
 * - Todo se calcula en el navegador a partir de /api/analitica/datos: un filtro (fecha, ciudad, sector,
 *   usuario, prioridad, oportunidad, score) o un clic en cualquier gráfico recalcula todo el panel.
 * - Cada gráfico tiene tooltip y una vista de tabla equivalente (los tooltips nunca son la única vía).
 * - Colores validados con scripts/validate_palette.js; el color sigue a la entidad, nunca a su posición. */
(function () {
    'use strict';

    // ------------------------------------------------------------------ constantes y utilidades
    const INK = '#0b0b0b', INK2 = '#52514e', MUTED = '#898781', GRID = '#e1e0d9', BASE = '#c3c2b7', SURF = '#fcfcfb';
    const AZUL = '#2a78d6', NARANJA = '#eb6834', AQUA = '#1baf7a';
    const C = { radar: AZUL, redes: NARANJA, leads: AZUL, contactos: NARANJA, respuestas: AQUA };
    const PRIO = { alta: { txt: 'Alta', c: '#E11D74' }, media: { txt: 'Media', c: '#E58A00' }, baja: { txt: 'Baja', c: '#6250d6' } };
    const OPP = { sin_web: 'Sin web', web_mala: 'Web débil', sin_medicion: 'Sin medición Ads', sin_captacion: 'No capta contactos',
        seo_local: 'SEO local', reputacion: 'Reputación', gestion: 'App de gestión' };
    const ORD = ['#86b6ef', '#5598e7', '#2a78d6', '#1c5cab', '#104281'];   // ordinal: embudo
    const SEQ = ['#cde2fb', '#0d366b'];                                       // secuencial: mapa de calor
    const RESP = new Set(['respondio', 'reunion', 'cerrado']), REUN = new Set(['reunion', 'cerrado']);
    const CANAL_TXT = { whatsapp: 'WhatsApp', email: 'Email', telefono: 'Llamada' };
    const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

    const nf = new Intl.NumberFormat('es');
    const nf1 = new Intl.NumberFormat('es', { maximumFractionDigits: 1 });
    const fmt = (n) => nf.format(Math.round(n));
    const pct = (a, b) => (b ? Math.round(1000 * a / b) / 10 : null);
    const pctTxt = (v) => (v == null ? '—' : nf1.format(v) + '%');
    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const $id = (id) => document.getElementById(id);
    const suma = (arr, k) => arr.reduce((t, x) => t + (x[k] || 0), 0);

    const pad = (n) => String(n).padStart(2, '0');
    const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    const fechaLocal = (iso) => (iso ? ymd(new Date(iso.length <= 10 ? iso + 'T00:00:00' : iso + 'Z')) : null);
    const addDays = (s, n) => { const d = new Date(s + 'T00:00:00'); d.setDate(d.getDate() + n); return ymd(d); };
    const diffDays = (a, b) => Math.round((new Date(b + 'T00:00:00') - new Date(a + 'T00:00:00')) / 864e5);
    const mesDe = (s) => s.slice(0, 7);
    const mesTxt = (m) => `${MESES[+m.slice(5, 7) - 1]} ${m.slice(0, 4)}`;
    const mesInicio = (m) => m + '-01';
    const mesFin = (m) => { const [y, mm] = m.split('-').map(Number); return ymd(new Date(y, mm, 0)); };
    const restaMeses = (m, n) => { const [y, mm] = m.split('-').map(Number); const d = new Date(y, mm - 1 - n, 1); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`; };
    const listaMeses = (a, b) => { const out = []; for (let m = a; m <= b; m = restaMeses(m, -1)) out.push(m); return out; };
    const lunes = (s) => { const d = new Date(s + 'T00:00:00'); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return ymd(d); };
    const diaTxt = (s) => { const d = new Date(s + 'T00:00:00'); return `${d.getDate()} ${MESES[d.getMonth()]}`; };

    // ------------------------------------------------------------------ estado
    let DATA = null, CUENTA = null, F = null;
    const UI = { consumoModo: 'mes', heat: 'leads', rend: 'usuario', tabla: {} };
    const charts = {}, TABLAS = {};
    let construido = false, S = null;
    let VISTAS = [], aplicadaDefault = false;
    const LISTAS = ['ciudad', 'sector', 'usuario', 'prioridad', 'oportunidad'];

    const filtroInicial = () => ({ preset: '6m', desde: null, hasta: null, ciudad: new Set(), sector: new Set(),
        usuario: new Set(), prioridad: new Set(), oportunidad: new Set(), score: null });

    const PRESETS = [['mes', 'Este mes'], ['mesant', 'Mes pasado'], ['3m', '3 meses'], ['6m', '6 meses'], ['12m', '12 meses'], ['todo', 'Todo']];

    function fechaMin() {
        const t = [...DATA.leads.map((l) => l.f), ...DATA.consumo.map((c) => c.f), ...DATA.eventos.map((e) => e.f)].filter(Boolean).sort();
        return t[0] || DATA.config.hoy;
    }
    function rango() {
        const hoy = DATA.config.hoy, m0 = mesDe(hoy);
        switch (F.preset) {
            case 'custom': return { desde: F.desde || fechaMin(), hasta: F.hasta || hoy };
            case 'mes': return { desde: mesInicio(m0), hasta: hoy };
            case 'mesant': { const pm = restaMeses(m0, 1); return { desde: mesInicio(pm), hasta: mesFin(pm) }; }
            case '3m': return { desde: mesInicio(restaMeses(m0, 2)), hasta: hoy };
            case '6m': return { desde: mesInicio(restaMeses(m0, 5)), hasta: hoy };
            case '12m': return { desde: mesInicio(restaMeses(m0, 11)), hasta: hoy };
            default: return { desde: fechaMin(), hasta: hoy };
        }
    }
    function periodoPrevio(rg) {
        if (F.preset === 'todo') return null;
        const dias = diffDays(rg.desde, rg.hasta) + 1;
        return { desde: addDays(rg.desde, -dias), hasta: addDays(rg.desde, -1) };
    }

    // ------------------------------------------------------------------ filtrado
    function pasaLead(l, rg) {
        if (rg && (l.f < rg.desde || l.f > rg.hasta)) return false;
        if (F.ciudad.size && !F.ciudad.has(l.ciudad)) return false;
        if (F.sector.size && !F.sector.has(l.sector)) return false;
        if (F.usuario.size && !F.usuario.has(String(l.usuario))) return false;
        if (F.prioridad.size && !F.prioridad.has(l.prioridad)) return false;
        if (F.oportunidad.size && !l.oportunidades.some((o) => F.oportunidad.has(o))) return false;
        if (F.score && (l.score < F.score[0] || l.score > F.score[1])) return false;
        return true;
    }
    function pasaConsumo(c, rg) {
        if (rg && (c.f < rg.desde || c.f > rg.hasta)) return false;
        if (F.ciudad.size && !F.ciudad.has(c.ciudad)) return false;
        if (F.sector.size && !F.sector.has(c.sector)) return false;
        if (F.usuario.size && !F.usuario.has(String(c.usuario))) return false;
        return true;
    }
    function calcular() {
        const rg = rango(), prev = periodoPrevio(rg);
        const leadsND = DATA.leads.filter((l) => pasaLead(l, null));
        const ids = new Set(leadsND.map((l) => l.id));
        return {
            rg, prev, leadsND,
            leads: leadsND.filter((l) => l.f >= rg.desde && l.f <= rg.hasta),
            leadsPrev: prev ? leadsND.filter((l) => l.f >= prev.desde && l.f <= prev.hasta) : null,
            consumoND: DATA.consumo.filter((c) => pasaConsumo(c, null)),
            consumo: DATA.consumo.filter((c) => pasaConsumo(c, rg)),
            consumoPrev: prev ? DATA.consumo.filter((c) => pasaConsumo(c, prev)) : null,
            eventosND: DATA.eventos.filter((e) => ids.has(e.lead)),
        };
    }
    const conteos = (ls) => ({
        n: ls.length, cont: ls.filter((l) => l.estado !== 'nuevo').length, resp: ls.filter((l) => RESP.has(l.estado)).length,
        reun: ls.filter((l) => REUN.has(l.estado)).length, cerr: ls.filter((l) => l.estado === 'cerrado').length,
    });

    // ------------------------------------------------------------------ tooltip (elementos HTML) y plantilla de tooltip
    const tipEl = document.createElement('div');
    tipEl.id = 'vizTip'; tipEl.setAttribute('role', 'tooltip');
    document.body.appendChild(tipEl);

    function tipHtml(titulo, filas, pie) {
        return `<div style="font-weight:600;margin-bottom:6px">${esc(titulo)}</div>` + filas.map((f) =>
            `<div style="display:flex;align-items:center;gap:8px;margin:3px 0">${f.color ? `<span style="width:12px;height:2px;background:${f.color};display:inline-block;border-radius:1px"></span>` : ''}` +
            `<span style="color:${INK2};flex:1">${esc(f.nombre)}</span><strong style="font-weight:650">${esc(f.valor)}</strong></div>`).join('') +
            (pie ? `<div style="margin-top:6px;color:${INK2};font-size:.72rem">${esc(pie)}</div>` : '');
    }
    function ligarTip(el, fn) {
        const mover = (x, y) => {
            const r = tipEl.getBoundingClientRect();
            let px = x + 14, py = y + 14;
            if (px + r.width > innerWidth - 8) px = innerWidth - r.width - 8;
            if (py + r.height > innerHeight - 8) py = y - r.height - 14;
            tipEl.style.left = Math.max(8, px) + 'px'; tipEl.style.top = Math.max(8, py) + 'px';
        };
        const mostrar = (x, y) => { tipEl.innerHTML = fn(); tipEl.style.display = 'block'; mover(x, y); };
        const ocultar = () => { tipEl.style.display = 'none'; };
        el.addEventListener('pointerenter', (e) => mostrar(e.clientX, e.clientY));
        el.addEventListener('pointermove', (e) => mover(e.clientX, e.clientY));
        el.addEventListener('pointerleave', ocultar);
        el.addEventListener('focus', () => { const r = el.getBoundingClientRect(); mostrar(r.left, r.bottom); });
        el.addEventListener('blur', ocultar);
    }

    // ------------------------------------------------------------------ ECharts: base común
    function chart(id) {
        const el = $id('ch-' + id);
        if (!el) return null;
        if (!charts[id] || charts[id].isDisposed()) charts[id] = echarts.init(el, null, { renderer: 'svg' });
        return charts[id];
    }
    const tooltipBase = (extra) => Object.assign({
        confine: true, backgroundColor: SURF, borderColor: 'rgba(11,11,11,.12)', borderWidth: 1, padding: [9, 11],
        textStyle: { color: INK, fontSize: 12 }, extraCssText: 'box-shadow:0 6px 24px rgba(11,11,11,.14);border-radius:10px;',
    }, extra);
    const ejeCat = (data, extra) => Object.assign({ type: 'category', data, axisLine: { lineStyle: { color: BASE } }, axisTick: { show: false },
        axisLabel: { color: MUTED, fontSize: 11 }, splitLine: { show: false } }, extra);
    const ejeVal = (extra) => Object.assign({ type: 'value', minInterval: 1, axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: MUTED, fontSize: 11 }, splitLine: { lineStyle: { color: GRID, width: 1, type: 'solid' } } }, extra);
    const leyenda = (nombres) => ({ data: nombres, top: 0, left: 0, icon: 'roundRect', itemWidth: 10, itemHeight: 10, itemGap: 16,
        textStyle: { color: INK2, fontSize: 12 } });
    const barraR = [4, 4, 0, 0];

    function describir(id, texto) {
        const el = $id('ch-' + id);
        if (el) { el.setAttribute('role', 'img'); el.setAttribute('aria-label', texto); }
    }
    function tabla(id, cols, filas) { TABLAS[id] = { cols, filas }; if (UI.tabla[id]) pintarTabla(id); }
    function pintarTabla(id) {
        const cont = $id('tb-' + id), t = TABLAS[id];
        if (!cont || !t) return;
        cont.textContent = '';
        const tb = document.createElement('table');
        const tr0 = tb.createTHead().insertRow();
        t.cols.forEach((c, i) => { const th = document.createElement('th'); th.textContent = c; if (i) th.className = 'num'; tr0.appendChild(th); });
        const body = tb.createTBody();
        t.filas.forEach((f) => { const tr = body.insertRow(); f.forEach((v, i) => { const td = tr.insertCell(); td.textContent = v; if (i) td.className = 'num'; }); });
        cont.appendChild(tb);
    }

    // ------------------------------------------------------------------ acciones de filtro (clic en gráficos)
    function alternar(set, valor) { if (set.has(valor)) set.delete(valor); else set.add(valor); }
    function fijarMes(m) {
        F.preset = 'custom'; F.desde = mesInicio(m); F.hasta = mesFin(m) > DATA.config.hoy ? DATA.config.hoy : mesFin(m);
        render();
    }

    // ------------------------------------------------------------------ HERO: consumo del mes (cuenta, no se filtra)
    function pintarHero() {
        const hoy = DATA.config.hoy, m = mesDe(hoy);
        const delMes = DATA.consumo.filter((c) => mesDe(c.f) === m);
        const usados = suma(delMes, 'creditos'), ahorrados = suma(delMes, 'ahorrados');
        const cuota = (CUENTA && CUENTA.disponible && CUENTA.cuota) || DATA.config.cuota_mes;
        const dia = +hoy.slice(8, 10), dias = +mesFin(m).slice(8, 10);
        const proy = dia ? Math.round(usados / dia * dias) : usados;
        const p = Math.min(100, usados / cuota * 100);
        const nivel = p >= 90 ? 'crit' : p >= 70 ? 'warn' : 'ok';
        const estado = { crit: '⚠ Casi agotada: modera las búsquedas', warn: '▲ Atención: ya va por encima del 70%', ok: '✓ Dentro de la cuota' }[nivel];
        const primera = DATA.consumo.map((c) => c.f).sort()[0];
        let real = '';
        if (CUENTA && CUENTA.disponible) {
            const fuera = (CUENTA.usadas || 0) - usados;
            real = `SerpAPI informa <b>${fmt(CUENTA.usadas || 0)} de ${fmt(CUENTA.cuota || cuota)}</b> búsquedas usadas este mes (plan ${esc(CUENTA.plan || '—')}; quedan ${fmt(CUENTA.restantes ?? 0)}).` +
                (fuera > 0 ? ` ${fmt(fuera)} se hicieron fuera de esta app o antes de que registrara el consumo.` : '');
        } else {
            real = `La cuota mensual (${fmt(cuota)}) es la configurada en SERPAPI_CUOTA_MES; no se pudo consultar la cuenta real de SerpAPI.`;
        }
        $id('vizHero').innerHTML = `
            <div class="hero-kpi">
                <div class="eyebrow">Búsquedas de SerpAPI consumidas · ${esc(mesTxt(m))}</div>
                <div class="hero-num">${fmt(usados)} <small>/ ${fmt(cuota)}</small></div>
                <div class="meter ${nivel === 'ok' ? '' : nivel}" role="meter" aria-valuemin="0" aria-valuemax="${cuota}" aria-valuenow="${usados}" aria-label="Créditos usados este mes"><i style="width:${p.toFixed(1)}%"></i></div>
                <span class="estado ${nivel}">${esc(estado)}</span>
            </div>
            <div class="hero-datos">
                <div class="dato"><b>${fmt(Math.max(0, cuota - usados))}</b><span>créditos disponibles</span></div>
                <div class="dato"><b>${fmt(proy)}</b><span>proyección a fin de mes</span></div>
                <div class="dato"><b>${fmt(ahorrados)}</b><span>ahorrados por caché</span></div>
                <div class="dato"><b>${fmt(dias - dia)}</b><span>días restantes del mes</span></div>
            </div>
            <div class="hero-nota">${real}${primera ? ` <span class="nota-chica">Esta app registra su consumo desde ${esc(diaTxt(primera))} ${esc(primera.slice(0, 4))}.</span>` : ''}</div>`;
    }

    // ------------------------------------------------------------------ KPI
    function buckets(items, fecha, rg, n) {
        const dias = diffDays(rg.desde, rg.hasta) + 1, out = new Array(n).fill(0);
        items.forEach((it) => {
            const i = Math.min(n - 1, Math.floor(diffDays(rg.desde, fecha(it)) * n / dias));
            if (i >= 0) out[i] += it.__v == null ? 1 : it.__v;
        });
        return out;
    }
    function spark(arr) {
        const w = 84, h = 28, p = 3, max = Math.max(1, ...arr), n = arr.length;
        const pts = arr.map((v, i) => [p + i * (w - 2 * p) / Math.max(1, n - 1), h - p - (v / max) * (h - 2 * p)]);
        const d = pts.map((q, i) => (i ? 'L' : 'M') + q[0].toFixed(1) + ' ' + q[1].toFixed(1)).join('');
        const [lx, ly] = pts[pts.length - 1];
        return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><path d="${d}" fill="none" stroke="${MUTED}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="4" fill="${AZUL}" stroke="${SURF}" stroke-width="2"/></svg>`;
    }
    function deltaHtml(cur, prev, neutro) {
        if (prev == null) return '<span class="delta neutro">Sin periodo anterior</span>';
        if (prev === 0) return cur ? '<span class="delta neutro">▲ nuevo vs periodo anterior</span>' : '<span class="delta neutro">= sin cambios</span>';
        const d = Math.round((cur - prev) / prev * 100);
        if (!d) return '<span class="delta neutro">= sin cambios</span>';
        const cls = neutro ? 'neutro' : d > 0 ? 'sube' : 'baja';
        return `<span class="delta ${cls}">${d > 0 ? '▲ +' : '▼ '}${d}% vs periodo anterior</span>`;
    }
    function pintarKpis() {
        const c = conteos(S.leads), p = S.leadsPrev ? conteos(S.leadsPrev) : null;
        const cred = suma(S.consumo, 'creditos'), credP = S.consumoPrev ? suma(S.consumoPrev, 'creditos') : null;
        const porLead = c.n ? cred / c.n : null;
        const sp = (arr, pred) => spark(buckets(arr.filter(pred), (l) => l.f, S.rg, 12));
        const K = [
            { et: 'Créditos usados', val: cred, prev: credP, neutro: true, nota: porLead == null ? 'Sin leads en el periodo' : `${nf1.format(porLead)} por lead nuevo`,
                sp: spark(buckets(S.consumo.map((x) => ({ f: x.f, __v: x.creditos })), (x) => x.f, S.rg, 12)) },
            { et: 'Leads generados', val: c.n, prev: p && p.n, nota: `${fmt(S.leads.filter((l) => l.prioridad === 'alta').length)} de prioridad alta`, sp: sp(S.leads, () => true) },
            { et: 'Contactados', val: c.cont, prev: p && p.cont, nota: `${pctTxt(pct(c.cont, c.n))} de los leads`, sp: sp(S.leads, (l) => l.estado !== 'nuevo') },
            { et: 'Respondieron', val: c.resp, prev: p && p.resp, nota: `${pctTxt(pct(c.resp, c.cont))} de los contactados`, sp: sp(S.leads, (l) => RESP.has(l.estado)) },
            { et: 'Reuniones', val: c.reun, prev: p && p.reun, nota: `${pctTxt(pct(c.reun, c.resp))} de los que respondieron`, sp: sp(S.leads, (l) => REUN.has(l.estado)) },
            { et: 'Cierres', val: c.cerr, prev: p && p.cerr, nota: cred && c.cerr ? `${nf1.format(cred / c.cerr)} créditos por cierre` : `${pctTxt(pct(c.cerr, c.cont))} de los contactados`, sp: sp(S.leads, (l) => l.estado === 'cerrado') },
        ];
        $id('vizKpis').innerHTML = K.map((k) => `<div class="vkpi"><div class="et">${esc(k.et)}</div><div class="val">${fmt(k.val)}</div>
            <div>${deltaHtml(k.val, k.prev, k.neutro)}</div><div class="nota">${esc(k.nota)}</div>${k.sp}</div>`).join('');
    }

    // ------------------------------------------------------------------ Consumo de créditos (mensual / diario)
    function pintarConsumo() {
        const ch = chart('consumo'); if (!ch) return;
        const hoy = DATA.config.hoy, modo = UI.consumoModo, rg = S.rg;
        let cats, etiquetas, fuente, cuota = null, enRango;
        if (modo === 'mes') {
            const m1 = mesDe(hoy);
            const primero = S.consumoND.map((c) => c.f).sort()[0] || hoy;
            let m0 = [mesDe(primero), mesDe(rg.desde), restaMeses(m1, 5)].sort()[0];
            if (m0 < restaMeses(m1, 23)) m0 = restaMeses(m1, 23);
            cats = listaMeses(m0, m1); etiquetas = cats.map(mesTxt);
            fuente = (c) => mesDe(c.f); cuota = (CUENTA && CUENTA.disponible && CUENTA.cuota) || DATA.config.cuota_mes;
            enRango = cats.map((m) => mesFin(m) >= rg.desde && mesInicio(m) <= rg.hasta);
        } else {
            const hasta = rg.hasta, desde = rg.desde < addDays(hasta, -44) ? addDays(hasta, -44) : rg.desde;
            cats = []; for (let d = desde; d <= hasta; d = addDays(d, 1)) cats.push(d);
            etiquetas = cats.map(diaTxt); fuente = (c) => c.f; enRango = cats.map(() => true);
        }
        const base = modo === 'mes' ? S.consumoND : S.consumo;
        const ix = Object.fromEntries(cats.map((k, i) => [k, i]));
        const rad = cats.map(() => 0), red = cats.map(() => 0), aho = cats.map(() => 0);
        base.forEach((c) => { const i = ix[fuente(c)]; if (i == null) return; (c.tipo === 'radar' ? rad : red)[i] += c.creditos; aho[i] += c.ahorrados; });
        const tot = cats.map((_, i) => rad[i] + red[i]);
        const maxI = tot.indexOf(Math.max(...tot)), ultI = tot.length - 1;
        const dato = (arr) => arr.map((v, i) => ({ value: v, itemStyle: { opacity: enRango[i] ? 1 : 0.35 } }));
        const etiqueta = { show: true, position: 'top', color: INK2, fontSize: 11, fontWeight: 600,
            formatter: (p) => ((p.dataIndex === maxI || p.dataIndex === ultI) && tot[p.dataIndex] ? tot[p.dataIndex] : '') };
        ch.setOption({
            animationDuration: 400, legend: leyenda(['Radar (Maps)', 'Búsqueda de redes']),
            grid: { left: 34, right: 18, top: 38, bottom: 26 },
            tooltip: tooltipBase({ trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(11,11,11,.04)' } },
                formatter: (ps) => { const i = ps[0].dataIndex; return tipHtml(etiquetas[i], [
                    { color: C.radar, nombre: 'Radar (Maps)', valor: fmt(rad[i]) }, { color: C.redes, nombre: 'Búsqueda de redes', valor: fmt(red[i]) },
                    { nombre: 'Total', valor: fmt(tot[i]) + (cuota ? ` (${Math.round(tot[i] / cuota * 100)}% de la cuota)` : '') },
                    { nombre: 'Ahorrado por caché', valor: fmt(aho[i]) }], enRango[i] ? '' : 'Fuera del rango de fechas activo'); } }),
            xAxis: ejeCat(etiquetas),
            yAxis: ejeVal({ max: (v) => Math.ceil(Math.max(v.max * 1.15, cuota ? cuota * 1.12 : 4)) }),
            series: [
                { name: 'Radar (Maps)', type: 'bar', stack: 't', barMaxWidth: 24, data: dato(rad), itemStyle: { color: C.radar, borderColor: SURF, borderWidth: 1 },
                    markLine: cuota ? { silent: true, symbol: 'none', lineStyle: { color: INK2, width: 1.5, type: 'solid' },
                        label: { formatter: `Cuota ${fmt(cuota)}`, position: 'insideStartTop', color: INK2, fontSize: 11 }, data: [{ yAxis: cuota }] } : undefined },
                { name: 'Búsqueda de redes', type: 'bar', stack: 't', barMaxWidth: 24, data: dato(red),
                    itemStyle: { color: C.redes, borderColor: SURF, borderWidth: 1, borderRadius: barraR }, label: etiqueta },
            ],
        }, true);
        ch.off('click');
        ch.on('click', (p) => { if (modo === 'mes') fijarMes(cats[p.dataIndex]); else { F.preset = 'custom'; F.desde = F.hasta = cats[p.dataIndex]; render(); } });
        describir('consumo', `Créditos de SerpAPI por ${modo === 'mes' ? 'mes' : 'día'}: total ${fmt(suma(tot.map((v) => ({ v })), 'v'))}.`);
        tabla('consumo', [modo === 'mes' ? 'Mes' : 'Día', 'Radar', 'Redes', 'Total', 'Ahorrado por caché'],
            cats.map((_, i) => [etiquetas[i], fmt(rad[i]), fmt(red[i]), fmt(tot[i]), fmt(aho[i])]));

        const cred = suma(S.consumo, 'creditos'), ah = suma(S.consumo, 'ahorrados'), c = conteos(S.leads);
        const conEmail = S.leads.filter((l) => l.email).length;
        const e = (v) => (v == null || !isFinite(v) ? '—' : nf1.format(v));
        $id('vizEficiencia').innerHTML = [
            [e(c.n ? cred / c.n : null), 'créditos por lead nuevo'], [e(conEmail ? cred / conEmail : null), 'créditos por lead con email'],
            [e(c.resp ? cred / c.resp : null), 'créditos por respuesta'], [fmt(ah), 'créditos ahorrados por caché'],
        ].map(([v, t]) => `<div class="dato"><b>${v}</b><span>${t}</span></div>`).join('');
    }

    // ------------------------------------------------------------------ Actividad semanal (selección por arrastre)
    function pintarActividad() {
        const ch = chart('actividad'); if (!ch) return;
        const hoy = DATA.config.hoy;
        const fechas = [...S.leadsND.map((l) => l.f), ...S.eventosND.map((e) => e.f)].filter(Boolean).sort();
        const ini = lunes(fechas[0] || hoy);
        let semanas = []; for (let d = ini; d <= lunes(hoy); d = addDays(d, 7)) semanas.push(d);
        semanas = semanas.slice(-52);
        const ix = Object.fromEntries(semanas.map((s, i) => [s, i]));
        const lead = semanas.map(() => 0), cont = semanas.map(() => 0), resp = semanas.map(() => 0);
        S.leadsND.forEach((l) => { const i = ix[lunes(l.f)]; if (i != null) lead[i]++; });
        S.eventosND.filter((e) => e.estado === 'contactado').forEach((e) => { const i = ix[lunes(e.f)]; if (i != null) cont[i]++; });
        const primera = {};
        S.eventosND.filter((e) => RESP.has(e.estado)).forEach((e) => { if (!primera[e.lead] || e.f < primera[e.lead]) primera[e.lead] = e.f; });
        Object.values(primera).forEach((f) => { const i = ix[lunes(f)]; if (i != null) resp[i]++; });
        const rg = S.rg, a = Math.max(semanas[0], lunes(rg.desde)), b = Math.min(semanas[semanas.length - 1], lunes(rg.hasta));
        const serie = (nombre, datos, color, extra) => Object.assign({ name: nombre, type: 'line', data: datos, showSymbol: false, symbol: 'circle', symbolSize: 8,
            lineStyle: { width: 2, color }, itemStyle: { color, borderColor: SURF, borderWidth: 2 }, areaStyle: { color, opacity: 0.1 }, emphasis: { focus: 'none' } }, extra);
        ch.setOption({
            animationDuration: 400, legend: leyenda(['Leads creados', 'Contactos', 'Respuestas']),
            grid: { left: 34, right: 18, top: 38, bottom: 26 },
            tooltip: tooltipBase({ trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: BASE, width: 1 } },
                formatter: (ps) => { const i = ps[0].dataIndex; return tipHtml(`Semana del ${diaTxt(semanas[i])}`, [
                    { color: C.leads, nombre: 'Leads creados', valor: fmt(lead[i]) }, { color: C.contactos, nombre: 'Contactos', valor: fmt(cont[i]) },
                    { color: C.respuestas, nombre: 'Respuestas', valor: fmt(resp[i]) }], 'Arrastra para filtrar por fechas'); } }),
            toolbox: { show: false },
            brush: { xAxisIndex: 0, brushType: 'lineX', brushMode: 'single', toolbox: [], throttleType: 'debounce', throttleDelay: 200,
                brushStyle: { borderWidth: 1, color: 'rgba(42,120,214,.12)', borderColor: AZUL } },
            xAxis: ejeCat(semanas, { boundaryGap: false, axisLabel: { color: MUTED, fontSize: 11, formatter: diaTxt, hideOverlap: true } }),
            yAxis: ejeVal(),
            series: [
                serie('Leads creados', lead, C.leads, { markArea: { silent: true, itemStyle: { color: 'rgba(42,120,214,.07)' }, data: [[{ xAxis: a }, { xAxis: b }]] } }),
                serie('Contactos', cont, C.contactos), serie('Respuestas', resp, C.respuestas),
            ],
        }, true);
        ch.dispatchAction({ type: 'takeGlobalCursor', key: 'brush', brushOption: { brushType: 'lineX', brushMode: 'single' } });
        ch.off('brushEnd');
        ch.on('brushEnd', (ev) => {
            const ar = ev.areas && ev.areas[0]; if (!ar) return;
            let [i0, i1] = ar.coordRange.map((v) => (typeof v === 'number' ? Math.round(v) : semanas.indexOf(v)));
            if (i0 > i1) [i0, i1] = [i1, i0];
            i0 = Math.max(0, i0); i1 = Math.min(semanas.length - 1, i1);
            F.preset = 'custom'; F.desde = semanas[i0]; F.hasta = addDays(semanas[i1], 6) > hoy ? hoy : addDays(semanas[i1], 6);
            ch.dispatchAction({ type: 'brush', areas: [] });
            render();
        });
        describir('actividad', `Actividad semanal: ${fmt(suma(lead.map((v) => ({ v })), 'v'))} leads, ${fmt(suma(cont.map((v) => ({ v })), 'v'))} contactos y ${fmt(suma(resp.map((v) => ({ v })), 'v'))} respuestas.`);
        tabla('actividad', ['Semana', 'Leads creados', 'Contactos', 'Respuestas'], semanas.map((s, i) => [diaTxt(s), fmt(lead[i]), fmt(cont[i]), fmt(resp[i])]));
    }

    // ------------------------------------------------------------------ Embudo (barras ordinales, HTML)
    function pintarEmbudo() {
        const c = conteos(S.leads), desc = S.leads.filter((l) => l.estado === 'descartado').length;
        const etapas = [['Leads', c.n], ['Contactados', c.cont], ['Respondieron', c.resp], ['Reunión', c.reun], ['Cerrados', c.cerr]];
        const cont = $id('ch-embudo'); cont.textContent = '';
        if (!c.n) { cont.innerHTML = '<div class="vacio-viz">Sin leads en este periodo.</div>'; tabla('embudo', ['Etapa', 'Leads'], []); return; }
        const wrap = document.createElement('div'); wrap.className = 'embudo';
        etapas.forEach(([nombre, n], i) => {
            const antes = i ? etapas[i - 1][1] : null, fila = document.createElement('div');
            fila.className = 'emb-fila'; fila.tabIndex = 0;
            fila.innerHTML = `<span class="nombre">${esc(nombre)}</span><div class="emb-pista"><div class="emb-barra" style="width:${(n / c.n * 100).toFixed(1)}%;background:${ORD[i]}"></div></div>` +
                `<div class="valor"><b>${fmt(n)}</b><span>${i ? `${pctTxt(pct(n, antes))} del paso anterior` : 'base del periodo'}</span></div>`;
            ligarTip(fila, () => tipHtml(nombre, [{ nombre: 'Leads', valor: fmt(n) }, { nombre: 'Del total', valor: pctTxt(pct(n, c.n)) },
                ...(i ? [{ nombre: 'Del paso anterior', valor: pctTxt(pct(n, antes)) }] : [])]));
            wrap.appendChild(fila);
        });
        cont.appendChild(wrap);
        const nota = document.createElement('div'); nota.className = 'nota-chica'; nota.style.marginTop = '10px';
        nota.textContent = `Descartados: ${fmt(desc)} (no se incluyen en las etapas). Cada etapa cuenta los leads que llegaron al menos hasta ella.`;
        cont.appendChild(nota);
        describir('embudo', `Embudo: ${etapas.map(([n, v]) => `${n} ${v}`).join(', ')}.`);
        tabla('embudo', ['Etapa', 'Leads', 'Del total', 'Del paso anterior'], etapas.map(([n, v], i) => [n, fmt(v), pctTxt(pct(v, c.n)), i ? pctTxt(pct(v, etapas[i - 1][1])) : '—']));
    }

    // ------------------------------------------------------------------ Calidad: prioridad (barra segmentada) + score
    function pintarCalidad() {
        const total = S.leads.length, cont = $id('ch-prio');
        cont.textContent = '';
        const cuenta = { alta: 0, media: 0, baja: 0 };
        S.leads.forEach((l) => { cuenta[l.prioridad] = (cuenta[l.prioridad] || 0) + 1; });
        if (!total) { cont.innerHTML = '<div class="vacio-viz">Sin leads en este periodo.</div>'; }
        else {
            const barra = document.createElement('div'); barra.className = 'seg-alta';
            ['alta', 'media', 'baja'].forEach((k) => {
                if (!cuenta[k]) return;
                const b = document.createElement('button'); b.type = 'button'; b.className = 'seg-bloque';
                b.style.width = (cuenta[k] / total * 100) + '%'; b.style.background = PRIO[k].c;
                b.style.opacity = F.prioridad.size && !F.prioridad.has(k) ? '.4' : '1';
                const share = Math.round(cuenta[k] / total * 100);
                b.textContent = cuenta[k] / total >= 0.12 ? share + '%' : '';
                b.setAttribute('aria-label', `Prioridad ${PRIO[k].txt}: ${cuenta[k]} leads (${share}%). Clic para filtrar`);
                b.addEventListener('click', () => { alternar(F.prioridad, k); render(); });
                ligarTip(b, () => tipHtml(`Prioridad ${PRIO[k].txt}`, [{ nombre: 'Leads', valor: fmt(cuenta[k]) }, { nombre: 'Del total', valor: share + '%' }], 'Clic para filtrar'));
                barra.appendChild(b);
            });
            const ley = document.createElement('div'); ley.className = 'seg-leyenda';
            ley.innerHTML = ['alta', 'media', 'baja'].map((k) => `<span><i style="background:${PRIO[k].c}"></i>${PRIO[k].txt} · ${fmt(cuenta[k])}</span>`).join('');
            cont.appendChild(barra); cont.appendChild(ley);
        }
        // histograma de score
        const ch = chart('score'); if (!ch) return;
        const bins = new Array(10).fill(0);
        S.leads.forEach((l) => { bins[Math.min(9, Math.floor((l.score || 0) / 10))]++; });
        const nombres = bins.map((_, i) => (i === 9 ? '90–100' : `${i * 10}–${i * 10 + 9}`));
        const sel = (i) => !F.score || (F.score[0] <= i * 10 && F.score[1] >= i * 10);
        ch.setOption({
            animationDuration: 400, grid: { left: 30, right: 10, top: 12, bottom: 26 },
            tooltip: tooltipBase({ trigger: 'item', formatter: (p) => tipHtml(`Puntuación ${nombres[p.dataIndex]}`,
                [{ color: AZUL, nombre: 'Leads', valor: fmt(bins[p.dataIndex]) }, { nombre: 'Del total', valor: pctTxt(pct(bins[p.dataIndex], total)) }], 'Clic para filtrar') }),
            xAxis: ejeCat(nombres.map((n, i) => (i % 2 ? '' : n.split('–')[0])), { axisLabel: { color: MUTED, fontSize: 11, interval: 0 } }),
            yAxis: ejeVal(),
            series: [{ type: 'bar', barMaxWidth: 24, data: bins.map((v, i) => ({ value: v, itemStyle: { color: AZUL, opacity: sel(i) ? 1 : 0.3, borderRadius: barraR } })),
                emphasis: { itemStyle: { color: '#256abf' } } }],
        }, true);
        ch.off('click');
        ch.on('click', (p) => { const a = p.dataIndex * 10, b = p.dataIndex === 9 ? 100 : a + 9;
            F.score = F.score && F.score[0] === a ? null : [a, b]; render(); });
        describir('score', `Distribución de puntuación de ${total} leads.`);
        tabla('score', ['Concepto', 'Leads'], [
            ...['alta', 'media', 'baja'].map((k) => [`Prioridad ${PRIO[k].txt}`, fmt(cuenta[k])]),
            ...nombres.map((n, i) => [`Puntuación ${n}`, fmt(bins[i])])]);
    }

    // ------------------------------------------------------------------ Oportunidades (barras ordenadas)
    function pintarOpps() {
        const ch = chart('opps'); if (!ch) return;
        const g = {};
        S.leads.forEach((l) => l.oportunidades.forEach((o) => {
            const d = g[o] = g[o] || { n: 0, cont: 0, resp: 0 };
            d.n++; d.cont += l.estado !== 'nuevo'; d.resp += RESP.has(l.estado);
        }));
        const claves = Object.keys(g).sort((a, b) => g[b].n - g[a].n);
        const orden = claves.slice().reverse();
        const activo = F.oportunidad.size > 0;
        ch.setOption({
            animationDuration: 400, grid: { left: 130, right: 46, top: 6, bottom: 22 },
            tooltip: tooltipBase({ trigger: 'item', formatter: (p) => { const k = orden[p.dataIndex], d = g[k];
                return tipHtml(OPP[k] || k, [{ color: AZUL, nombre: 'Leads', valor: fmt(d.n) }, { nombre: 'Contactados', valor: fmt(d.cont) },
                    { nombre: 'Respondieron', valor: fmt(d.resp) }, { nombre: 'Tasa de respuesta', valor: pctTxt(pct(d.resp, d.cont)) }], 'Clic para filtrar'); } }),
            xAxis: ejeVal(), yAxis: ejeCat(orden.map((k) => OPP[k] || k), { axisLabel: { color: INK2, fontSize: 12 }, axisLine: { show: false } }),
            series: [{ type: 'bar', barMaxWidth: 16, data: orden.map((k) => ({ value: g[k].n, itemStyle: { color: AZUL, opacity: !activo || F.oportunidad.has(k) ? 1 : 0.3, borderRadius: [0, 4, 4, 0] } })),
                label: { show: true, position: 'right', color: INK2, fontSize: 11, fontWeight: 600 }, emphasis: { itemStyle: { color: '#256abf' } } }],
        }, true);
        ch.off('click');
        ch.on('click', (p) => { alternar(F.oportunidad, orden[p.dataIndex]); render(); });
        describir('opps', `Leads por tipo de oportunidad: ${claves.map((k) => `${OPP[k] || k} ${g[k].n}`).join(', ') || 'sin datos'}.`);
        tabla('opps', ['Oportunidad', 'Leads', 'Contactados', 'Respondieron', 'Tasa de respuesta'],
            claves.map((k) => [OPP[k] || k, fmt(g[k].n), fmt(g[k].cont), fmt(g[k].resp), pctTxt(pct(g[k].resp, g[k].cont))]));
    }

    // ------------------------------------------------------------------ Mapa de calor ciudad × sector
    function pintarCalor() {
        const ch = chart('calor'); if (!ch) return;
        const m = UI.heat, cel = {};
        const get = (c, s) => cel[c + '|' + s] = cel[c + '|' + s] || { leads: 0, cont: 0, resp: 0, cred: 0 };
        S.leads.forEach((l) => { const d = get(l.ciudad, l.sector); d.leads++; d.cont += l.estado !== 'nuevo'; d.resp += RESP.has(l.estado); });
        S.consumo.forEach((c) => { get(c.ciudad, c.sector).cred += c.creditos; });
        const tot = (dim) => { const t = {}; Object.entries(cel).forEach(([k, d]) => { const n = k.split('|')[dim === 'c' ? 0 : 1]; t[n] = (t[n] || 0) + (m === 'creditos' ? d.cred : d.leads); }); return t; };
        const top = (t) => Object.keys(t).sort((a, b) => t[b] - t[a]).slice(0, 8);
        const ciudades = top(tot('c')), sectores = top(tot('s'));
        const valor = (d) => (!d ? null : m === 'leads' ? d.leads : m === 'creditos' ? d.cred : (d.cont ? Math.round(d.resp / d.cont * 1000) / 10 : null));
        const datos = [], vals = [];
        ciudades.forEach((c, y) => sectores.forEach((s, x) => { const v = valor(cel[c + '|' + s]); datos.push({ value: [x, y, v == null ? '-' : v], v }); if (v != null) vals.push(v); }));
        const max = Math.max(1, ...vals), unidad = m === 'tasa' ? '%' : '';
        datos.forEach((d) => { d.label = { color: d.v != null && d.v / max > 0.5 ? '#ffffff' : INK }; });
        const pocas = ciudades.length * sectores.length <= 49;
        ch.setOption({
            animationDuration: 400, grid: { left: 110, right: 16, top: 8, bottom: 58 },
            tooltip: tooltipBase({ trigger: 'item', formatter: (p) => { const c = ciudades[p.value[1]], s = sectores[p.value[0]], d = cel[c + '|' + s] || { leads: 0, cont: 0, resp: 0, cred: 0 };
                return tipHtml(`${c} · ${s}`, [{ nombre: 'Leads', valor: fmt(d.leads) }, { nombre: 'Contactados', valor: fmt(d.cont) }, { nombre: 'Respondieron', valor: fmt(d.resp) },
                    { nombre: 'Tasa de respuesta', valor: pctTxt(pct(d.resp, d.cont)) }, { nombre: 'Créditos', valor: fmt(d.cred) }], 'Clic para filtrar ciudad y sector'); } }),
            xAxis: ejeCat(sectores, { axisLabel: { color: INK2, fontSize: 11, interval: 0, width: 80, overflow: 'truncate' }, splitArea: { show: false }, axisLine: { show: false } }),
            yAxis: ejeCat(ciudades, { inverse: true, axisLabel: { color: INK2, fontSize: 12, width: 100, overflow: 'truncate' }, axisLine: { show: false } }),
            visualMap: { type: 'continuous', min: 0, max, calculable: false, orient: 'horizontal', left: 'center', bottom: 6, itemWidth: 12, itemHeight: 140,
                inRange: { color: SEQ }, textStyle: { color: INK2, fontSize: 11 }, text: [`alto${unidad ? ' (%)' : ''}`, 'bajo'] },
            series: [{ type: 'heatmap', data: datos, itemStyle: { borderColor: SURF, borderWidth: 2, borderRadius: 3 },
                label: { show: pocas, fontSize: 11, fontWeight: 600, formatter: (p) => (p.value[2] === '-' || p.value[2] === 0 ? '' : p.value[2] + unidad) }, emphasis: { itemStyle: { borderColor: INK, borderWidth: 2 } } }],
        }, true);
        ch.off('click');
        ch.on('click', (p) => { const c = ciudades[p.value[1]], s = sectores[p.value[0]];
            const igual = F.ciudad.size === 1 && F.ciudad.has(c) && F.sector.size === 1 && F.sector.has(s);
            F.ciudad = new Set(igual ? [] : [c]); F.sector = new Set(igual ? [] : [s]); render(); });
        const nombreM = { leads: 'leads', tasa: 'tasa de respuesta (%)', creditos: 'créditos' }[m];
        describir('calor', `Mapa de calor de ${nombreM} por ciudad y sector.`);
        tabla('calor', ['Ciudad', 'Sector', 'Leads', 'Contactados', 'Respondieron', 'Tasa de respuesta', 'Créditos'],
            Object.entries(cel).map(([k, d]) => { const [c, s] = k.split('|'); return [c, s, fmt(d.leads), fmt(d.cont), fmt(d.resp), pctTxt(pct(d.resp, d.cont)), fmt(d.cred)]; })
                .sort((a, b) => Number(b[2].replace(/\D/g, '')) - Number(a[2].replace(/\D/g, ''))));
    }

    // ------------------------------------------------------------------ Rendimiento (usuario / canal / sector)
    function pintarRend() {
        const ch = chart('rend'); if (!ch) return;
        const dim = UI.rend, g = {};
        S.leads.filter((l) => l.estado !== 'nuevo').forEach((l) => {
            const clave = dim === 'usuario' ? String(l.usuario) : dim === 'canal' ? (l.canal || '—') : l.sector;
            const d = g[clave] = g[clave] || { cont: 0, resp: 0 };
            d.cont++; d.resp += RESP.has(l.estado);
        });
        const claves = Object.keys(g).sort((a, b) => g[b].cont - g[a].cont).slice(0, 8);
        const nombre = (k) => (dim === 'usuario' ? (DATA.usuarios[k] || '—') : dim === 'canal' ? (CANAL_TXT[k] || k) : k);
        const filtro = dim === 'usuario' ? F.usuario : dim === 'sector' ? F.sector : null;
        const op = (k) => (filtro && filtro.size && !filtro.has(k) ? 0.3 : 1);
        ch.setOption({
            animationDuration: 400, legend: leyenda(['Contactados', 'Respondieron']), grid: { left: 34, right: 12, top: 38, bottom: 28 },
            tooltip: tooltipBase({ trigger: 'item', formatter: (p) => { const k = claves[p.dataIndex], d = g[k];
                return tipHtml(nombre(k), [{ color: C.contactos, nombre: 'Contactados', valor: fmt(d.cont) }, { color: C.respuestas, nombre: 'Respondieron', valor: fmt(d.resp) },
                    { nombre: 'Tasa de respuesta', valor: pctTxt(pct(d.resp, d.cont)) }], filtro ? 'Clic para filtrar' : ''); } }),
            xAxis: ejeCat(claves.map(nombre), { axisLabel: { color: INK2, fontSize: 11, interval: 0, width: 80, overflow: 'truncate' } }), yAxis: ejeVal(),
            series: [
                { name: 'Contactados', type: 'bar', barMaxWidth: 20, barGap: '12%', data: claves.map((k) => ({ value: g[k].cont, itemStyle: { color: C.contactos, opacity: op(k), borderRadius: barraR } })) },
                { name: 'Respondieron', type: 'bar', barMaxWidth: 20, data: claves.map((k) => ({ value: g[k].resp, itemStyle: { color: C.respuestas, opacity: op(k), borderRadius: barraR } })) },
            ],
        }, true);
        ch.off('click');
        ch.on('click', (p) => { if (filtro) { alternar(filtro, claves[p.dataIndex]); render(); } });
        describir('rend', `Contactados y respondieron por ${dim}.`);
        tabla('rend', [dim[0].toUpperCase() + dim.slice(1), 'Contactados', 'Respondieron', 'Tasa de respuesta'],
            claves.map((k) => [nombre(k), fmt(g[k].cont), fmt(g[k].resp), pctTxt(pct(g[k].resp, g[k].cont))]));
    }

    // ------------------------------------------------------------------ Plantillas A/B
    function pintarPlantillas() {
        const g = {};
        S.leads.filter((l) => l.plantilla).forEach((l) => {
            const d = g[l.plantilla] = g[l.plantilla] || { n: 0, cont: 0, resp: 0 };
            d.n++; d.cont += l.estado !== 'nuevo'; d.resp += RESP.has(l.estado);
        });
        const claves = Object.keys(g).sort((a, b) => (pct(g[b].resp, g[b].cont) || -1) - (pct(g[a].resp, g[a].cont) || -1) || g[b].cont - g[a].cont);
        const nom = (k) => { const [a, c, v] = k.split(':'); return `${OPP[a] || a} · ${c === 'wa' ? 'WhatsApp' : 'Email'} · variante ${(v || '').toUpperCase()}`; };
        const cont = $id('ch-plantillas'); cont.textContent = '';
        if (!claves.length) { cont.innerHTML = '<div class="vacio-viz">Aún no hay plantillas con leads en este periodo.</div>'; tabla('plantillas', ['Plantilla', 'Leads'], []); return; }
        const tb = document.createElement('table'); tb.className = 'vt';
        tb.innerHTML = '<thead><tr><th>Plantilla</th><th class="num">Leads</th><th class="num">Contactados</th><th class="num">Respondieron</th><th>Tasa de respuesta</th></tr></thead>';
        const body = document.createElement('tbody');
        claves.forEach((k) => {
            const d = g[k], t = pct(d.resp, d.cont), tr = document.createElement('tr');
            const celdas = [[nom(k), ''], [fmt(d.n), 'num'], [fmt(d.cont), 'num'], [fmt(d.resp), 'num']];
            celdas.forEach(([txt, cls]) => { const td = document.createElement('td'); td.textContent = txt; td.className = cls; tr.appendChild(td); });
            const td = document.createElement('td');
            td.innerHTML = `<span class="mini-meter"><i style="width:${t || 0}%"></i></span>${pctTxt(t)}${d.cont < 10 && d.cont ? ' <span class="nota-chica">muestra pequeña</span>' : ''}`;
            tr.appendChild(td); body.appendChild(tr);
            ligarTip(tr, () => tipHtml(nom(k), [{ nombre: 'Leads', valor: fmt(d.n) }, { nombre: 'Contactados', valor: fmt(d.cont) }, { nombre: 'Respondieron', valor: fmt(d.resp) },
                { nombre: 'Tasa de respuesta', valor: pctTxt(t) }], d.cont < 10 ? 'Con menos de 10 contactos, la tasa aún no es fiable.' : ''));
        });
        tb.appendChild(body); cont.appendChild(tb);
        tabla('plantillas', ['Plantilla', 'Leads', 'Contactados', 'Respondieron', 'Tasa de respuesta'], claves.map((k) => [nom(k), fmt(g[k].n), fmt(g[k].cont), fmt(g[k].resp), pctTxt(pct(g[k].resp, g[k].cont))]));
    }

    // ------------------------------------------------------------------ Listas accionables
    function listaLeads(contId, filas, vacio, comoContacto, extra) {
        const cont = $id(contId); cont.textContent = '';
        if (!filas.length) { cont.innerHTML = `<div class="vacio-viz">${esc(vacio)}</div>`; return; }
        const tb = document.createElement('table'); tb.className = 'vt';
        const body = document.createElement('tbody');
        filas.forEach((l) => {
            const tr = document.createElement('tr'); tr.className = 'click'; tr.tabIndex = 0;
            const td0 = document.createElement('td'); const pill = document.createElement('span');
            pill.className = 'pill-score'; pill.style.background = (PRIO[l.prioridad] || PRIO.baja).c; pill.textContent = l.score; td0.appendChild(pill);
            const td1 = document.createElement('td'); const b = document.createElement('b'); b.textContent = l.nombre; b.style.fontWeight = 600;
            const sub = document.createElement('div'); sub.className = 'nota-chica'; sub.textContent = `${l.ciudad} · ${l.sector}${extra ? ' · ' + extra(l) : ''}`;
            td1.append(b, sub);
            const td2 = document.createElement('td'); td2.className = 'nota-chica';
            td2.textContent = l.oportunidades.slice(0, 2).map((o) => OPP[o] || o).join(', ');
            tr.append(td0, td1, td2); body.appendChild(tr);
            const abrir = () => window.abrirLead && window.abrirLead(l.id, comoContacto);
            tr.addEventListener('click', abrir);
            tr.addEventListener('keydown', (e) => { if (e.key === 'Enter') abrir(); });
        });
        tb.appendChild(body); cont.appendChild(tb);
    }
    function pintarPendientes() {
        const hoy = DATA.config.hoy;
        const nuevos = S.leadsND.filter((l) => l.estado === 'nuevo').sort((a, b) => b.score - a.score).slice(0, 8);
        listaLeads('ch-top', nuevos, 'No quedan leads nuevos con estos filtros.', true);
        const venc = S.leadsND.filter((l) => l.seguimiento && l.seguimiento <= hoy && ['contactado', 'respondio'].includes(l.estado))
            .sort((a, b) => a.seguimiento.localeCompare(b.seguimiento)).slice(0, 8);
        listaLeads('ch-venc', venc, 'Sin seguimientos vencidos. Todo al día.', false, (l) => `vencido el ${diaTxt(l.seguimiento)}`);
        tabla('top', ['Lead', 'Puntuación', 'Ciudad', 'Sector'], nuevos.map((l) => [l.nombre, l.score, l.ciudad, l.sector]));
        tabla('venc', ['Lead', 'Vencido el', 'Ciudad'], venc.map((l) => [l.nombre, l.seguimiento, l.ciudad]));
    }

    // ------------------------------------------------------------------ Filtros (una fila) y chips
    function listaChips() {
        const etiq = { ciudad: (v) => v, sector: (v) => v, usuario: (v) => DATA.usuarios[v] || v, prioridad: (v) => PRIO[v].txt, oportunidad: (v) => OPP[v] || v };
        const nombresDim = { ciudad: 'Ciudad', sector: 'Sector', usuario: 'Usuario', prioridad: 'Prioridad', oportunidad: 'Oportunidad' };
        const chips = [];
        Object.keys(etiq).forEach((dim) => F[dim].forEach((v) => chips.push({ t: `${nombresDim[dim]}: ${etiq[dim](v)}`, quitar: () => F[dim].delete(v) })));
        if (F.score) chips.push({ t: `Puntuación ${F.score[0]}–${F.score[1]}`, quitar: () => { F.score = null; } });
        return chips;
    }
    const rangoTxt = () => { const p = PRESETS.find(([k]) => k === F.preset); const r = rango(); return p ? p[1] : `${r.desde} → ${r.hasta}`; };

    // ------------------------------------------------------------------ Vistas guardadas
    function serializar() {
        const custom = F.preset === 'custom';
        return { preset: F.preset, desde: custom ? F.desde : null, hasta: custom ? F.hasta : null,
            ciudad: [...F.ciudad], sector: [...F.sector], usuario: [...F.usuario], prioridad: [...F.prioridad], oportunidad: [...F.oportunidad],
            score: F.score, ui: { consumoModo: UI.consumoModo, heat: UI.heat, rend: UI.rend } };
    }
    // Clave para saber si los filtros actuales coinciden con una vista guardada (ignora el orden y la forma de los gráficos)
    const claveFiltros = (o) => JSON.stringify([o.preset, o.preset === 'custom' ? o.desde : null, o.preset === 'custom' ? o.hasta : null,
        ...LISTAS.map((k) => [...(o[k] || [])].sort()), o.score || null]);
    function sincronizarSeg() {
        document.querySelectorAll('#viz [data-seg]').forEach((b) => {
            const g = b.dataset.seg, val = g === 'consumo' ? UI.consumoModo : g === 'heat' ? UI.heat : UI.rend, on = b.dataset.v === val;
            b.classList.toggle('activo', on); b.setAttribute('aria-pressed', on);
        });
    }
    function aplicarVista(o) {
        F = filtroInicial();
        F.preset = o.preset; F.desde = o.desde || null; F.hasta = o.hasta || null;
        LISTAS.forEach((k) => { F[k] = new Set(o[k] || []); });
        F.score = o.score || null;
        if (o.ui) { UI.consumoModo = o.ui.consumoModo || 'mes'; UI.heat = o.ui.heat || 'leads'; UI.rend = o.ui.rend || 'usuario'; }
        sincronizarSeg();
    }
    async function enviar(metodo, url, cuerpo) {
        const r = await fetch(url, { method: metodo, headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' }, body: cuerpo ? JSON.stringify(cuerpo) : undefined });
        if (r.status === 401) { location.href = '/login'; throw new Error('Sesión caducada'); }
        const d = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(d.error || 'No se pudo completar la acción');
        return d;
    }
    async function recargarVistas() { VISTAS = (await pedir('/api/vistas')).vistas; pintarVistas(); }
    function vistaActiva() { const k = claveFiltros(serializar()); return VISTAS.find((v) => claveFiltros(v.filtros) === k) || null; }

    function pintarVistas() {
        const sel = $id('vizVistas'); if (!sel) return;
        const op = (v) => `<option value="${v.id}">${v.predeterminada ? '★ ' : ''}${esc(v.nombre)}${v.propia && v.compartida ? ' (compartida)' : ''}${v.propia ? '' : ' · ' + esc(v.autor)}</option>`;
        const propias = VISTAS.filter((v) => v.propia), ajenas = VISTAS.filter((v) => !v.propia);
        sel.innerHTML = '<option value="">Vistas guardadas…</option>' +
            (propias.length ? `<optgroup label="Mis vistas">${propias.map(op).join('')}</optgroup>` : '') +
            (ajenas.length ? `<optgroup label="Del equipo">${ajenas.map(op).join('')}</optgroup>` : '');
        const activa = vistaActiva();
        sel.value = activa ? String(activa.id) : '';
        const def = $id('vizVistaDef');
        def.hidden = !(activa && activa.propia);
        def.textContent = activa && activa.predeterminada ? '★ Predeterminada' : '☆ Hacer predeterminada';
        def.setAttribute('aria-pressed', String(!!(activa && activa.predeterminada)));
        $id('vizVistaDel').hidden = !(activa && activa.puede_borrar);
    }
    function nombreSugerido() {
        const partes = [...F.ciudad, ...F.sector, ...[...F.prioridad].map((k) => PRIO[k].txt), ...[...F.oportunidad].map((o) => OPP[o] || o)];
        return (partes.length ? partes.join(' · ') : rangoTxt()).slice(0, 60);
    }
    function abrirDialogoVista() {
        const dlg = $id('vizDlgVista');
        $id('vizNombreVista').value = nombreSugerido(); $id('vizCompartir').checked = false;
        $id('vizResumenVista').textContent = 'Se guardará: ' + [rangoTxt(), ...listaChips().map((c) => c.t)].join(' · ');
        $id('vizDlgErr').classList.remove('active');
        dlg.showModal(); $id('vizNombreVista').select();
    }
    function crearDialogoVista() {
        const dlg = document.createElement('dialog');
        dlg.id = 'vizDlgVista'; dlg.setAttribute('aria-labelledby', 'vizDlgTit');
        dlg.innerHTML = `<div class="dlg-cab"><h2 id="vizDlgTit">Guardar vista</h2>
            <button type="button" class="btn-icono" id="vizDlgX" aria-label="Cerrar"><svg class="icono" aria-hidden="true"><use href="#i-x"/></svg></button></div>
            <div class="dlg-cuerpo"><div class="aviso error" id="vizDlgErr" role="alert"></div>
            <form id="vizFormVista" autocomplete="off">
                <div class="form-group"><label for="vizNombreVista">Nombre de la vista</label>
                    <input type="text" id="vizNombreVista" maxlength="60" required></div>
                <p class="ayuda" id="vizResumenVista" style="margin-bottom:12px"></p>
                <label class="check"><input type="checkbox" id="vizCompartir"> Compartir con el equipo (podrán verla y aplicarla, no modificarla)</label>
                <div class="dlg-acciones"><button type="button" class="btn btn-clear" id="vizDlgCancel">Cancelar</button>
                    <button type="submit" class="btn btn-primario" id="vizDlgOk"><span>Guardar</span></button></div>
            </form></div>`;
        document.body.appendChild(dlg);
        const cerrar = () => dlg.close();
        dlg.querySelector('#vizDlgX').addEventListener('click', cerrar);
        dlg.querySelector('#vizDlgCancel').addEventListener('click', cerrar);
        dlg.addEventListener('click', (e) => { if (e.target === dlg) cerrar(); });
        dlg.querySelector('#vizFormVista').addEventListener('submit', async (ev) => {
            ev.preventDefault();
            const ok = $id('vizDlgOk'); ok.disabled = true;
            try {
                await enviar('POST', '/api/vistas', { nombre: $id('vizNombreVista').value, filtros: serializar(), compartida: $id('vizCompartir').checked });
                dlg.close(); await recargarVistas();
            } catch (e) { const er = $id('vizDlgErr'); er.textContent = e.message; er.classList.add('active'); }
            finally { ok.disabled = false; }
        });
    }

    function pintarFiltros() {
        const rg = rango();
        $id('vizPresets').innerHTML = PRESETS.map(([k, t]) => `<button type="button" class="viz-btn${F.preset === k ? ' activo' : ''}" data-preset="${k}" aria-pressed="${F.preset === k}">${t}</button>`).join('');
        $id('vizDesde').value = rg.desde; $id('vizHasta').value = rg.hasta;
        const opciones = {
            ciudad: [...new Set(DATA.leads.map((l) => l.ciudad))].sort(), sector: [...new Set(DATA.leads.map((l) => l.sector))].sort(),
            usuario: Object.entries(DATA.usuarios).sort((a, b) => a[1].localeCompare(b[1])).map(([id, n]) => [id, n]),
            prioridad: ['alta', 'media', 'baja'].map((k) => [k, PRIO[k].txt]), oportunidad: Object.entries(OPP),
        };
        Object.entries(opciones).forEach(([dim, lista]) => {
            const sel = $id('vizSel-' + dim), titulo = sel.dataset.titulo;
            sel.innerHTML = `<option value="">${esc(titulo)}…</option>` + lista.map((o) => Array.isArray(o) ? `<option value="${esc(o[0])}">${esc(o[1])}</option>` : `<option value="${esc(o)}">${esc(o)}</option>`).join('');
        });
        const chips = listaChips();
        const cont = $id('vizChips'); cont.textContent = '';
        chips.forEach((c) => {
            const s = document.createElement('span'); s.className = 'vchip'; s.append(c.t + ' ');
            const b = document.createElement('button'); b.type = 'button'; b.textContent = '×'; b.setAttribute('aria-label', 'Quitar filtro ' + c.t);
            b.addEventListener('click', () => { c.quitar(); render(); }); s.appendChild(b); cont.appendChild(s);
        });
        $id('vizReset').hidden = !chips.length && F.preset === '6m';
        pintarVistas();
    }

    // ------------------------------------------------------------------ construcción y render
    function tarjeta(id, span, titulo, sub, acciones, cuerpo) {
        return `<article class="viz-card span-${span}" id="card-${id}"><div class="viz-card-cab"><div><h3>${titulo}</h3><div class="sub">${sub}</div></div>
            <div class="viz-acciones">${acciones || ''}<button type="button" class="viz-btn" data-tabla="${id}" aria-pressed="false" title="Ver los datos del gráfico en una tabla">Tabla</button></div></div>
            <div class="viz-body">${cuerpo}</div><div class="viz-tabla" id="tb-${id}"></div></article>`;
    }
    const seg = (grupo, opts, activo) => `<div class="viz-seg" role="group">${opts.map(([k, t]) => `<button type="button" class="viz-btn${activo === k ? ' activo' : ''}" data-seg="${grupo}" data-v="${k}" aria-pressed="${activo === k}">${t}</button>`).join('')}</div>`;

    function construir() {
        const sel = (dim, titulo) => `<select id="vizSel-${dim}" data-titulo="${titulo}" aria-label="Filtrar por ${titulo.toLowerCase()}"></select>`;
        $id('analiticaCont').innerHTML = `<div class="viz-root" id="viz">
            <section class="viz-hero" id="vizHero" aria-label="Consumo del mes"></section>
            <div class="viz-filtros" id="vizFiltros">
                <span class="grupo vistas"><select id="vizVistas" aria-label="Vistas guardadas"></select>
                    <button type="button" class="viz-btn" id="vizGuardarVista" title="Guardar los filtros actuales con un nombre">Guardar vista</button>
                    <button type="button" class="viz-btn" id="vizVistaDef" hidden aria-pressed="false" title="El panel se abrirá con esta vista"></button>
                    <button type="button" class="viz-btn" id="vizVistaDel" hidden>Eliminar</button></span>
                <div class="viz-seg" id="vizPresets" role="group" aria-label="Rango de fechas"></div>
                <span class="grupo"><label class="mini" for="vizDesde">Desde</label><input type="date" id="vizDesde"><label class="mini" for="vizHasta">Hasta</label><input type="date" id="vizHasta"></span>
                <span class="grupo">${sel('ciudad', 'Ciudad')}${sel('sector', 'Sector')}${sel('usuario', 'Usuario')}${sel('prioridad', 'Prioridad')}${sel('oportunidad', 'Oportunidad')}</span>
                <button type="button" class="viz-btn" id="vizReset" hidden>Restablecer filtros</button>
                <a class="viz-btn" href="/api/consumo.csv" style="text-decoration:none;margin-left:auto">Descargar consumo (CSV)</a>
            </div>
            <div class="viz-chips" id="vizChips" aria-live="polite"></div>
            <div class="viz-kpis" id="vizKpis"></div>
            <div class="viz-grid">
                ${tarjeta('consumo', 12, 'Consumo de créditos de SerpAPI', 'Clic en una barra para filtrar ese mes · la línea es la cuota mensual', seg('consumo', [['mes', 'Mensual'], ['dia', 'Diario']], UI.consumoModo),
                    '<div class="chart" id="ch-consumo" style="height:300px"></div><div class="hero-datos" id="vizEficiencia" style="margin-top:12px"></div>')}
                ${tarjeta('actividad', 7, 'Actividad semanal', 'Arrastra sobre el gráfico para filtrar por fechas · franja azul = rango activo', '', '<div class="chart" id="ch-actividad" style="height:300px"></div>')}
                ${tarjeta('embudo', 5, 'Embudo comercial', 'Del lead al cierre, con la conversión entre pasos', '', '<div id="ch-embudo" style="min-height:260px"></div>')}
                ${tarjeta('score', 5, 'Calidad de los leads', 'Clic en un bloque o una barra para filtrar', '', '<div id="ch-prio"></div><div class="chart" id="ch-score" style="height:200px"></div>')}
                ${tarjeta('opps', 7, 'Oportunidades detectadas', 'Un lead puede tener varias · clic para filtrar', '', '<div class="chart" id="ch-opps" style="height:290px"></div>')}
                ${tarjeta('calor', 7, 'Ciudad × sector', 'Dónde se concentran los resultados · clic en una celda para filtrar',
                    seg('heat', [['leads', 'Leads'], ['tasa', 'Tasa de respuesta'], ['creditos', 'Créditos']], UI.heat), '<div class="chart" id="ch-calor" style="height:340px"></div>')}
                ${tarjeta('rend', 5, 'Rendimiento', 'Contactados y respondieron', seg('rend', [['usuario', 'Usuario'], ['canal', 'Canal'], ['sector', 'Sector']], UI.rend), '<div class="chart" id="ch-rend" style="height:340px"></div>')}
                ${tarjeta('plantillas', 12, 'Plantillas de mensaje (prueba A/B)', 'Qué ángulo, canal y variante responde mejor', '', '<div id="ch-plantillas"></div>')}
                ${tarjeta('top', 6, 'Mejores oportunidades sin contactar', 'Clic para abrir el lead y contactarlo', '', '<div id="ch-top"></div>')}
                ${tarjeta('venc', 6, 'Seguimientos vencidos', 'Contactados o con respuesta que esperan un nuevo toque',
                    '<button type="button" class="viz-btn" id="vizVerSeg">Ver en Mis leads</button>', '<div id="ch-venc"></div>')}
            </div></div>`;
        const raiz = $id('viz');
        raiz.addEventListener('click', (e) => {
            const p = e.target.closest('[data-preset]'); if (p) { F.preset = p.dataset.preset; F.desde = F.hasta = null; render(); return; }
            const t = e.target.closest('[data-tabla]');
            if (t) { const id = t.dataset.tabla, on = !UI.tabla[id]; UI.tabla[id] = on; $id('card-' + id).classList.toggle('ver-tabla', on); t.setAttribute('aria-pressed', on); t.classList.toggle('activo', on);
                if (on) pintarTabla(id); else setTimeout(() => Object.values(charts).forEach((c) => c.resize()), 0); return; }
            const s = e.target.closest('[data-seg]');
            if (s) { const g = s.dataset.seg; if (g === 'consumo') UI.consumoModo = s.dataset.v; else if (g === 'heat') UI.heat = s.dataset.v; else UI.rend = s.dataset.v;
                s.parentElement.querySelectorAll('.viz-btn').forEach((b) => { const on = b === s; b.classList.toggle('activo', on); b.setAttribute('aria-pressed', on); });
                ({ consumo: pintarConsumo, heat: pintarCalor, rend: pintarRend })[g](); return; }
            if (e.target.id === 'vizReset') { F = filtroInicial(); render(); return; }
            if (e.target.id === 'vizGuardarVista') { abrirDialogoVista(); return; }
            if (e.target.id === 'vizVistaDef') {
                const v = vistaActiva(); if (!v) return;
                enviar('PATCH', '/api/vistas/' + v.id, { predeterminada: !v.predeterminada }).then(recargarVistas).catch((er) => alert(er.message)); return;
            }
            if (e.target.id === 'vizVistaDel') {
                const v = vistaActiva();
                if (v && confirm(`¿Eliminar la vista "${v.nombre}"?`)) enviar('DELETE', '/api/vistas/' + v.id).then(recargarVistas).catch((er) => alert(er.message));
                return;
            }
            if (e.target.id === 'vizVerSeg') { const c = document.getElementById('fSeg'); if (c) c.checked = true; if (window.irA) window.irA('leads'); }
        });
        raiz.addEventListener('change', (e) => {
            const id = e.target.id;
            if (id === 'vizDesde' || id === 'vizHasta') { F.preset = 'custom'; F.desde = $id('vizDesde').value || null; F.hasta = $id('vizHasta').value || null; render(); return; }
            if (id === 'vizVistas') { const v = VISTAS.find((x) => String(x.id) === e.target.value); if (v) { aplicarVista(v.filtros); render(); } return; }
            const m = /^vizSel-(.+)$/.exec(id);
            if (m && e.target.value) { F[m[1]].add(e.target.value); render(); }
        });
        if (window.ResizeObserver) new ResizeObserver(() => Object.values(charts).forEach((c) => { if (!c.isDisposed()) c.resize(); })).observe(raiz);
        crearDialogoVista();
        construido = true;
    }

    function render() {
        if (!DATA) return;
        S = calcular();
        const vacio = !DATA.leads.length && !DATA.consumo.length;
        $id('viz').classList.toggle('sin-datos', vacio);
        [pintarHero, pintarFiltros, pintarKpis, pintarConsumo, pintarActividad, pintarEmbudo, pintarCalidad, pintarOpps, pintarCalor, pintarRend, pintarPlantillas, pintarPendientes]
            .forEach((fn) => { try { fn(); } catch (err) { console.error('Panel:', fn.name, err); } });
    }

    async function pedir(url) {
        const r = await fetch(url);
        if (r.status === 401) { location.href = '/login'; throw new Error('Sesión caducada'); }
        if (!r.ok) throw new Error('No se pudieron cargar los datos del panel');
        return r.json();
    }

    async function cargar() {
        const cont = $id('analiticaCont'), err = $id('errorAnalitica');
        if (err) err.classList.remove('active');
        if (!construido && !DATA) cont.innerHTML = '<div class="vacio-viz">Cargando el panel…</div>';
        try {
            const [datos, cuenta, vistas] = await Promise.all([pedir('/api/analitica/datos'), pedir('/api/serpapi/cuenta').catch(() => null),
                pedir('/api/vistas').catch(() => ({ vistas: [] }))]);
            datos.leads.forEach((l) => { l.f = fechaLocal(l.creado); });
            datos.eventos.forEach((e) => { e.f = fechaLocal(e.fecha); });
            datos.consumo.forEach((c) => { c.f = fechaLocal(c.fecha); });
            DATA = datos; CUENTA = cuenta; VISTAS = vistas.vistas || [];
            if (!F) F = filtroInicial();
            if (!construido) construir();
            if (!aplicadaDefault) {  // la primera vez, el panel se abre con la vista predeterminada del usuario
                aplicadaDefault = true;
                const d = VISTAS.find((v) => v.propia && v.predeterminada);
                if (d) aplicarVista(d.filtros);
            }
            const raiz = $id('viz'); raiz.classList.add('cargando');
            render();
            requestAnimationFrame(() => { raiz.classList.remove('cargando'); Object.values(charts).forEach((c) => { if (!c.isDisposed()) c.resize(); }); });
        } catch (e) {
            if (err) { err.textContent = e.message; err.classList.add('active'); }
            else cont.textContent = e.message;
        }
    }

    window.Analitica = { cargar, _estado: () => ({ F, DATA, S }) };
})();
