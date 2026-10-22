# Servidor de CGAME (API real, con el SVM entrenado corriendo del lado del servidor)

Este servidor (Flask) expone exactamente los endpoints que `client/cgame.html` ya sabe
consumir cuando lo abres con `?api=https://tu-servidor/api`. No reimplementa el SVM:
importa `backend/recommender/` tal cual (`compute_result`, `recommend`, `LinearSVM`) y
usa los mismos coeficientes de `backend/data/svm_model.json` que ya viste en el juego.

No puedo desplegarlo por ti (este entorno de chat no tiene salida a internet), pero
aquí tienes el código ya probado — funcionó de punta a punta contra el juego real en
pruebas automatizadas — y los pasos para ponerlo en línea tú mismo. Elige una opción.

## 0. Probarlo en tu computadora (2 minutos)

```bash
cd cgame/backend/server
pip install -r requirements.txt
export CGAME_SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
python app.py
```

Verás `Escuchando en http://0.0.0.0:5057/api`. Ahora abre `client/cgame.html` (el
archivo local, no el publicado) agregando el parámetro:

```
client/cgame.html?api=http://127.0.0.1:5057/api
```

Regístrate y juega: los datos ya se están guardando en `cgame.db` (SQLite) y la
recomendación que ves viene de este proceso Python, no del navegador.

**Importante:** para que el juego *publicado* en claude.ai use este servidor, el
servidor tiene que tener una URL pública (https) — `http://127.0.0.1` solo funciona
si abres el juego desde la misma computadora donde corre el servidor. Para que lo usen
estudiantes desde otros dispositivos, necesitas una de las opciones de abajo.

## 0.5. Si el servidor "se cayó" (checklist rápido)

1. Abre `https://TU-SERVIDOR/api/health`. Si tarda ~30-60 s y luego responde `"ok": true`,
   no estaba caído: estaba **dormido** (normal en Render gratis). El juego ya espera solo
   hasta 75 s mostrando "Despertando el servidor…".
2. Si no responde: en Render entra a tu servicio → **Logs**. Busca `Out of memory`,
   `ModuleNotFoundError` o errores de build. Luego **Manual Deploy → Clear build cache & deploy**.
3. Esta versión ya **no instala scikit-learn ni numpy** en el servidor (solo hacen falta para
   entrenar), así que consume mucho menos memoria y construye más rápido: vuelve a subir
   `backend/server/requirements.txt` actualizado a tu repositorio y redespliega.
4. Si sigue sin levantar, pásate a PythonAnywhere (sección siguiente).

## 0.6. Migrar a PythonAnywhere (gratis, no duerme y el disco persiste)

Ventajas frente a Render gratis: la base SQLite **se conserva** entre reinicios y no hay
"servidor dormido". Límites del plan gratis (revísalos en su sitio, cambian): una sola
web app, cuota diaria de CPU y acceso saliente a internet restringido (no lo necesitamos).

1. Crea una cuenta gratis en pythonanywhere.com (usuario = `TU_USUARIO`).
2. Pestaña **Files** → sube la carpeta `backend/` y `shared/` a `/home/TU_USUARIO/cgame/`
   (`cgame/backend/recommender`, `cgame/backend/data`, `cgame/backend/server`, `cgame/shared`).
3. Pestaña **Consoles** → abre una consola *Bash* y ejecuta:
   `pip install --user flask pyjwt`
4. Pestaña **Web** → **Add a new web app** → *Manual configuration* → la versión de Python más
   reciente disponible.
5. En **Web → Code → WSGI configuration file**, borra todo y pega el contenido de
   `wsgi_pythonanywhere.py`, cambiando `TU_USUARIO` y las dos claves por valores tuyos.
6. Pulsa **Reload**. Prueba `https://TU_USUARIO.pythonanywhere.com/api/health`.
7. Tu enlace para compartir pasa a ser:
   `https://gabrielasa27.github.io/cgame/cgame/client/index.html?api=https://TU_USUARIO.pythonanywhere.com/api`
8. Panel del docente: `https://TU_USUARIO.pythonanywhere.com/admin` (usa tu `CGAME_ADMIN_KEY`).

## 1. Opción más simple: Render.com (gratis)

