/* Sección «Ajustes» (solo administradores): claves y configuración gestionadas desde la app.
 * El servidor nunca devuelve una clave: aquí solo se ve si está configurada y de dónde viene.
 * Todo texto del servidor entra en el DOM con textContent / propiedades (nunca innerHTML). */
(function () {
    'use strict';

    const $id = (id) => document.getElementById(id);
    let ESTADO = null, pestana = 'usuarios';

    // Constructor mínimo de elementos: h('div', {class: 'x', text: 'hola'}, hijo1, hijo2)
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
        const r = await fetch(url, { method: metodo, headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
            body: cuerpo ? JSON.stringify(cuerpo) : undefined });
        if (r.status === 401) { location.href = '/login'; throw new Error('Sesión caducada'); }
        const d = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(d.error || 'No se pudo completar la acción');
        return d;
    }

    const fechaCorta = (iso) => (iso ? new Date(iso + 'Z').toLocaleString('es', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '');
    const ORIGEN = { app: ['Guardada en la app', 'badge-exito'], entorno: ['Desde Render (entorno)', 'badge-azul'] };

    function mensaje(caja, tipo, texto) {
        caja.className = 'aviso ' + (tipo === 'ok' ? 'exito' : 'error') + ' active';
        caja.textContent = texto;
    }

    // ---------------------------------------------------------------- una tarjeta por grupo
    function tarjeta(g) {
        const inputs = {};
        const aviso = h('div', { class: 'aviso', role: 'status' });
        const cuerpo = [];
        let subActual = null;
        if (!ESTADO.cifrado_disponible && g.campos.some((c) => c.tipo === 'secreto')) {
            cuerpo.push(h('div', { class: 'aviso warning active' },
                'Para guardar claves hace falta una SECRET_KEY estable (mínimo 16 caracteres) en el entorno: con ella se cifran. En Render se genera sola con render.yaml; en local, defínela en .env.'));
        }
        g.campos.forEach((c) => {
            if (c.sub && c.sub !== subActual) { subActual = c.sub; cuerpo.push(h('h3', { class: 'aj-sub', text: c.sub })); }
            const id = 'aj-' + c.clave;
            const secreto = c.tipo === 'secreto';
            const input = h('input', {
                id, type: secreto ? 'password' : (c.tipo === 'numero' ? 'number' : 'text'), autocomplete: secreto ? 'new-password' : 'off',
                autocapitalize: 'none', spellcheck: 'false',
                placeholder: secreto ? (c.origen ? '•••••••• (escribe para reemplazarla)' : 'Pega aquí la clave') : (c.placeholder || (c.defecto ? 'Por defecto: ' + c.defecto : '')),
                disabled: secreto && !ESTADO.cifrado_disponible,
            });
            if (!secreto) { input.value = c.valor || ''; input.dataset.inicial = c.valor || ''; }
            inputs[c.clave] = input;

            const etiquetas = [h('span', { text: c.etiqueta })];
            if (c.ilegible) etiquetas.push(h('span', { class: 'badge badge-aviso', text: 'No se pudo descifrar: vuelve a introducirla' }));
            else if (c.origen) etiquetas.push(h('span', { class: 'badge ' + ORIGEN[c.origen][1], text: ORIGEN[c.origen][0] }));
            else etiquetas.push(h('span', { class: 'badge badge-neutro', text: c.defecto ? 'Por defecto: ' + c.defecto : 'Sin configurar' }));

            const extras = [];
            if (secreto && c.origen === 'entorno' && ESTADO.cifrado_disponible) {
                extras.push(h('button', { type: 'button', class: 'btn btn-clear btn-sm', text: 'Guardar en la app la que ya está en Render',
                    onclick: () => accion(g, aviso, { importar: [c.clave] }, 'Clave guardada (cifrada) en la app. Ya puedes quitarla de Render si quieres.') }));
            }
            if (secreto && c.origen === 'app') {
                extras.push(h('button', { type: 'button', class: 'btn btn-clear btn-sm', text: 'Quitar la guardada',
                    onclick: () => { if (confirm(`¿Quitar «${c.etiqueta}» de la app? Si hay una en Render, se usará esa.`)) accion(g, aviso, { borrar: [c.clave] }, 'Clave quitada de la app.'); } }));
            }
            const meta = c.actualizado_por ? ` Última vez: ${c.actualizado_por}, ${fechaCorta(c.actualizado_en)}.` : '';
            cuerpo.push(h('div', { class: 'form-group aj-campo' },
                h('label', { for: id }, etiquetas), input,
                (c.ayuda || meta) ? h('p', { class: 'ayuda', text: (c.ayuda + meta).trim() }) : null,
                extras.length ? h('div', { class: 'aj-extra' }, extras) : null));
        });

        const guardar = h('button', { type: 'button', class: 'btn btn-primario', text: 'Guardar cambios' });
        guardar.addEventListener('click', async () => {
            const valores = {};
            g.campos.forEach((c) => {
                const v = inputs[c.clave].value;
                if (c.tipo === 'secreto') { if (v.trim() !== '') valores[c.clave] = v; }
                else if (v !== inputs[c.clave].dataset.inicial) valores[c.clave] = v;
            });
            if (!Object.keys(valores).length) { mensaje(aviso, 'error', 'No hay cambios que guardar.'); return; }
            await accion(g, aviso, { valores }, 'Cambios guardados.', guardar);
        });
        const botones = [guardar];
        if (g.id === 'serpapi') botones.push(h('button', { type: 'button', class: 'btn btn-clear', text: 'Probar clave',
            onclick: (e) => probar(e.currentTarget, aviso, 'POST', '/api/ajustes/probar/serpapi',
                (d) => `Conexión correcta: plan ${d.plan || '—'}, ${d.usadas ?? '—'} de ${d.cuota ?? '—'} búsquedas usadas este mes (quedan ${d.restantes ?? '—'}).`) }));
        if (g.id === 'correo') botones.push(h('button', { type: 'button', class: 'btn btn-clear', text: 'Enviar correo de prueba',
            onclick: (e) => probar(e.currentTarget, aviso, 'POST', '/api/alertas/prueba', (d) => `Correo de prueba enviado a ${(d.destinos || []).join(', ')}. Revisa la bandeja.`) }));
        return h('div', { class: 'card aj-card' },
            h('h2', { class: 'card-titulo', text: g.titulo }), h('p', { class: 'ayuda', style: 'margin-bottom:16px', text: g.ayuda }),
            cuerpo, h('div', { class: 'aj-acciones' }, botones),
            g.id === 'correo' ? h('p', { class: 'ayuda', style: 'margin-top:10px', text: 'Guarda los cambios antes de enviar la prueba: se usa lo guardado.' }) : null,
            h('div', { style: 'margin-top:12px' }, aviso));
    }

    async function accion(g, aviso, cuerpo, okTexto, boton) {
        if (boton) boton.disabled = true;
        try {
            const d = await llamar('PUT', '/api/ajustes', cuerpo);
            ESTADO = d;
            pintar();
            const caja = document.querySelector(`#aj-${g.id} .aviso:last-child`) || null;
            if (caja) mensaje(caja, 'ok', okTexto);
            if (window.refrescarCorreo) window.refrescarCorreo();
        } catch (e) { mensaje(aviso, 'error', e.message); }
        finally { if (boton) boton.disabled = false; }
    }

    async function probar(boton, aviso, metodo, url, textoOk) {
        boton.disabled = true;
        try { mensaje(aviso, 'ok', textoOk(await llamar(metodo, url))); }
        catch (e) { mensaje(aviso, 'error', e.message); }
        finally { boton.disabled = false; }
    }

    // ---------------------------------------------------------------- pestañas
    function pintar() {
        ESTADO.grupos.forEach((g) => {
            const cont = $id('aj-' + g.id);
            if (!cont) return;
            cont.textContent = '';
            cont.appendChild(tarjeta(g));
        });
        mostrar(pestana);
    }
    function mostrar(id) {
        pestana = id;
        document.querySelectorAll('.aj-tab').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.aj === id)));
        document.querySelectorAll('.aj-panel').forEach((p) => { p.hidden = p.id !== 'aj-' + id; });
    }

    async function cargar() {
        const err = $id('errorAjustes');
        try {
            ESTADO = await llamar('GET', '/api/ajustes');
            if (err) err.classList.remove('active');
            pintar();
        } catch (e) { if (err) mensaje(err, 'error', e.message); }
    }

    document.addEventListener('click', (e) => {
        const t = e.target.closest('.aj-tab');
        if (t) mostrar(t.dataset.aj);
    });

    window.Ajustes = { cargar };
})();
