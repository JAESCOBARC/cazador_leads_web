# Conectar tu correo y tus claves (desde la propia app)

Todo se gestiona en **Ajustes** (menú lateral, solo administradores). No hace falta poner nada en Render, salvo `SECRET_KEY` (ver más abajo).

| Pestaña | Qué configuras |
|---|---|
| **Usuarios** | Cuentas del equipo (lo de siempre) |
| **Motor de búsqueda** | La clave de SerpAPI y las búsquedas de tu plan al mes |
| **Correo** | Dónde recibes los avisos, y tu Gmail (SMTP) o Resend (API) para enviar |
| **Remitente y firma** | Tu nombre, cargo, agencia y contacto (van en los mensajes) |

## Seguridad: cómo se guardan las claves

- Las claves (SerpAPI, contraseña SMTP, API de Resend) se guardan **cifradas** en la base de datos con una clave derivada de `SECRET_KEY`.
- **Nunca se vuelven a mostrar**: ni en pantalla ni en la API. La interfaz solo dice si están configuradas y de dónde vienen. Para cambiar una, escribes la nueva; para quitarla, «Quitar la guardada».
- Solo los **administradores** ven o cambian los ajustes. Cada cambio queda con su autor y fecha (nunca con el valor).
- **Necesitas una `SECRET_KEY` estable** (mínimo 16 caracteres). En Render ya se genera sola con `render.yaml` y no cambia entre despliegues. En local, defínela en `.env`. **Si la cambias, las claves guardadas quedan ilegibles** y habrá que volver a introducirlas (la app te lo avisa).
- Los mensajes de error nunca incluyen claves ni contraseñas.

## Prioridad: la app manda, Render es el respaldo

Si un ajuste está guardado en la app, se usa ese. Si no, se usa la variable de entorno de Render (si existe), y si no, el valor por defecto. Por eso nada se rompe mientras migras:

1. Entra en **Ajustes → Motor de búsqueda**. Si tu clave de SerpAPI sigue en Render verás «Desde Render (entorno)».
2. Pulsa **«Guardar en la app la que ya está en Render»**: la copia cifrada, sin pasar por tu navegador.
3. Pulsa **«Probar clave»**: consulta tu cuenta de SerpAPI (no gasta créditos).
4. Ya puedes borrar `SERPAPI_KEY` de Render. Si lo haces, no se pierde nada.

## Conectar tu correo

### Opción A — Tu Gmail por SMTP
1. Activa la **verificación en dos pasos** en tu cuenta de Google.
2. Crea una **contraseña de aplicación**: <https://myaccount.google.com/apppasswords> (16 letras, distinta de tu contraseña normal, revocable).
3. En **Ajustes → Correo**: servidor `smtp.gmail.com`, puerto `587`, tu correo como usuario y la contraseña de aplicación. Pon también el email que recibirá los avisos.
4. **Guardar cambios** y luego **Enviar correo de prueba**.

> **Ojo con Render:** según el anuncio de Render de 2025, los servicios del plan gratis no pueden salir por los puertos SMTP (25, 465 y 587). Verifícalo en su documentación. En ese caso usa la opción B o un plan de pago.

### Opción B — API de Resend (funciona en Render gratis)
1. Crea una cuenta en <https://resend.com> y genera una **API key**.
2. En **Ajustes → Correo**, pégala en «API key de Resend» y pon el email de tu cuenta de Resend como destino de los avisos.
3. Para los **avisos** basta con eso (con el remitente de pruebas Resend solo permite enviar a tu propio email).
4. Para **escribir a clientes** hace falta **verificar un dominio tuyo** en Resend y poner en «Remitente que ve el cliente» algo como `Tu Nombre <hola@tudominio.com>`.

Si defines las dos, **Resend tiene prioridad**.

## Avisos de cuota

Un correo cuando el consumo mensual de SerpAPI llega al porcentaje que fijes (80 % por defecto; puedes poner varios, p. ej. `80, 100`). Una vez por mes y umbral. En **Analítica**, debajo del medidor, ves si está activo y, como administrador, puedes enviar un correo de prueba.

## Propuestas a clientes

Botón **Enviar por email** en cada lead con email publicado. Siempre manual:

- **Enviarme una prueba**: antes de escribir al cliente, el botón manda el mismo mensaje (con tu firma y la línea de baja) a **tu propio correo** —el de los avisos en Ajustes → Correo—, nunca al lead. No cuenta en el tope diario, no queda en el historial y no cambia el estado del lead.
- Un lead a la vez, con **vista previa editable y confirmación**.
- Solo al **email que el propio negocio publicó** (nunca a una dirección escrita a mano).
- **Tope diario** (5 por defecto, ajustable) y **una vez cada 24 h por lead**.
- Firma y **línea para darse de baja** en cada correo. La app **no lee las respuestas**: si alguien dice que no, márcalo tú como *Descartado*.
- No sale si el mensaje aún tiene datos por completar (`[TU NOMBRE]`…): complétalos en **Remitente y firma**.
- Cada intento (enviado o con error) queda en el **historial de correos del lead**, con el mensaje exacto que se envió. El lead pasa a *Contactado* con seguimiento a +3 días.

## Textos de los mensajes y firma con imagen (módulo Contacto)

En el menú **Contacto** (solo administradores) editas cada texto: por ángulo, paso (inicial, seguimiento, cierre) y variante A/B, con vista previa en vivo. El saludo y la firma de email y de WhatsApp están en la pestaña «Saludo y firma». En la pestaña «Imagen de firma» subes un logo o firma gráfica (PNG, JPG o GIF, hasta 300 KB) que se añade al final de los emails.

- Los cambios valen para todo el equipo desde el siguiente mensaje que se genere. «Restaurar el original» vuelve al texto que trae la app.
- Con imagen, el correo sale en HTML con la imagen incrustada y siempre con la versión de texto. Usa «Enviarme una prueba» en un lead para verlo en tu bandeja antes de escribir a un cliente.
- Si usas **Resend**, la imagen va como adjunto incrustado (`content_id`). Compruébalo con la prueba: si tu bandeja no la muestra, quita la imagen y avísame.

### Enlaces de agenda y WhatsApp (pestaña «Enlaces y CTA»)

Escribe el enlace de tu agenda (Calendly, Cal.com…, con https://) y tu WhatsApp (número con indicativo, p. ej. +57 300 123 4567, o tu enlace wa.me). Se añaden donde el texto del mensaje lleve `{cta}`, que ya está en los textos originales. Si no configuras nada, los mensajes salen igual que antes. En los emails con imagen de firma los enlaces son clicables; sin imagen, el correo es de texto y tu lector de correo suele convertirlos en enlaces. Usa «Enviarme una prueba» para verlo.

## Variables de entorno (opcionales)

Siguen funcionando como respaldo: `SERPAPI_KEY`, `SERPAPI_CUOTA_MES`, `SMTP_HOST`, `SMTP_PUERTO`, `SMTP_USUARIO`, `SMTP_CLAVE`, `RESEND_API_KEY`, `EMAIL_REMITENTE`, `EMAIL_RESPONDER_A`, `ALERTA_EMAIL_DESTINO`, `ALERTA_UMBRALES`, `ENVIO_MAX_DIA`, `REMITENTE_NOMBRE`, `REMITENTE_CARGO`, `AGENCIA_NOMBRE`, `REMITENTE_CONTACTO`, `CASO_EXITO`. Imprescindibles en Render: `SECRET_KEY`, `DATABASE_URL`, `ADMIN_USER` y `ADMIN_PASSWORD`.