1. Sube la carpeta `cgame/` a un repositorio de GitHub.
2. En [render.com](https://render.com), crea cuenta → **New** → **Blueprint** → conecta
   el repositorio. Render detecta `backend/server/render.yaml` automáticamente y arma el
   servicio (usa el `Dockerfile` incluido).
3. Espera el build (unos 2-3 minutos). Render te da una URL como
   `https://cgame-api-xxxx.onrender.com`.
4. Prueba que responde: abre `https://cgame-api-xxxx.onrender.com/api/health` en el
   navegador — debe devolver un JSON con `"ok": true`.
5. Abre el juego publicado agregando `?api=`:
   `https://claude.ai/artifact/CQH6y6BguTFkdFycKbdq4g?api=https://cgame-api-xxxx.onrender.com/api`

   (En el plan gratuito, Render "duerme" el servicio tras 15 minutos sin uso; la
   primera visita tras eso tarda ~30 s en responder mientras despierta. Para un salón de
   clases en vivo, conviene el plan pago o cualquiera de las opciones de abajo.)

## 2. Railway.app / Fly.io (gratis con límites, no duermen igual)

Ambos leen el mismo `Dockerfile`:

- **Railway**: New Project → Deploy from GitHub repo → selecciona `cgame` → cuando
  pregunte el Dockerfile, apunta a `backend/server/Dockerfile` con contexto en la raíz
  del repo → agrega la variable de entorno `CGAME_SECRET_KEY` (genera una con
  `python3 -c "import secrets;print(secrets.token_hex(32))"`) → agrega un volumen
  persistente montado en `/var/data` y pon `CGAME_DB_PATH=/var/data/cgame.db` si quieres
  que los datos sobrevivan a los redeploys.
- **Fly.io**: `fly launch` dentro de `cgame/` (detecta el Dockerfile), `fly volumes
  create cgame_data --size 1`, monta el volumen en `/var/data`, define
  `CGAME_SECRET_KEY` con `fly secrets set`, y `fly deploy`.

## 3. Un VPS propio (DigitalOcean, un servidor de la escuela, etc.)

```bash
git clone <tu-repo> && cd cgame/backend/server
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export CGAME_SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
export CGAME_DB_PATH=/var/lib/cgame/cgame.db   # crea esa carpeta antes
gunicorn app:app --bind 127.0.0.1:5057 --workers 2 --threads 4 --daemon
```

Pon Nginx o Caddy delante para servir HTTPS (el navegador exige https para que
`fetch()` funcione desde una página en claude.ai). Con Caddy es una sola línea en el
`Caddyfile`:

```
tu-dominio.com {
    reverse_proxy 127.0.0.1:5057
}
```

Caddy obtiene el certificado HTTPS automáticamente.

## Cómo ver los datos de todos los estudiantes

Dentro del juego, "Datos para el docente" solo muestra los intentos de la cuenta con
la que iniciaste sesión (a propósito: un estudiante no debe ver los datos de otro).
Para ver a **todos los estudiantes juntos**, el servidor expone un panel aparte:

```
https://tu-servidor.com/admin
```

Pide ahí la clave de administrador (`CGAME_ADMIN_KEY`) — en Render la encuentras en
tu servicio → pestaña **Environment** → variable `CGAME_ADMIN_KEY` (se generó sola si
usaste el `render.yaml` incluido). Pégala en el panel y pulsa "Cargar datos": verás
una tabla con todos los intentos de todos los estudiantes (nombre, correo, juego,
nivel, puntaje, tiempo, errores, ayudas, resultado y fecha) y un botón para descargar
todo como CSV.

Si prefieres no exponer una clave en un formulario web, puedes llamar directamente
al endpoint que usa esa página:

```bash
curl "https://tu-servidor.com/api/admin/attempts?key=TU_CLAVE"
```

## Variables de entorno

| Variable | Para qué sirve | Por defecto |
|---|---|---|
| `CGAME_SECRET_KEY` | Firma los tokens de sesión. **Defínela siempre en producción** — si no, se genera una al azar en cada arranque y las sesiones se invalidan al reiniciar. | aleatoria por arranque |
| `CGAME_ADMIN_KEY` | Clave para entrar al panel `/admin` (ver todos los estudiantes). **Defínela siempre en producción** por la misma razón que la anterior. | aleatoria por arranque (se imprime en los logs al iniciar) |
| `CGAME_DB_PATH` | Dónde guardar la base SQLite. Ponla en un disco persistente si tu plataforma reinicia el contenedor sin conservar el disco. | `backend/server/cgame.db` |
| `CGAME_CORS_ORIGIN` | Qué origen puede llamar a la API. `*` funciona para probar; para producción puedes restringirlo a `https://claude.ai`. | `*` |
| `PORT` | Puerto donde escucha (varias plataformas lo definen automáticamente). | `5057` |

## Qué hace y qué no hace este servidor

- Implementa exactamente los 6 endpoints que el cliente espera:
  `POST /register`, `POST /login`, `GET /me`, `GET /attempts`, `POST /attempts`,
  `GET /recommendation` — todos bajo `/api`.
- Cada `POST /attempts` completado llama a `recommend(MODEL, historial)` — la misma
  función de `backend/recommender/recommend.py`, con el modelo entrenado — y guarda la
  recomendación para que `GET /recommendation` la devuelva.
- Guarda todo en SQLite (`users`, `attempts`, `recommendations`) — suficiente para un
  salón de clases; si necesitas más escala, cambia `sqlite3` por Postgres sin tocar la
  lógica de `recommender/`.
- **Aviso de seguridad honesto**: el navegador ya calcula el puntaje antes de
  enviarlo (`score`, `accuracy`, etc.), no los eventos crudos del intento. Para un
  prototipo o una clase esto es razonable, pero un estudiante con conocimientos técnicos
  podría enviar un puntaje falso directamente a la API. Si esto va a tener peso en una
  calificación real, el siguiente paso sería reenviar los eventos crudos (aciertos,
  fallos, movimientos) y recalcular `compute_result` del lado del servidor antes de
  guardar — la función ya existe en `recommender/scoring.py`, solo faltaría cambiar qué
  datos manda el cliente.
- No implementa recuperación de contraseña ni verificación de correo (no hacía falta
  para el prototipo). Se puede agregar sin tocar el resto.

## Reentrenar el modelo con datos reales

Cuando tengas intentos reales guardados en `cgame.db`, puedes exportarlos y usarlos en
vez de los casos simulados de `recommender/simulate.py` para reentrenar
(`recommender/model.py::train`). El resto del sistema (cliente, servidor, endpoints)
no cambia: solo se reemplaza `backend/data/svm_model.json` por el nuevo modelo entrenado
y se reconstruye el cliente con `python tools/build_client.py` si también quieres
actualizar la copia que corre en el navegador cuando se usa sin servidor.
