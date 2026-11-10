# BLACKBOX AI

Plataforma de testing web autorizado. **Fase 6: Testing Lab, suites declarativas, CLI y GitHub Actions.** Conserva proyectos, análisis, informes, regresiones e inteligencia por reglas y LLM opcional.

Repositorio: [Landerpro05/blackbox-ai](https://github.com/Landerpro05/blackbox-ai). La rama `feature/phase-6-local-testing-ci` parte exactamente de `236937beca23c1158ee1b331ef8601f160552d8e`, último commit de fase 5. No se hace merge automático. Los commits están en castellano. Dependencias instaladas, secretos, bases de datos y evidencias locales quedan fuera del control de versiones.

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
- Informes HTML autónomos y PDF, exportaciones JSON/CSV, comparación de ejecuciones y gráficos históricos con datos de SQLite.
- Diagnósticos por reglas sin clave, interpretación LLM con consentimiento, hipótesis vinculadas a evidencias, agrupación determinista y propuestas de tests Playwright copiables.
- Entornos por proyecto, suites de siete tipos, resultados persistidos por caso, importación revisada de sugerencias y CLI con códigos de salida diferenciados.
- Aplicación HTTP local controlada con catálogo verificado, consentimiento por ejecución y bloqueo de otros destinos; workflow de CI sin LLMs comerciales.

**La navegación remota está deshabilitada.** Solo se analiza contenido integrado del proyecto, con activación del servidor y autorización expresa por ejecución. Guardar una URL no provoca navegación. Los informes y el análisis por reglas funcionan offline. El LLM opcional envía únicamente contexto textual redactado al proveedor configurado, tras autorización expresa; no recibe herramientas ni capturas. No hay autenticación multiusuario ni despliegue público.

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
Los registros de [fase 1](docs/verification-phase-1.md), [fase 2](docs/verification-phase-2.md), [fase 3](docs/verification-phase-3.md), [fase 4](docs/verification-phase-4.md), [fase 5](docs/verification-phase-5.md) y [fase 6](docs/verification-phase-6.md) detallan los resultados comprobados, incluidas pruebas reales de navegador y evaluaciones controladas de inteligencia.

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

`pytest` aplica las migraciones a archivos SQLite temporales. Conserva los casos de las fases 1–5 y añade cobertura de políticas locales, entornos, suites, CLI y navegador. Los resultados de esta entrega están en [la verificación de fase 6](docs/verification-phase-6.md). No modifica `backend/data/blackbox.db` ni realiza llamadas comerciales reales. La prueba de React necesita Node y las dependencias del frontend instaladas. Para ejecutar solo los casos sin navegador usa `python -m pytest -m "not browser"` con el Python del entorno virtual.

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

Las variables `VITE_` son visibles en el navegador. No guardes allí secretos. La clave de IA solo se configura en el backend; la interfaz nunca la recibe ni dispone de un campo para introducirla.

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

## Informes y comparación de la fase 4

1. Finaliza dos análisis de un mismo proyecto de demostración.
2. Abre cada ejecución y consulta el resumen por severidad. Descarga HTML, PDF, JSON o CSV desde «Informe de ejecución».
3. Las capturas están desmarcadas por defecto en la interfaz. Puedes incluirlas en HTML/PDF; revisa su contenido antes de compartirlas.
4. En el proyecto, «Evolución de calidad» muestra totales históricos, navegación media, severidades/tipos, páginas de hasta 20 ejecuciones y enlaces a sus informes.
5. En «Informes» o «Análisis», selecciona proyecto, base anterior y destino reciente. Pulsa «Comparar ejecuciones» y filtra NEW, RESOLVED, PERSISTENT o UNCONFIRMED.

| Endpoint GET bajo `/api/v1` | Resultado |
| --- | --- |
| `/runs/{id}/report` | Documento JSON estructurado para el resumen y sus detalles |
| `/runs/{id}/report/html?include_evidence=true` | HTML autónomo, sin JavaScript ni recursos remotos |
| `/runs/{id}/report/pdf?include_evidence=true` | PDF A4 con portada, tablas, cabeceras y páginas; ReportLab, sin Chromium |
| `/runs/{id}/export/json` | JSON UTF-8, versión de esquema 1; sin archivos ni rutas locales |
| `/runs/{id}/export/csv` | CSV de incidencias con metadatos y totales, UTF-8 con BOM, fórmulas neutralizadas |
| `/projects/{id}/analytics?limit=20&offset=0` | Agregaciones SQL y ejecuciones paginadas, máximo 50 por petición |
| `/projects/{id}/compare?base_run_id=...&target_run_id=...` | Grupos de incidencias comparados sin modificar el histórico |

Los informes requieren una ejecución finalizada (completada, fallida o cancelada). Las dos últimas llevan aviso de parcialidad. Una ejecución activa devuelve 409; un recurso inexistente o de otro workspace, 404; UUID/parámetros inválidos, 422; un export excesivo, 413. Solo se genera un HTML/PDF a la vez por proceso; otra petición recibe 409 para reintentar sin crear una cola.

La huella SHA-256 usa tipo, URL normalizada sin consulta/fragmento y título/descripción redactados. Normaliza espacios, mayúsculas del mensaje y host, puertos predeterminados, UUID, fechas ISO y duraciones con unidades. Conserva códigos HTTP y otros números con significado técnico. No utiliza IDs de incidencia/ejecución, severidad, tiempos de navegación ni fechas del registro. Los duplicados se agrupan; las cifras comparadas son grupos, mientras la analítica cuenta registros.

**La comparación es heurística.** Cambiar un mensaje, ruta o tipo puede separar un mismo fallo; mensajes parecidos pueden agrupar fallos distintos. NEW significa observado solo en destino, aunque la base pudo no cubrirlo. RESOLVED significa ausencia observada en una URL revisitada bajo las mismas condiciones, sin garantizar corrección. Se exige que ambas ejecuciones estén completadas, tengan igual destino y límites, sin truncamiento ni problemas de navegación/presupuesto; el destino debe registrar esa URL sin navegación bloqueada. Las demás ausencias son UNCONFIRMED. No se cambia `Issue.status`.

Los informes incluyen como máximo 200 incidencias, 20 páginas y 4 capturas de 1920×1080, 3 MB por PNG y 4 MB acumulados, con recodificación y eliminación de metadatos. El máximo de export es 12 MB. Se informan omisiones y los totales agregados conservan todos los registros. El desglose por tipos se limita a 50 grupos; los contadores HTTP/JS/enlaces se calculan aparte. JSON/CSV incluyen referencias a páginas, sin bytes de imágenes. El CSV vacío conserva una fila de metadatos con totales cero; no inventa una incidencia.

Se escapa todo texto al generar HTML y marcado PDF. La CSP del HTML impide contenido activo y recursos externos; solo se incrustan PNG validados del mismo análisis. Las rutas UUID rechazan traversal y enlaces/junctions a otros archivos o ejecuciones. Se redactan credenciales conocidas, consultas URL, correos y rutas locales en datos históricos exportados; la redacción es heurística y las capturas no tienen OCR ni detección universal de secretos. El PDF utiliza la fuente libre Vera incluida en ReportLab; caracteres no soportados se representan con `?`. Consulta [ReportLab Platypus](https://docs.reportlab.com/reportlab/userguide/ch5_platypus/) y [CSV de Python](https://docs.python.org/3.12/library/csv.html).

No hay cambios de esquema ni nuevos índices: se reutilizan los índices por workspace, proyecto, ejecución y fechas. Alembic sigue siendo la autoridad del esquema. ReportLab y sus dependencias de imagen se instalan con los locks habituales; `pypdf` solo se usa en pruebas. Poppler se utilizó como herramienta local de revisión, no es dependencia de la aplicación.

## Testing Lab y CI — Fase 6

**Restricción deliberada:** el laboratorio local solo admite la aplicación de desarrollo incluida en este repositorio. No está habilitado para aplicaciones arbitrarias, aunque sean propias. Playwright, la interceptación y el proxy no constituyen un aislamiento de sistema operativo suficiente frente a HTML/JavaScript malicioso. En esta fase se aplica la alternativa controlada permitida en los requisitos: el broker compara cada cuerpo, estado, Content-Type y Location con el catálogo versionado antes de entregarlo al navegador. El contenido alterado se rechaza, no se sanitiza ni se ejecuta.

### Configurar el catálogo local

Arranca la aplicación controlada en otra terminal, desde `backend/`:

```powershell
.\.venv\Scripts\python.exe -m app.lab_server --port 3000
```

Solo escucha en `127.0.0.1`. Contiene fallos intencionados, incluyendo `/missing`, `/server-error`, JavaScript en `/`, redirección prohibida y `/slow`. No representa un servicio de producción ni requiere GPU. Para habilitar ese origen, configura `backend/.env` y reinicia el backend con un único worker, sin `--reload` en Windows:

```dotenv
BLACKBOX_LOCAL_LAB_ENABLED=true
BLACKBOX_LOCAL_LAB_ALLOWED_ORIGINS=["http://127.0.0.1:3000"]
```

Por defecto el modo permanece deshabilitado y la lista está vacía. Solo se admiten HTTP/HTTPS, IP literal `127.0.0.1` o `[::1]` y puerto explícito 1024–65535. El servidor incluido ofrece HTTP IPv4; usar HTTPS exige un servidor de catálogo con certificado TLS válido, sin omitir su comprobación. `localhost`, otras redes privadas, credenciales, consultas, fragmentos, rutas no catalogadas y saltos de puerto se rechazan. Una ejecución solo autoriza su origen, aunque la lista del servidor contenga otros. No se amplía el acceso por compartir un workspace.

Antes de migrar tus datos conserva una copia consistente de SQLite. Ejecuta `python -m alembic upgrade head` desde `backend/`. La revisión nueva es `e62f1b809a73`; conserva las ejecuciones, incidencias y análisis de las fases anteriores.

### Crear y ejecutar una suite

1. Abre **Testing Lab** y selecciona un proyecto existente o crea uno.
2. Registra un entorno **Desarrollo local controlado** con URL `http://127.0.0.1:3000/`. También puedes usar **Demo integrada** con `http://blackbox-demo.invalid/` cuando esté habilitada en el backend. Registrar/editar no accede a la URL.
3. Pulsa **Comprobar**, revisa el origen y autoriza expresamente la solicitud. Un resultado `verified` confirma contenido compatible en ese momento; no concede autorización a futuras ejecuciones.
4. En **Test Suites**, crea una suite y añade casos. Para una primera suite correcta usa `/about`: HTTP 200, título `Acerca de`, existencia de `h1`, texto `Acerca de` o ausencia de errores JavaScript. La ruta `/depth/1` permite comprobar enlaces internos o navegación a `/depth/2`. La portada contiene errores JavaScript deliberados.
5. Elige el entorno y marca el consentimiento de esa ejecución. Se ejecutan los casos habilitados por orden numérico, con un máximo de 20 y sin superar las páginas del entorno. Las posiciones son únicas; para intercambiarlas usa primero una posición libre.
6. Consulta progreso, `pass/fail/error/skipped`, evidencias y cancelación en la ejecución. Informes e inteligencia anteriores siguen disponibles al finalizar. El historial conserva una copia del entorno, del destino y de cada caso; editar o eliminar la suite/entorno no cambia estos resultados.

Los siete tipos son estado HTTP, título exacto, existencia de selector simple, texto visible, ausencia de errores JavaScript/consola, enlaces internos (hasta 20 por caso) y navegación autorizada. No hay evaluadores de código del usuario, acciones de formulario ni scripts libres. Los errores de política, transporte o presupuesto son `error`; una expectativa incumplida es `fail`. Una ejecución con aserciones fallidas puede terminar `completed`: significa que el motor completó sus comprobaciones, no que todas fueran correctas. Cancelar marca como `skipped` los casos pendientes.

Los límites por defecto siguen siendo 10 páginas/casos, profundidad 2, navegación 15 s, global 120 s y 100 solicitudes. Solo hay un navegador, una pestaña de análisis y una ejecución activa. Las suites no hacen crawling adicional; la profundidad limita el crawler de demo y los casos de navegación tienen un único salto explícito. Descargas, WebSockets, iframes, service workers y métodos distintos de GET permanecen bloqueados. Chromium trabaja offline; un broker separado realiza las peticiones acotadas al catálogo local. No se copian cookies ni cabeceras de la aplicación al navegador.

Para importar una propuesta de IA, usa el ID del análisis y su índice (desde 0) en la suite del mismo proyecto, confirma la conversión y revisa el caso deshabilitado resultante. Solo se admiten las plantillas conocidas con evidencia compatible; el código generado se ignora. LLM sigue siendo opcional y requiere consentimiento independiente y cuotas. Un fallo del proveedor no afecta a las pruebas normales.

### CLI

Desde `backend/`, usando el Python del entorno virtual:

```powershell
python -m app.cli demo --authorize --json results.json
python -m app.cli test --project PROJECT_ID --suite SUITE_ID --environment ENV_ID --origin http://127.0.0.1:3000 --authorize --timeout 180 --json results.json
```

La CLI se conecta por defecto a `http://127.0.0.1:8000/api/v1`, sin proxies ni redirecciones. `--api` solo admite una API en loopback. `demo` crea un proyecto, entorno y suite reales con cuatro casos en `/about`; las ejecuciones permanecen guardadas. No elimina datos automáticamente. `test` comprueba que la suite pertenece al proyecto indicado. El progreso se escribe en stderr y `--json` guarda el resultado estructurado, sin secretos del proveedor.

Para CI o uso aislado, la API puede vivir en el propio proceso usando los mismos servicios y motor:

```powershell
$env:BLACKBOX_DEMO_TESTING_ENABLED='true'
python -m app.cli demo --standalone --database ../.tools/cli/demo.db --authorize --json ../.tools/cli/results.json
```

`--database` requiere `--standalone`; se migra al inicio y debe ser una base independiente de cualquier API activa. El bloqueo de proceso rechaza una base ocupada. `--standalone` no evita las políticas del servidor ni habilita los modos de testing automáticamente. `--timeout` admite 5–300 segundos; al agotarse solicita cancelación y espera la limpieza. Ctrl+C también solicita cancelación.

| Código | Significado |
| --- | --- |
| 0 | Motor completado y todos los casos correctos |
| 1 | Motor completado con aserciones fallidas |
| 2 | Configuración, política, conexión o ejecución fallida |
| 3 | Cancelación o timeout de espera de la CLI |

### GitHub Actions

El workflow [ci.yml](.github/workflows/ci.yml) se ejecuta en push a ramas feature/main, Pull Requests y despacho manual cuando GitHub lo permita. Los push que solo modifican Markdown no repiten el análisis; los PR siguen activando la verificación. No hace push ni merge. Usa Ubuntu 24.04, Python 3.12.16 y Node 24.22.2, acciones fijadas por SHA, dependencias Python con hashes y `npm ci`. El token solo dispone de `contents: read`, sin credenciales Git persistidas. Limita la concurrencia a una ejecución por workflow/ref, cancela versiones anteriores de la misma rama y aplica timeout de 20 minutos. No ejecuta jobs en paralelo ni usa `pull_request_target`.

Verifica dependencias, migraciones, todos los tests (incluidos navegador e integración local), el cliente TypeScript y el build. También ejecuta la demo CLI en otra base temporal. Los servidores y destinos de las pruebas pertenecen al propio runner; no se analizan sitios públicos ni se llaman LLMs comerciales. Las descargas de dependencias y Chromium sí requieren conexión durante la instalación. Se cachean descargas de pip/npm con claves ligadas a los lockfiles, sin cachear bases, evidencias ni secretos. Los artifacts contienen únicamente JUnit y el JSON de la demo sintética, conservados 7 días.

La pantalla CI muestra instrucciones y **estado remoto sin consultar**; no inventa un estado verde. Consulta resultados reales en [Actions](https://github.com/Landerpro05/blackbox-ai/actions). El estado comprobado de esta entrega se registra en [verificación de fase 6](docs/verification-phase-6.md).

### API del laboratorio

Todos los endpoints usan `/api/v1`, UUIDs y el workspace asignado por el servidor. Este ámbito local no equivale a autenticación multiusuario.

| Recurso | Operaciones |
| --- | --- |
| `/lab/capabilities` | GET capacidades y restricciones actuales |
| `/projects/{id}/environments` | GET paginado, POST |
| `/environments/{id}` | PATCH, DELETE |
| `/environments/{id}/check` | POST con `authorize` y `consent_origin` exacto |
| `/projects/{id}/suites` | GET paginado, POST |
| `/suites/{id}` | GET detalle/casos, PATCH, DELETE |
| `/suites/{id}/cases` | POST |
| `/suite-cases/{id}` | PATCH, DELETE |
| `/suites/{id}/import-ai` | POST conversión confirmada |
| `/suites/{id}/runs` | POST con entorno y consentimiento, GET historial paginado |
| `/runs/{id}/suite-results` | GET resultados persistidos y contadores |
| `/runs/{id}/cancel` | POST cancelación compartida con el motor existente |

Ejemplo declarativo, sin código ejecutable:

```json
{"name":"Título esperado","position":0,"enabled":true,"definition":{"type":"title","path":"/about","expected_title":"Acerca de"}}
```

Quedan pendientes el aislamiento de sistema operativo para aplicaciones propias arbitrarias, autenticación multiusuario, staging remoto y consulta automática de estados de GitHub. No se inicia la Fase 7.

## AI Intelligence - Fase 5

### Modo local sin API

No requiere clave, GPU ni modelo instalado. En una ejecución finalizada, pulsa **Analizar con IA**, conserva **Análisis basado en reglas** y confirma. Se guardan el resumen, hipótesis sin confirmar, recomendaciones, evidencias usadas y plantillas compatibles con HTTP, JavaScript o consola. Las incidencias desconocidas o incompletas reciben un diagnóstico general que reconoce la falta de información. Los resultados se pueden volver a consultar tras reiniciar.

La sección distingue los hechos guardados de las hipótesis, recomendaciones y código propuesto. Las agrupaciones por huella reutilizan fase 4; las relaciones adicionales de un LLM, si existen, se muestran aparte como hipotéticas. Puedes copiar los tests; **no se ejecutan ni se aplican correcciones automáticamente**. El código usa una constante BASE_URL que debes sustituir por tu entorno autorizado. El dominio virtual de la demo solo existe dentro del motor BLACKBOX AI.

### Modo LLM opcional

El primer adaptador utiliza la API Messages de Anthropic, mediante una interfaz independiente del proveedor. No se instala un SDK de IA ni modelos locales; HTTPX2, ya usado en pruebas, pasa a ser dependencia de ejecución. Modelo y clave se configuran exclusivamente en `backend/.env` o en el entorno del proceso:

```dotenv
BLACKBOX_AI_PROVIDER=anthropic
BLACKBOX_AI_MODEL=identificador-de-un-modelo-compatible
BLACKBOX_AI_API_KEY=
BLACKBOX_AI_TIMEOUT_SECONDS=30
BLACKBOX_AI_MAX_RETRIES=1
BLACKBOX_AI_MAX_OUTPUT_TOKENS=2000
BLACKBOX_AI_DAILY_CALL_LIMIT=10
BLACKBOX_AI_RUN_CALL_LIMIT=2
BLACKBOX_AI_DAILY_TOKEN_LIMIT=100000
BLACKBOX_AI_COOLDOWN_SECONDS=60
```

El identificador anterior es un marcador: usa un modelo disponible en tu cuenta que admita Messages con salida JSON estructurada. Guarda tu clave real solo en ese archivo local ignorado o en el entorno del backend. No la pegues en archivos versionados ni en variables VITE_. Consulta [las salidas estructuradas oficiales](https://platform.claude.com/docs/en/build-with-claude/structured-outputs). Para desactivar llamadas externas usa `BLACKBOX_AI_PROVIDER=disabled`; las reglas siguen disponibles.

Después de instalar el lock actualizado y aplicar Alembic, reinicia FastAPI. Un proceso Uvicorn ya abierto no incorpora estos módulos automáticamente. No sobrescribas un `.env` existente con el ejemplo.

El modal identifica proveedor/modelo, datos enviados, límites y posibles costes. **Seleccionar LLM no autoriza el envío**: hay que marcar la casilla explícita. El servidor exige JSON booleano `true` y coincidencia de proveedor/modelo confirmados. Si cambia la configuración, rechaza la solicitud para que se revise la autorización. No se permite cambiar endpoint, proveedor, clave o modelo mediante el cuerpo de la petición.

Se envían hasta **12 000 bytes de contexto textual**, con como máximo 20 incidencias y 10 páginas, más instrucciones y esquema JSON. Las URLs de las evidencias incluidas se conservan completas, hasta el límite histórico de 2048 caracteres. Se omiten registros completos para cumplir el presupuesto, sin recortar rutas e inventar destinos de tests. La comparación histórica opcional contiene solo un resumen del análisis anterior del mismo proyecto/workspace. No se envían capturas, archivos, código fuente, cabeceras, cookies ni claves. La redacción por patrones no es una garantía universal: revisa la información antes de autorizar al proveedor.

### Límites, costes y estados

- Una interpretación activa por base de datos, tanto rules como llm. La llamada LLM se realiza en segundo plano: POST devuelve 202 y el frontend consulta el estado.
- Se reutiliza un resultado pending/running/completed si coincide el contexto redactado, modo, proveedor, modelo, máximo de hipótesis y versión de prompt. La autorización externa se comprueba también al reutilizarlo.
- Por defecto: 10 solicitudes LLM por workspace/día UTC, 2 por ejecución en toda su vida, 100 000 tokens reservados por día y 60 s entre nuevas solicitudes externas. Los fallos y cancelaciones consumen cuota; las consultas/caché no hacen otra llamada. Reglas: hasta 100 creaciones nuevas al día por workspace.
- Hasta un reintento para 429/502/503/529, tras una pausa de 1 s. Los demás errores, respuestas truncadas/inválidas y timeouts no se reintentan. Cada intento tiene timeout; hay además un plazo total del trabajo. Cancelar interrumpe la espera, aunque una petición ya enviada puede generar cargos.
- El servidor reserva `(entrada_estimada + salida_máxima) × intentos_máximos`. La entrada se estima con bytes UTF-8 del contexto, esquema e instrucciones más 1024 de margen; **no es el tokenizer del proveedor**. Los tokens reales de la última respuesta válida se guardan por separado cuando se comunican.
- Si configuras ambas tarifas `BLACKBOX_AI_INPUT_USD_PER_MILLION` y `BLACKBOX_AI_OUTPUT_USD_PER_MILLION`, la reserva en USD es `(entrada_estimada × tarifa_entrada + salida_máxima × tarifa_salida) × intentos_máximos / 1 000 000`, redondeada hacia arriba a 8 decimales. No se incorporan tarifas supuestas ni actualizaciones automáticas de precios.
- `BLACKBOX_AI_DAILY_BUDGET_USD` es opcional y exige ambas tarifas. La suma diaria de reservas se compara antes de llamar. Sin tarifas, el coste monetario es desconocido; siguen vigentes cuotas de tokens/solicitudes. Son controles locales conservadores, no una factura ni un límite certificado por el proveedor; configura también el presupuesto de tu cuenta externa.
- El cierre cancela trabajos; tras un reinicio, pending/running pasan a failed. No hay reenvío automático de evidencias ni reintentos al arrancar. Los resultados originales, informes y CRUD siguen disponibles si falla la inteligencia.

| Endpoint bajo `/api/v1` | Función |
| --- | --- |
| `GET /ai/capabilities` | Disponibilidad, proveedor/modelo y límites públicos, sin claves |
| `POST /runs/{run_id}/ai-analysis` | Crear trabajo: 202 nuevo, 200 si se reutiliza |
| `GET /runs/{run_id}/ai-analysis?limit=5&offset=0` | Histórico paginado; máximo 20 |
| `GET /ai-analyses/{analysis_id}` | Resultado estructurado y evidencias usadas |
| `POST /ai-analyses/{analysis_id}/cancel` | Cancelar interpretación activa, 202 |

Ejemplo de cuerpo sin envío externo:

```json
{"mode":"rules","max_findings":5,"include_history":true}
```

Para LLM se requiere `mode="llm"`, `authorize_external=true`, `consent_provider` y `consent_model` iguales a `/ai/capabilities`. No hay un campo de prompt libre. HTTP 403 indica falta de autorización; 404, recurso inexistente o ajeno; 409, ejecución no finalizada, contención o configuración pendiente/cambiada; 422, parámetros inválidos; 429, cuota o presupuesto local; 503, servicio no disponible. Los errores del proveedor se guardan como un estado failed con mensaje genérico, sin exponer su respuesta o la clave.

### Validación y límites de las conclusiones

Las instrucciones del sistema están separadas del JSON de evidencias no confiables. Se ponen en cuarentena patrones conocidos de instrucciones/comandos incrustados, se valida el JSON con Pydantic estricto y se comprueban referencias, compatibilidad de plantillas, URLs y códigos HTTP citados. Se rechazan campos de código libre, comandos y referencias a archivos de código no suministrados. Estas defensas no demuestran inmunidad completa a prompt injection ni fidelidad semántica de toda frase generada.

Todos los resultados generativos son interpretaciones, nunca hechos nuevos certificados. Las hipótesis permanecen sin confirmar, aunque el modelo indique confianza alta. No se almacena cadena de pensamiento ni prompts/respuestas brutos. Una plantilla HTTP solo comprueba la respuesta inicial; las de JS/consola observan la navegación, no todos los flujos posteriores. Si falta una URL utilizable, no se inventa un test. La utilidad diagnóstica y las relaciones del modelo requieren revisión humana.

Los tests emplean fixtures y transportes/proveedores controlados, sin llamadas comerciales reales. **No se ha verificado una llamada real con una cuenta y modelo comercial**; la configuración y calidad de ese modelo deben validarse después de autorizar el envío. Consulta [la verificación de fase 5](docs/verification-phase-5.md) para los resultados concretos.

**La fase 6 no se ha iniciado.**
