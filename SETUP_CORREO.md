# Conectar tu correo a Cazador Leads

El correo se usa para dos cosas:

1. **Avisos de cuota**: te escribe cuando el consumo de búsquedas de SerpAPI llega al 80 % del mes (una vez por mes y umbral).
2. **Propuestas a clientes**: botón «Enviar por email» en cada lead. Siempre manual: un lead a la vez, con vista previa editable, confirmación y registro en el historial.

Las credenciales van **solo en variables de entorno** (`.env` en local, *Environment* en Render). No se guardan en la base de datos, no se muestran en la interfaz y no se comparten con nadie: ni con Claude ni en el chat.

## Opción A — Tu Gmail por SMTP (la más directa)

1. Activa la **verificación en dos pasos** en tu cuenta de Google.
2. Crea una **contraseña de aplicación**: <https://myaccount.google.com/apppasswords>. Es de 16 letras y distinta de tu contraseña normal; se puede revocar cuando quieras.
3. Pon en `.env`:

```
SMTP_HOST=smtp.gmail.com
SMTP_PUERTO=587
SMTP_USUARIO=tu_correo@gmail.com
SMTP_CLAVE=la contraseña de aplicación
ALERTA_EMAIL_DESTINO=tu_correo@gmail.com
```

Sirve para escribir a cualquier cliente. Gmail limita el volumen diario, y con el tope de la app (5 correos/día por defecto) vas muy por debajo.

> **Ojo con Render:** según el anuncio de Render de 2025, los servicios del plan gratis no pueden salir por los puertos SMTP (25, 465 y 587). Verifícalo en su documentación. En ese caso, usa la opción B o un plan de pago.

## Opción B — API de Resend (funciona en Render gratis)

1. Crea una cuenta en <https://resend.com> y genera una **API key**.
2. Pon `RESEND_API_KEY=` (la key) y `ALERTA_EMAIL_DESTINO=` (el email de tu cuenta de Resend).
3. **Para los avisos de cuota** basta con eso: con el remitente de pruebas (`onboarding@resend.dev`, el valor por defecto) Resend solo permite enviar al email de tu propia cuenta.
4. **Para escribir a clientes** necesitas **verificar un dominio tuyo** en Resend y poner `EMAIL_REMITENTE=Tu Nombre <hola@tudominio.com>`. Sin dominio verificado, Resend rechazará esos envíos y la app te mostrará el motivo.

## Variables

| Variable | Para qué |
|---|---|
| `ALERTA_EMAIL_DESTINO` | Quién recibe los avisos (uno o varios, separados por coma) |
| `ALERTA_UMBRALES` | Porcentajes de aviso. Por defecto `80`. Ejemplo: `80,100` |
| `SMTP_HOST`, `SMTP_PUERTO`, `SMTP_USUARIO`, `SMTP_CLAVE` | Opción A |
| `RESEND_API_KEY` | Opción B (tiene prioridad si ambas están definidas) |
| `EMAIL_REMITENTE` | Nombre y dirección que ve el cliente. Por defecto, tu usuario SMTP |
| `EMAIL_RESPONDER_A` | Dirección a la que llegan las respuestas, si es distinta |
| `ENVIO_MAX_DIA` | Tope diario de propuestas enviadas desde la app. Por defecto `5` |
| `REMITENTE_NOMBRE`, `REMITENTE_CARGO`, `AGENCIA_NOMBRE`, `REMITENTE_CONTACTO` | Firma de los mensajes. **Si falta alguno, la app no deja enviar** (evita que salga un «[TU NOMBRE]») |
| `APP_URL` | Para incluir el enlace al panel en el aviso (en Render se toma sola) |

## Cómo comprobar que funciona

1. Reinicia la app.
2. **Analítica**: debajo del medidor verás «Aviso por email al 80 %: activo (t***@gmail.com)». Como administrador, pulsa **Enviar correo de prueba**.
3. En un lead con email, elige el canal **Email** en el mensaje sugerido: aparece **Enviar por email**.

## Salvaguardas del envío a clientes

- Solo se envía al **email que el propio negocio publicó** (el de su web o su bio), nunca a una dirección escrita a mano: la app no puede usarse como relé.
- Siempre hay **vista previa editable y confirmación** explícita. No hay envío masivo ni automático.
- **Tope diario** y **una vez cada 24 h por lead**.
- Cada correo lleva tu firma y una línea para **darse de baja** («responde “no” y no volveré a escribirte»). La app **no lee las respuestas**: si alguien dice que no, márcalo tú como *Descartado* y la app dejará de ofrecer el envío a ese lead.
- Cada intento (enviado o con error) queda registrado, y el lead pasa a *Contactado* con su seguimiento a +3 días.
- Los mensajes de error nunca incluyen contraseñas ni claves.
