# BLACKBOX AI

Plataforma de testing web autorizado. **Fase 3: motor Playwright con demostración controlada.** Backend FastAPI y frontend React independientes, SQLite persistente, CRUD, ejecuciones en segundo plano, cancelación y resultados con capturas.

Repositorio: [Landerpro05/blackbox-ai](https://github.com/Landerpro05/blackbox-ai), rama `main`. Los commits se redactan en castellano y agrupan cambios relacionados. Los entornos virtuales, dependencias instaladas, secretos, bases de datos y evidencias locales quedan fuera del control de versiones.

## Alcance de esta entrega

- API de salud que consulta SQLite: `GET /api/v1/health`.
- Dashboard real: `GET /api/v1/dashboard`, contadores, evolución de 14 días UTC, últimas 8 ejecuciones y hasta 5 proyectos recientes.
- Modelos iniciales `Project`, `Run`, `Issue` y migración reversible.
- Interfaz oscura responsive, navegación, configuración de conexión de solo lectura, carga, reintento y error de conexión.
- Sin datos simulados: una instalación nueva muestra ceros y estados vacíos.
- Pruebas de integración con una base temporal separada de tus datos.
- Creación, listado paginado, detalle, edición y eliminación confirmada de proyectos con nombre, descripción, URL y fechas.
- Validación del backend, actualización de vistas tras guardar o eliminar y ámbito de workspace asignado por el servidor.
- Análisis real de la demo integrada mediante Chromium headless, con errores HTTP, JavaScript, consola, enlaces rotos y revisión pasiva de etiquetas de formularios.
- Historial, progreso, filtros por severidad, tiempos de navegación, evidencias y cancelación.

**La navegación remota está deshabilitada.** Se ha aplicado la alternativa de demostración controlada prevista en el encargo. Solo se analiza contenido integrado del proyecto, con activación del servidor y autorización expresa por ejecución. Guardar una URL no provoca navegación. Los informes HTML descargables quedan para la fase 4; la IA, para la 5. No hay autenticación multiusuario ni despliegue público.

## Estructura

```text
ProyectoTocho/
├── backend/      FastAPI, modelos, repositorios, esquemas, Alembic y tests
├── frontend/     React, TypeScript, Vite, Tailwind, Router, Recharts, Lucide
├── docs/         arquitectura y registro de verificación
├── scripts/      arranque PowerShell
└── README.md
```

Consulta [la arquitectura](docs/architecture.md) para conocer límites, semántica de contadores y controles pendientes.
Los registros de [fase 1](docs/verification-phase-1.md), [fase 2](docs/verification-phase-2.md) y [fase 3](docs/verification-phase-3.md) detallan los resultados comprobados. La fase 3 incluye una prueba de navegador del flujo completo y revisión de capturas de escritorio/móvil.

## Windows · instalación desde cero

Necesitas **Python 3.12** y **Node.js 24 LTS** con npm. Para los análisis también necesitas el Chromium headless de Playwright, instalado con el comando de abajo. No hacen falta Docker, GPU ni claves de IA. Puedes instalar los runtimes desde sus sitios oficiales o usar WinGet:

```powershell
winget install --exact --id Python.Python.3.12
winget install --exact --id OpenJS.NodeJS.LTS
```

Abre una terminal nueva después de instalarlos y comprueba:

```powershell
py -3.12 --version
node --version
npm.cmd --version
```

Los comandos siguientes parten de la raíz del proyecto. Usamos el ejecutable del entorno virtual directamente: no necesitas activar scripts de Python ni cambiar la política de ejecución de tu equipo.

### Backend

```powershell
Set-Location 'C:\Users\lande\Desktop\ProyectoTocho'
py -3.12 -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.lock
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Get-Location).Path '.tools\browsers'
.\backend\.venv\Scripts\python.exe -m playwright install chromium --only-shell
Copy-Item backend\.env.example backend\.env
Set-Location backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Usa `requirements.lock` en lugar de `requirements-dev.lock` si no necesitas herramientas de pruebas. Los archivos `.txt` contienen los rangos de dependencias directas; los `.lock` fijan las versiones verificadas. No sobrescribas un `.env` existente con tus cambios.

Se descarga solo Chromium headless y sus utilidades, sin Firefox ni WebKit. Consulta [Playwright: headless shell](https://playwright.dev/python/docs/browsers#chromium-headless-shell). `start-backend.ps1` reconoce automáticamente la caché `.tools/browsers`; si arrancas Uvicorn directamente, conserva la variable `PLAYWRIGHT_BROWSERS_PATH` en esa terminal.

### Frontend · otra terminal

```powershell
Set-Location 'C:\Users\lande\Desktop\ProyectoTocho\frontend'
npm.cmd ci --no-fund --no-audit
Copy-Item .env.example .env
npm.cmd run dev
```

Abre **http://127.0.0.1:5173**. La documentación de FastAPI está en **http://127.0.0.1:8000/docs**.

`--strictPort` evita que Vite cambie de puerto silenciosamente y deje de coincidir con CORS. Los servidores se enlazan a loopback y se detienen con `Ctrl+C` en sus terminales.

## Arranque rápido en este workspace ya preparado

Durante la implementación se instalaron Python 3.12 y Node 24 portables en `.tools/`, ya que no estaban disponibles globalmente. Esa carpeta, `backend/.venv`, `node_modules` y los datos locales están ignorados por Git. No necesitas instalar los runtimes globales para usar esta copia. Conserva `.tools/`: el entorno virtual depende de su Python.

Desde la raíz, abre **dos terminales PowerShell** y ejecuta un comando en cada una:

```powershell
# Terminal 1: aplica migraciones pendientes y arranca FastAPI.
Set-Location 'C:\Users\lande\Desktop\ProyectoTocho'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-backend.ps1
```

```powershell
# Terminal 2: encuentra el Node portable y arranca Vite.
Set-Location 'C:\Users\lande\Desktop\ProyectoTocho'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-frontend.ps1
```

El ajuste `Bypass` se limita al proceso que ejecuta cada script; no modifica la política del sistema. El motor está deshabilitado en este arranque normal. Para activarlo, usa el modo de demostración de la sección siguiente. En Windows, la demo necesita Uvicorn **sin `--reload` y con un solo worker**; la aplicación comprueba que el bucle admite los subprocesos de Playwright. `-Reload` se conserva para desarrollo del CRUD con la demo deshabilitada.

Para reinstalar dependencias del frontend con el Node portable:

```powershell
Set-Location 'C:\Users\lande\Desktop\ProyectoTocho'
$env:PATH = "$(Join-Path (Get-Location).Path '.tools\node');$env:PATH"
Set-Location frontend
npm.cmd ci --no-fund --no-audit
```

## Demostración completa de la fase 3

En esta copia ya están instalados Playwright y Chromium headless. La base está migrada. No se han añadido resultados ficticios ni proyectos de ejemplo automáticamente.

Si tienes un backend anterior abierto, detenlo con `Ctrl+C`. Desde la raíz, ejecuta cada bloque en una terminal distinta:

```powershell
# Terminal 1: habilita explícitamente solo la demo integrada.
Set-Location 'C:\Users\lande\Desktop\ProyectoTocho'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-backend.ps1 -Demo
```

```powershell
# Terminal 2: frontend.
Set-Location 'C:\Users\lande\Desktop\ProyectoTocho'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-frontend.ps1
```

1. Abre **http://127.0.0.1:5173/projects**.
2. Pulsa **Crear proyecto de demostración**. Es una operación real del CRUD, solicitada por ti.
3. Revisa los límites, marca **Autorizo analizar únicamente la demostración integrada de BLACKBOX AI** y pulsa **Iniciar análisis**.
4. Consulta el estado, las páginas analizadas, las incidencias y la duración. La pantalla consulta la API cada 1,5 segundos mientras la ejecución está activa.
5. Al terminar, filtra por severidad, abre los detalles técnicos y consulta las capturas. La página de Análisis y el proyecto conservan su historial.
6. Para probar cancelación con margen, edita el proyecto ya finalizado y cambia su URL a `http://blackbox-demo.invalid/slow`. Inicia otra ejecución y pulsa **Cancelar análisis**. El estado final se guarda después de cerrar Chromium.

La URL `http://blackbox-demo.invalid/` es un origen virtual de la demo, servido exclusivamente al navegador del motor mediante respuestas integradas. No requiere servidor de destino ni resolución DNS y no se abre directamente en un navegador normal. Las URLs reales, privadas, loopback y otros dominios se pueden registrar como datos de proyecto, pero **no se pueden analizar** en esta versión.

`-Demo` activa la opción únicamente en el proceso de backend. Para activación persistente local puedes establecer `BLACKBOX_DEMO_TESTING_ENABLED=true` en `backend/.env`. Por defecto es `false`; la demo tampoco puede habilitarse con `BLACKBOX_ENVIRONMENT=production`.

### Límites del ejecutor

| Recurso | Valor inicial | Máximo aceptado |
| --- | --- | --- |
| Análisis activos | 1 global | 1 global |
| Chromium / contexto / pestaña de análisis | 1 / 1 / 1 | 1 / 1 / 1 |
| Páginas | 10 | 20 |
| Profundidad | 2 | 3 |
| Timeout de navegación | 15 s | 30 s |
| Timeout global | 120 s | 180 s |
| Presupuesto de peticiones | 100 | 200 |
| Incidencias almacenadas | Hasta 200 | 200 |
| Captura | Viewport 1280 × 720 | 3 MB por PNG |

Los límites se eligen por ejecución y se guardan como una instantánea. Los valores históricos del proyecto no se sobrescriben. El timeout global interrumpe el trabajo de navegación; cerrar el navegador y terminar transacciones pendientes puede añadir un breve tiempo de limpieza. Las solicitudes que exceden el presupuesto se abortan; el contador observado puede incluir intentos bloqueados ya emitidos por la página. Alcanzar los límites de páginas/profundidad/peticiones termina el recorrido acotado; un timeout global deja la ejecución fallida con explicación y conserva los resultados parciales.

Solo hay un proceso de API y un ejecutor local. Un bloqueo de proceso por base de datos y un índice único de SQLite evitan ejecutores simultáneos. Los análisis usan tareas asyncio y transacciones cortas en hilos; no mantienen bloqueada la petición que los inicia. Una segunda solicitud recibe 409 mientras el navegador anterior sigue activo. Editar o eliminar el proyecto activo también devuelve 409.

Al apagar normalmente se solicita cancelación y se cierra el navegador. Tras un cierre brusco, el siguiente arranque marca las ejecuciones pendientes/en curso como fallidas por reinicio, incluso con la demo deshabilitada. No se reanudan ni se ejecutan automáticamente. No es una cola distribuida ni un servicio preparado para varios workers o varias máquinas.

### API de análisis

| Método y ruta | Resultado |
| --- | --- |
| `GET /api/v1/testing/capabilities` | Disponibilidad, modo, URL integrada y límites |
| `POST /api/v1/projects/{project_id}/runs` | 202; exige `authorize_demo: true` y admite `limits` |
| `GET /api/v1/projects/{project_id}/runs` | Historial paginado del proyecto |
| `GET /api/v1/runs` | Historial paginado del workspace |
| `GET /api/v1/runs/{run_id}` | Estado, progreso, duración y límites aplicados |
| `GET /api/v1/runs/{run_id}/issues?severity=high` | Incidencias, con filtro opcional |
| `GET /api/v1/runs/{run_id}/pages` | Páginas, estados HTTP, profundidad y tiempos |
| `POST /api/v1/runs/{run_id}/cancel` | 202; solicita cancelación de forma idempotente |
| `GET /api/v1/runs/{run_id}/pages/{page_id}/screenshot` | PNG con comprobación de ámbito |

Consultar, cancelar o descargar una evidencia de otro workspace devuelve 404. La API publica estados `pending`, `running`, `completed`, `failed`, `cancelled`. El estado pendiente reutiliza el `queued` histórico de SQLite para conservar compatibilidad. Una cancelación no modifica ejecuciones ya terminadas.

## Comprobar la conexión

Con ambos servidores arrancados:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Invoke-RestMethod http://127.0.0.1:8000/api/v1/dashboard | ConvertTo-Json -Depth 8
```

El endpoint de salud debe devolver `status: ok` y `database: connected`. En el dashboard, pulsa **Actualizar**: aparecerá el estado conectado y cambiará la hora de la consulta. Con una base nueva verás los cuatro contadores a cero y los paneles vacíos.

Detén FastAPI y pulsa **Actualizar** para ver el error de conexión. Arráncalo otra vez y pulsa **Reintentar conexión**. La pantalla de Configuración muestra la URL que está utilizando el frontend y un enlace a Swagger.

## Usar la gestión de proyectos

Si ya tenías la fase 1, no reinstales ni recrees la base de datos. Reinicia el backend mediante `start-backend.ps1`: aplica automáticamente la nueva migración. Si arrancas Uvicorn manualmente, ejecuta antes `python -m alembic upgrade head` con el Python del entorno virtual, desde `backend/`.

1. Abre `http://127.0.0.1:5173/projects` o pulsa **Proyectos** en el menú.
2. Pulsa **Nuevo proyecto**, escribe nombre, URL HTTP/HTTPS y descripción opcional, y guarda.
3. Consulta sus datos, fecha de creación y última actualización en el detalle.
4. Usa **Editar** para modificar los campos. Los límites iniciales del motor se muestran como información de solo lectura.
5. **Eliminar** abre una confirmación. Cancelar no realiza ninguna petición DELETE; confirmar elimina el proyecto, sus ejecuciones, errores y capturas asociadas de forma permanente. Un análisis activo debe terminar o cancelarse antes.
6. Vuelve al dashboard para ver los contadores y el resumen actualizados. El listado permite recorrer todos los proyectos en páginas de 12.

El formulario muestra carga, errores de validación y mensajes de éxito. Si el backend no está disponible, permite reintentar la lectura sin mostrar información inventada.

### API de proyectos

La ruta principal sigue la convención existente `/api/v1/projects`. También se exponen las rutas solicitadas `/api/projects` mediante el mismo router y los mismos datos. No cambies `VITE_API_BASE_URL`: salud y dashboard siguen bajo `/api/v1`.

| Método y ruta solicitada | Resultado |
| --- | --- |
| `GET /api/projects?limit=20&offset=0` | 200, `{items, total, limit, offset}`; límite entre 1 y 100 |
| `GET /api/projects/{id}` | 200, datos del proyecto |
| `POST /api/projects` | 201, proyecto creado y cabecera `Location` |
| `PATCH /api/projects/{id}` | 200, proyecto actualizado parcialmente |
| `DELETE /api/projects/{id}` | 204, respuesta sin cuerpo |

Creación y edición aceptan únicamente `name`, `description` y `base_url`. Nombre: 1–120 caracteres tras recortar espacios, sin controles. Descripción: opcional en creación, hasta 4000 caracteres; se vacía enviando `""`. URL: absoluta HTTP/HTTPS, máximo 2048 caracteres normalizados, sin credenciales, consultas ni fragmentos. Se permite guardar una URL local; **guardarla no autoriza ni ejecuta análisis**. No se comprueba conectividad ni se resuelve DNS. Las URLs se normalizan (por ejemplo, se añade `/` tras un dominio sin ruta).

PATCH conserva los campos omitidos; rechaza un objeto vacío, valores nulos y campos no editables. Los nombres no son únicos: varias aplicaciones pueden compartir nombre. Los errores usan 422 para entradas inválidas, 404 para proyectos inexistentes o fuera del ámbito local y 503 para fallos de base de datos, sin exponer SQL, rutas internas ni valores introducidos en los errores de validación.

El servidor asigna `workspace_id=local`. El cliente no puede modificarlo ni elegir otro workspace mediante cabeceras. Es una base para autorización futura, **no autenticación**: todos los usuarios del entorno local comparten el mismo ámbito. El CRUD y el dashboard consultan ese ámbito.

## Pruebas y build

```powershell
Set-Location 'C:\Users\lande\Desktop\ProyectoTocho\backend'
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pip check

Set-Location ..
# Solo si estás usando el Node portable de esta copia:
$env:PATH = "$(Join-Path (Get-Location).Path '.tools\node');$env:PATH"
Set-Location frontend
npm.cmd run build
npm.cmd run test:integration
```

`pytest` aplica las migraciones a archivos SQLite temporales: **118 casos correctos** en la verificación de esta entrega, conservando los 67 de fases anteriores. Incluye motor real, límites, cancelación, fallos, cierre, aislamiento, solicitudes bloqueadas, migraciones y el flujo React con Chromium. No modifica `backend/data/blackbox.db`. La prueba de React necesita Node y las dependencias del frontend instaladas. Para ejecutar solo los casos sin navegador usa `python -m pytest -m "not browser"` con el Python del entorno virtual.

`npm run build` comprueba TypeScript y genera `frontend/dist/`. `npm run test:integration` conserva la comprobación del cliente TypeScript del CRUD contra FastAPI temporal. La prueba `backend/tests/test_browser_ui.py`, ejecutada con pytest, añade los clics reales de creación de demo, inicio, resultados, filtros, evidencias, menú móvil y cancelación. Los procesos y datos de prueba son temporales; las capturas de QA quedan en `.tools/qa/`, ignoradas por Git.

## Configuración y datos

`backend/.env` (opcional):

```dotenv
BLACKBOX_ENVIRONMENT=development
BLACKBOX_DATABASE_URL=sqlite:///./data/blackbox.db
BLACKBOX_CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
BLACKBOX_DEMO_TESTING_ENABLED=false
```

`frontend/.env` (opcional):

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

Sin esos archivos se utilizan los mismos valores por defecto. Reinicia los servicios después de cambiar configuración. Las rutas relativas de SQLite se resuelven contra `backend/`, no contra el directorio de la terminal. La base habitual queda en `backend/data/blackbox.db`; reiniciar los servidores conserva los datos. Alembic, no `create_all`, controla el esquema.

Las variables `VITE_` son visibles en el navegador. No guardes allí secretos. No hay campos para credenciales ni claves de IA en esta fase.

Las evidencias se guardan bajo `backend/evidence/{run_id}/`. No se publica ese directorio como archivos estáticos: cada PNG pasa por una ruta con UUID y comprobación de workspace. Al cancelar o fallar se conservan los resultados parciales ya registrados. Los archivos temporales de capturas y el perfil del navegador se cierran/limpian; al borrar un proyecto se eliminan sus evidencias conocidas.

## Seguridad y alcance del modo demo

Solo se sirve HTML/JS integrado y versionado. No se acepta HTML, código, cookies, credenciales ni comandos del usuario. No hay un proxy de navegación ni se invoca `continue_()`/`fetch()` hacia destinos de análisis. Las redirecciones se revisan antes de seguirlas; se rechazan otros orígenes, métodos de escritura, iframes y consultas con secretos. Service Workers, WebSockets y descargas están deshabilitados o bloqueados. Los formularios se inspeccionan sin rellenarlos ni enviarlos.

La resolución de nombres del navegador se deshabilita y se configura un proxy sin salida como defensa adicional. **No se ha implementado ni certificado un sandbox SSRF general para Internet.** El ensayo de rebinding verifica que un dominio variable nunca se resuelve ni se acepta, pues toda navegación externa está rechazada de antemano. Tampoco se permiten servidores locales arbitrarios. Antes de ampliar destinos harán falta aislamiento de red real y pruebas de DNS, conexiones, redirecciones y subrecursos sobre esa arquitectura.

Los mensajes almacenados se redactan (contraseñas/tokens, Bearer, consultas URL, credenciales y correo). Las capturas enmascaran campos y bloques marcados sensibles de la demo. Esto es una protección comprobada para el contenido integrado; no es un detector universal de datos personales en páginas ajenas. No se guardan cuerpos de peticiones, cookies ni cabeceras de autenticación.

## Solución de problemas

- **`node`/`npm` no se reconoce:** instala Node o usa `start-frontend.ps1`, que añade `.tools/node` al PATH de su proceso. Invoca `npm.cmd` para evitar el bloqueo de `npm.ps1`.
- **Python 3.12 no aparece en `py`:** la instalación portable de esta copia no se registra en el lanzador Windows. Usa el entorno `backend/.venv` ya creado; en otra máquina instala Python 3.12 antes de crear el entorno.
- **API devuelve 503:** revisa que el directorio de la base sea escribible y ejecuta `python -m alembic upgrade head` usando el ejecutable del entorno y situándote en `backend/`.
- **Puerto ocupado:** detén el servicio anterior. Si cambias el puerto de FastAPI, actualiza `VITE_API_BASE_URL`; si cambias el de Vite, actualiza `BLACKBOX_CORS_ORIGINS`.
- **CORS:** el origen incluye protocolo, nombre de host y puerto. Se permiten `localhost:5173` y `127.0.0.1:5173`, no cualquier origen. Consulta [FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/).
- **No aparecen proyectos:** usa Nuevo proyecto o, con la demo activada, Crear proyecto de demostración. No se insertan registros automáticamente.
- **Iniciar análisis está deshabilitado:** activa la demo en el servidor y utiliza un proyecto del origen integrado. Las demás URLs no se pueden analizar en esta fase.
- **Falla el lanzamiento del motor:** ejecuta la instalación de Chromium indicada arriba y comprueba `PLAYWRIGHT_BROWSERS_PATH`. En Windows usa un solo worker, sin `--reload`.
- **409 al iniciar, editar o eliminar:** hay una ejecución activa. Espera o solicita su cancelación; el slot se libera después del cierre del navegador.

Se usa un solo worker y un solo Chromium de análisis. No se han añadido Celery, Redis, contenedores, librerías LLM, DuckDB ni infraestructura distribuida. No hay análisis contra sitios públicos en las pruebas.

**La fase 4 requiere tu confirmación. No se ha iniciado ni se ha integrado IA.**
