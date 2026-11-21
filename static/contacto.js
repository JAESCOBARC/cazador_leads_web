/* Módulo «Contacto» (solo administradores): los textos de los mensajes y la imagen de firma.
 * Todo texto que viene del servidor entra en el DOM con textContent (nunca innerHTML). */
(function () {
    'use strict';

    const $id = (id) => document.getElementById(id);
    let E = null;                                   // estado completo que devuelve /api/contacto
    let pestana = 'mensajes';
    const sel = { ang: 'sin_web', paso: 0, variante: 'a', canal: 'email' };
    let temporizador = null, ultimoCampo = null, sinGuardar = false;

    function h(tag, props, ...hijos) {
        const e = document.createElement(tag);
        Object.entries(props || {}).forEach(([k, v]) => {
            if (v == null || v === false) return;
            if (k === 'class') e.className = v;
            else if (k === 'text') e.textContent = v;
            else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
            else if (v === true) e.setAttribute(k, '');
            else e.setAttribute(k, v);
        });
        hijos.flat().forEach((c) => { if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c)); });
        return e;
    }

    async function llamar(metodo, url, cuerpo) {
        const opts = { method: metodo, headers: { 'X-Requested-With': 'fetch' } };
        if (cuerpo instanceof FormData) opts.body = cuerpo;
        else if (cuerpo) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(cuerpo); }
        const r = await fetch(url, opts);
        if (r.status === 401) { location.href = '/login'; throw new Error('Sesión caducada'); }
        const d = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(d.error || 'No se pudo completar la acción');
        return d;
    }

    function aviso(caja, tipo, texto) {
        caja.className = 'aviso ' + (tipo === 'ok' ? 'exito' : tipo === 'aviso' ? 'warning' : 'error') + ' active';
        caja.textContent = texto;
    }

    const clave = () => `${sel.ang}:${sel.paso}:${sel.variante}`;
    const pers = (k) => E.plantillas[k] && E.plantillas[k].personalizada;

    function confirmarCambio() {
        return !sinGuardar || confirm('Tienes cambios sin guardar en este texto. ¿Descartarlos?');
    }

    // ---------------------------------------------------------------- vista previa (sin guardar)
    function programarVista(k, campoAsunto, campoCuerpo, caja, meta, canal) {
        clearTimeout(temporizador);
        temporizador = setTimeout(async () => {
            try {
                const d = await llamar('POST', '/api/contacto/vista-previa', { clave: k, asunto: campoAsunto ? campoAsunto.value : null, cuerpo: campoCuerpo.value, canal });
                caja.textContent = '';
                if (d.asunto) caja.append(h('div', { class: 'ct-prev-asunto' }, h('span', { text: 'Asunto: ' }), h('strong', { text: d.asunto })));
                caja.append(h('div', { class: 'ct-prev-cuerpo', text: d.cuerpo }));
                const largo = d.palabras > d.max_palabras;
                meta.className = 'ayuda' + (largo ? ' ct-largo' : '');
                meta.textContent = `${d.palabras} palabras en el mensaje completo` + (largo ? ` · pasa de ${d.max_palabras}: la regla del proyecto es no superarlas` : ` (máximo ${d.max_palabras})`);
            } catch (e) {
                caja.textContent = '';
                caja.append(h('div', { class: 'ct-prev-error', text: e.message }));
                meta.textContent = '';
            }
        }, 350);
    }

    function insertar(texto) {
        const c = ultimoCampo;
        if (!c) return;
        const a = c.selectionStart ?? c.value.length, b = c.selectionEnd ?? a;
        c.value = c.value.slice(0, a) + texto + c.value.slice(b);
        c.focus();
        c.selectionStart = c.selectionEnd = a + texto.length;
        c.dispatchEvent(new Event('input', { bubbles: true }));
    }

    // ---------------------------------------------------------------- editor de un texto (mensaje o pieza general)
    function editor({ k, conAsunto, canal, titulo, ayuda, filas }) {
        const p = E.plantillas[k];
        const msg = h('div', { class: 'aviso', role: 'status' });
        const asunto = conAsunto ? h('input', { type: 'text', id: 'ct-asunto', value: p.asunto || '', maxlength: '200', autocomplete: 'off' }) : null;
        const cuerpo = h('textarea', { id: 'ct-cuerpo', rows: String(filas || 14), spellcheck: 'true', maxlength: '3000' });
        cuerpo.value = p.cuerpo;
        const caja = h('div', { class: 'ct-prev ' + (canal === 'whatsapp' ? 'ct-wa' : 'ct-mail') });
        const meta = h('p', { class: 'ayuda' });
        const marca = (el) => el.addEventListener('focus', () => { ultimoCampo = el; });
        marca(cuerpo); if (asunto) marca(asunto);
        ultimoCampo = cuerpo;
        const cambio = () => { sinGuardar = true; programarVista(k, asunto, cuerpo, caja, meta, canal); };
        cuerpo.addEventListener('input', cambio); if (asunto) asunto.addEventListener('input', cambio);

        const vars = E.variables.filter((v) => !(v.nombre === 'asunto_inicial' && (!conAsunto || sel.paso === 0)));
        const chips = h('div', { class: 'ct-vars' }, vars.map((v) => h('button', {
            type: 'button', class: 'ct-var', title: `${v.explicacion}\nEjemplo: ${v.ejemplo.trim()}`, text: '{' + v.nombre + '}',
            onclick: () => insertar('{' + v.nombre + '}') })));

        const guardar = h('button', { type: 'button', class: 'btn btn-primario', text: 'Guardar texto' });
        guardar.addEventListener('click', async () => {
            guardar.disabled = true;
            try {
                E = await llamar('PUT', '/api/contacto/plantillas/' + k, { asunto: asunto ? asunto.value : null, cuerpo: cuerpo.value });
                sinGuardar = false; pintar();
                const caja2 = $id('ct-aviso'); if (caja2) aviso(caja2, 'ok', 'Guardado. Los mensajes nuevos que generes ya usan este texto.');
            } catch (e) { aviso(msg, 'error', e.message); } finally { guardar.disabled = false; }
        });
        const restaurar = h('button', { type: 'button', class: 'btn btn-clear', text: 'Restaurar el original', disabled: !p.personalizada });
        restaurar.addEventListener('click', async () => {
            if (!confirm('Se descartará tu versión y volverá el texto original. ¿Seguro?')) return;
            try {
                E = await llamar('DELETE', '/api/contacto/plantillas/' + k);
                sinGuardar = false; pintar();
                const caja2 = $id('ct-aviso'); if (caja2) aviso(caja2, 'ok', 'Vuelve el texto original.');
            } catch (e) { aviso(msg, 'error', e.message); }
        });

        const tarjeta = h('div', { class: 'ct-grid' },
            h('div', { class: 'card' },
                h('h2', { class: 'card-titulo', text: titulo }),
                ayuda ? h('p', { class: 'ayuda', style: 'margin-bottom:12px', text: ayuda }) : null,
                asunto ? h('div', { class: 'form-group' }, h('label', { for: 'ct-asunto', text: 'Asunto (solo email)' }), asunto) : null,
                h('div', { class: 'form-group' }, h('label', { for: 'ct-cuerpo', text: conAsunto ? 'Mensaje (sin saludo ni firma: se añaden solos)' : 'Texto' }), cuerpo),
                h('p', { class: 'ayuda', style: 'margin:0 0 6px', text: 'Pulsa una variable para insertarla donde tienes el cursor. Se sustituye por datos reales de cada negocio; pasa el ratón para ver qué es.' }),
                chips,
                h('div', { class: 'aj-acciones' }, guardar, restaurar),
                h('div', { style: 'margin-top:12px' }, msg),
                p.personalizada ? h('p', { class: 'ayuda', style: 'margin-top:8px', text: 'Este texto está personalizado.' }) : h('p', { class: 'ayuda', style: 'margin-top:8px', text: 'Este texto es el original.' })),
            h('div', { class: 'card' },
                h('h2', { class: 'card-titulo', text: 'Vista previa' }),
                h('p', { class: 'ayuda', style: 'margin-bottom:10px', text: 'Con un negocio de ejemplo (Clínica Dental Sol) y tus datos de Ajustes. Se actualiza mientras escribes; no se guarda hasta que pulses «Guardar texto».' }),
                caja, meta));
        sinGuardar = false;
        programarVista(k, asunto, cuerpo, caja, meta, canal);
        return tarjeta;
    }

    // ---------------------------------------------------------------- pestaña: mensajes
    function pestanaMensajes() {
        const total = Object.keys(E.plantillas).filter((k) => !k.startsWith('global:'));
        const hechas = total.filter(pers).length;
        const ang = E.angulos.find((a) => a.id === sel.ang);
        const boton = (texto, activo, marcado, fn, extra) => h('button', {
            type: 'button', class: 'ct-chip' + (extra ? ' ' + extra : ''), 'aria-pressed': String(activo), onclick: () => { if (confirmarCambio()) { fn(); pintar(); } } },
            texto, marcado ? h('span', { class: 'ct-punto', title: 'Personalizado', text: '●' }) : null);
        const hay = (f) => total.some((k) => pers(k) && f(k.split(':')));
        return h('div', null,
            h('p', { class: 'ayuda', style: 'margin-bottom:12px', text: `${hechas} de ${total.length} textos personalizados. Hay un texto por cada ángulo, paso y variante (A/B): el sistema reparte A y B para que puedas medir cuál funciona mejor en Analítica.` }),
            h('div', { class: 'card ct-selector' },
                h('div', null, h('span', { class: 'ct-etq', text: 'Ángulo' }),
                    h('div', { class: 'ct-chips' }, E.angulos.map((a) => boton(a.titulo, sel.ang === a.id, hay((p) => p[0] === a.id), () => { sel.ang = a.id; })))),
                h('div', null, h('span', { class: 'ct-etq', text: 'Paso' }),
                    h('div', { class: 'ct-chips' }, E.pasos.map((p) => boton(p.titulo, sel.paso === p.id, hay((x) => x[0] === sel.ang && Number(x[1]) === p.id), () => { sel.paso = p.id; })))),
                h('div', null, h('span', { class: 'ct-etq', text: 'Variante' }),
                    h('div', { class: 'ct-chips' }, ['a', 'b'].map((v) => boton('Variante ' + v.toUpperCase(), sel.variante === v, pers(`${sel.ang}:${sel.paso}:${v}`), () => { sel.variante = v; })))),
                h('div', null, h('span', { class: 'ct-etq', text: 'Ver como' }),
                    h('div', { class: 'ct-chips' }, [['email', 'Email'], ['whatsapp', 'WhatsApp']].map(([c, t]) => boton(t, sel.canal === c, false, () => { sel.canal = c; }))))),
            h('p', { class: 'ayuda', style: 'margin:10px 0', text: `Servicio de este ángulo: ${ang.servicio}. El texto se aplica tanto al email como a WhatsApp; el saludo y la firma de cada canal se editan en «Saludo y firma».` }),
            editor({ k: clave(), conAsunto: true, canal: sel.canal, titulo: `${ang.titulo} · ${E.pasos[sel.paso].titulo} · variante ${sel.variante.toUpperCase()}` }));
    }

    // ---------------------------------------------------------------- pestaña: saludo y firma
    let globalSel = 'global:firma_email';
    function pestanaGlobales() {
        const cana = (k) => (k.endsWith('whatsapp') ? 'whatsapp' : 'email');
        return h('div', null,
            h('p', { class: 'ayuda', style: 'margin-bottom:12px', text: 'Lo que rodea a todos los mensajes: cómo empiezan y cómo se firman. Tu nombre, cargo, agencia y contacto se toman de Ajustes → Remitente y firma.' }),
            h('div', { class: 'card ct-selector' }, h('div', null, h('div', { class: 'ct-chips' }, E.globales.map((g) => h('button', {
                type: 'button', class: 'ct-chip', 'aria-pressed': String(globalSel === g.clave),
                onclick: () => { if (confirmarCambio()) { globalSel = g.clave; pintar(); } } }, g.titulo, pers(g.clave) ? h('span', { class: 'ct-punto', text: '●' }) : null))))),
            h('div', { style: 'height:12px' }),
            editor({ k: globalSel, conAsunto: false, canal: cana(globalSel), titulo: E.globales.find((g) => g.clave === globalSel).titulo, filas: 5 }));
    }

    // ---------------------------------------------------------------- pestaña: imagen de firma
    function pestanaImagen() {
        const im = E.imagen;
        const msg = h('div', { class: 'aviso', role: 'status' });
        const archivo = h('input', { type: 'file', id: 'ct-archivo', accept: 'image/png,image/jpeg,image/gif' });
        const ancho = h('input', { type: 'number', id: 'ct-ancho', min: String(im.ancho_min), max: String(im.ancho_max), step: '10', value: String(im.ancho || 200) });
        const vista = im.existe ? h('div', { class: 'ct-firma-vista' },
            h('p', { class: 'ayuda', text: 'Así se verá debajo de tu firma de texto (al ancho que indiques):' }),
            h('div', { class: 'ct-firma-marco' }, h('img', { src: '/api/contacto/firma-imagen?v=' + encodeURIComponent(im.actualizado_en), alt: 'Imagen de firma', style: `width:${im.ancho}px;max-width:100%;height:auto;display:block` }))) : null;

        const subir = h('button', { type: 'button', class: 'btn btn-primario', text: im.existe ? 'Reemplazar imagen' : 'Subir imagen' });
        subir.addEventListener('click', async () => {
            if (!archivo.files[0]) { aviso(msg, 'error', 'Elige primero un archivo PNG, JPG o GIF.'); return; }
            if (archivo.files[0].size > im.max_kb * 1024) { aviso(msg, 'error', `Pesa ${Math.round(archivo.files[0].size / 1024)} KB; el máximo es ${im.max_kb} KB.`); return; }
            const fd = new FormData(); fd.append('imagen', archivo.files[0]); fd.append('ancho', ancho.value);
            subir.disabled = true;
            try { E = await llamar('POST', '/api/contacto/firma-imagen', fd); pintar(); const c = $id('ct-aviso'); if (c) aviso(c, 'ok', 'Imagen guardada. Saldrá en los correos que envíes a partir de ahora (usa «Enviarme una prueba» para verla).'); }
            catch (e) { aviso(msg, 'error', e.message); } finally { subir.disabled = false; }
        });
        const botones = [subir];
        if (im.existe) {
            botones.push(h('button', { type: 'button', class: 'btn btn-clear', text: 'Guardar solo el ancho', onclick: async () => {
                try { E = await llamar('PATCH', '/api/contacto/firma-imagen', { ancho: ancho.value }); pintar(); const c = $id('ct-aviso'); if (c) aviso(c, 'ok', 'Ancho guardado.'); }
                catch (e) { aviso(msg, 'error', e.message); } } }));
            botones.push(h('button', { type: 'button', class: 'btn btn-clear', text: 'Quitar imagen', onclick: async () => {
                if (!confirm('Los correos saldrán solo con la firma de texto. ¿Quitar la imagen?')) return;
                try { E = await llamar('DELETE', '/api/contacto/firma-imagen'); pintar(); const c = $id('ct-aviso'); if (c) aviso(c, 'ok', 'Imagen quitada.'); }
                catch (e) { aviso(msg, 'error', e.message); } } }));
        }
        return h('div', { class: 'card aj-card', style: 'max-width:720px' },
            h('h2', { class: 'card-titulo', text: 'Imagen de firma' }),
            h('p', { class: 'ayuda', style: 'margin-bottom:14px', text: 'Un logo o una firma gráfica que se añade al final de los emails, debajo de tu firma de texto y encima de la línea de baja. No aparece en WhatsApp.' }),
            vista,
            h('div', { class: 'form-group' }, h('label', { for: 'ct-archivo', text: 'Archivo (PNG, JPG o GIF, hasta ' + im.max_kb + ' KB)' }), archivo),
            h('div', { class: 'form-group' }, h('label', { for: 'ct-ancho', text: `Ancho en el correo, en píxeles (${im.ancho_min}–${im.ancho_max})` }), ancho,
                h('p', { class: 'ayuda', text: 'Sube la imagen al doble del ancho que vayas a mostrar (p. ej. 400 px de ancho para mostrarla a 200) para que se vea nítida en pantallas de alta resolución.' })),
            h('div', { class: 'aj-acciones' }, botones),
            h('div', { style: 'margin-top:12px' }, msg),
            h('ul', { class: 'ct-notas' },
                h('li', { text: 'Cuando hay imagen, el correo sale en formato HTML con la imagen incrustada, y siempre lleva también la versión de texto.' }),
                h('li', { text: 'Algunos clientes de correo no muestran imágenes hasta que el destinatario lo permite: por eso tu firma de texto se mantiene siempre.' }),
                h('li', { text: 'Un correo con imagen es algo más propenso a caer en spam que uno de solo texto. Mide la respuesta en Analítica y, si baja, prueba sin ella.' }),
                h('li', { text: 'No se admiten SVG ni WebP (no funcionan en todos los correos).' })));
    }

    // ---------------------------------------------------------------- estructura general
    function pintar() {
        const raiz = $id('contactoCont');
        if (!raiz || !E) return;
        raiz.textContent = '';
        const tabs = [['mensajes', 'Mensajes'], ['globales', 'Saludo y firma'], ['imagen', 'Imagen de firma']];
        raiz.append(
            h('div', { class: 'ct-tabs', role: 'tablist' }, tabs.map(([id, t]) => h('button', {
                type: 'button', class: 'ct-tab', role: 'tab', 'aria-selected': String(pestana === id),
                onclick: () => { if (pestana !== id && confirmarCambio()) { pestana = id; pintar(); } } }, t))),
            h('div', { class: 'aviso', id: 'ct-aviso', role: 'status' }),
            pestana === 'mensajes' ? pestanaMensajes() : pestana === 'globales' ? pestanaGlobales() : pestanaImagen());
    }

    async function cargar() {
        const err = $id('errorContacto');
        try {
            E = await llamar('GET', '/api/contacto');
            if (err) err.classList.remove('active');
            pintar();
        } catch (e) { if (err) aviso(err, 'error', e.message); }
    }

    window.Contacto = { cargar };
})();
