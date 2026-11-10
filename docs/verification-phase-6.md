# Verificación — Fase 6

Fecha: **10 de noviembre de 2026**, zona Europe/Madrid. Rama `feature/phase-6-local-testing-ci`, creada exactamente desde `236937beca23c1158ee1b331ef8601f160552d8e` de `feature/phase-5-ai-intelligence`. No se ha hecho merge ni se ha iniciado la Fase 7.

## Resultado local comprobado

Entorno: Windows, Python 3.12.16, Node 24.22.2, Playwright 1.64.1 y Chromium headless instalado en la caché portable del workspace. SQLite temporal para tests, proveedor LLM deshabilitado y servidores de prueba propios en loopback. Las verificaciones no analizan aplicaciones públicas ni contactan APIs comerciales de IA.

| Comprobación | Resultado observado |
| --- | --- |
| `python -m pytest backend/tests --junitxml=.tools/qa/phase6-pytest.xml` | **282 passed en 228,81 s**, sin fallos ni skips |
| GitHub Actions final en Ubuntu 24.04 | **282 passed en 99,36 s**, workflow completo success |
| Regresión de fases anteriores | Los 216 casos previos siguen incluidos; 66 casos nuevos |
| Revisión posterior de UI y configuración deshabilitada | 4 passed, 108 deselected en 16,79 s |
| UI tras vincular consentimiento al origen y comprobar una edición concurrente mediante API real | 1 passed, 3 deselected en 18,97 s |
| `npm --prefix frontend run test:integration` | PASS CRUD real, validación, 404, sincronización dashboard y backend no disponible |
| `npm --prefix frontend run build` | TypeScript y Vite correctos, 2018 módulos transformados |
| `uv pip check --python backend/.venv/Scripts/python.exe` | 37 paquetes compatibles |
| Instalación con hashes en modo dry-run | 36 dependencias fijadas; no requiere cambios |
| Ruff sobre módulos y pruebas nuevos del laboratorio | All checks passed; no se afirma un lint completo de los archivos heredados |
| `alembic upgrade head` y `alembic check` sobre la base local | `e62f1b809a73`, sin operaciones pendientes |
| CLI demo standalone, base independiente y JSON | Código 0, completed, 4 pass / 0 fail / 0 error |
| CLI con suites persistidas | Códigos reales 1 (aserción), 2 (timeout del motor) y 3 (timeout CLI con cancelación), verificados en subprocess |
| Salud API y frontend local | API healthy y SQLite connected; `/lab` HTTP 200 |

El pase completo de Windows precede al último ajuste del consentimiento UI, que se comprobó después con su prueba específica y build local; el workflow completo de Linux verifica el commit final de código. El primer pase completo encontró una prueba antigua que cargaba el mapper actual de Run después de bajar a Fase 4. Se corrigió para consultar explícitamente la columna histórica Run.id; sigue verificando que Run e Issue sobreviven al downgrade y que la recuperación de IA funciona tras volver a head. La prueba nueva de migración conserva además Run, Issue y AIAnalysis durante el downgrade/upgrade de Fase 6. No se eliminó ninguna prueba anterior.

La revisión de las aserciones detectó dos problemas del motor que se corrigieron antes del pase final: una redirección rechazada se podía presentar como una respuesta HTTP comprobable y un caso podía figurar pass pese a agotar el presupuesto. Ambos producen ahora error de caso y ejecución failed. La validación local también se realiza antes de la normalización HttpUrl para rechazar IPs alternativas y puertos no canónicos, tanto al crear como al editar un entorno.

## Cobertura nueva

- Orígenes: HTTP/HTTPS, puerto explícito, loopback literal, origen exacto y modo deshabilitado por defecto. Se rechazan DNS/localhost, redes privadas adicionales, metadata IP, IPs alternativas, IPv4 mapeada, credenciales, consultas, fragmentos, rutas codificadas, métodos distintos de GET y otros puertos, incluso si otro origen está en la lista global.
- Broker: cuerpo alterado, estado incorrecto, Location inesperado, Content-Type incorrecto, límite de tamaño, rutas privadas rechazadas antes de I/O y ausencia de hostname susceptible de rebinding. El transporte no sigue redirects ni usa proxies del entorno.
- Aplicación HTTP real: fixture con ThreadingHTTPServer y catálogo del proyecto. Chromium recibe respuestas verificadas del servidor local; no se simulan los resultados de las aserciones.
- Siete tipos declarativos ejecutados en una suite real: HTTP, título, elemento, texto, JavaScript, enlaces internos y navegación. Resultado esperado y observado: 7 pass y 2 fail para nueve casos habilitados; un caso deshabilitado no se ejecuta.
- Seguridad declarativa: rechazo de Python/JavaScript libre, propiedades extra, XPath, selectores complejos, rutas peligrosas, booleanos usados como enteros, rangos HTTP invertidos y textos requeridos vacíos.
- Persistencia: CRUD de entornos/suites/casos, orden/activación, posiciones duplicadas, máximo 20 casos, presupuesto de páginas, límites de entorno, paginación, recursos inexistentes, proyecto incompatible y aislamiento por workspace.
- Histórico: captura de entorno y definición al iniciar; editar el entorno y borrar la suite conservan destino y resultados originales. Las evidencias usan la ruta protegida existente.
- Ejecución: límites de solicitudes, timeout de navegación/global, redirects y subrecursos bloqueados, un solo slot activo, cancelación, pendientes skipped y liberación para operaciones posteriores.
- Contenido no verificado: el servidor devuelve HTML con script añadido; el broker lo rechaza y la ejecución queda failed/error. La marca del script no aparece en los eventos ejecutados del navegador.
- IA: diagnóstico por reglas de los fallos de una suite real; importación explícita con evidencia del mismo proyecto, conversión a plantilla declarativa, código ignorado y caso guardado deshabilitado.
- CLI: demo real con cuatro casos, consentimiento obligatorio, suite existente, JSON persistido, progreso, códigos 0/1/2/3 y cancelación al superar el tiempo de espera.
- React: crear entorno demo, autorizar comprobación, crear suite, añadir dos títulos (uno correcto y otro incorrecto), exigir consentimiento de ejecución, consultar resultados, filtrar fallos, abrir referencias de evidencia, conservar historial y consultar instrucciones CI sin estado ficticio. Viewports 1440×1080 y 390×844; sin errores JS de la aplicación y sin desbordamiento horizontal comprobado. La edición de un origen desde otro cliente, usando la API real, invalida la casilla de consentimiento al refrescar los datos: se prueban dos orígenes configurados permitidos sin navegar hacia ellos.

## Archivos y arquitectura

| Área | Archivos principales |
| --- | --- |
| Política y servidor controlado | `backend/app/testing/local_policy.py`, `backend/app/lab_server.py`, `backend/app/core/config.py`, `backend/.env.example` |
| Persistencia | `backend/app/models/lab.py`, `models/entities.py`, `models/__init__.py`, revisión `e62f1b809a73` |
| Contrato y API | `backend/app/schemas/lab.py`, `schemas/runs.py`, `app/api/lab.py`, `app/services/lab.py`, `app/main.py` |
| Motor compartido | `testing/engine.py`, `testing/declarative.py`, `services/run_manager.py`, `repositories/runs.py`, `services/ai_rules.py` |
| Interfaz | `frontend/src/pages/TestingLab.tsx`, `components/SuiteResults.tsx`, `services/lab.ts`, `lab.css`; integración en Router, Layout, RunDetail, Settings y tipos existentes |
| CLI y CI | `backend/app/cli.py`, `.github/workflows/ci.yml`, `backend/requirements-dev.lock` con hashes, limpieza POSIX en `frontend/scripts/verify-projects-client.mjs` |
| Verificación | `backend/tests/test_lab.py`, `test_cli_suites.py`, `test_browser_ui.py`, ajuste de consulta histórica en `test_intelligence.py` |
| Documentación | `README.md`, `docs/architecture.md`, este registro |

Se reutilizan RunManager, DemoEngine, RunWriter, WorkerLock, EvidenceStore, lifespan FastAPI y rutas anteriores de cancelación, reporting e inteligencia. No se incorporan colas, contenedores, bases adicionales, modelos locales de IA ni servicios pesados. No se han modificado `lambda_insert_incendio.py` ni `best.pt`.

## Datos y evidencias locales

Antes de migrar se creó una copia consistente usando la API backup de SQLite: `backend/data/before-phase6-20261110T173814Z.db`. La base estaba en revisión `d51e09a3b842`. Los recuentos antes/después permanecen iguales: 0 proyectos, 0 ejecuciones, 0 incidencias, 0 páginas y 0 análisis de IA. La copia, la base y los lockfiles de proceso están ignorados por Git. La prueba automatizada de conservación usa datos no vacíos, incluyendo incidencias y resultados IA.

Los resultados de QA quedan en `.tools/qa/phase6-pytest.xml`, `phase6-cli-results.json` y las capturas `phase6-lab-desktop.png`, `phase6-lab-mobile.png`, `phase6-results-mobile.png`. El JSON CLI contiene únicamente resultados de su demo sintética en una base independiente. Estos archivos no se suben al repositorio. Las capturas se revisan visualmente; las pruebas esperan la transición del menú móvil para no capturar un estado intermedio.

Aplicación local iniciada y comprobada: API `http://127.0.0.1:8000`, frontend `http://127.0.0.1:5173/lab`. Ambos solo escuchan en 127.0.0.1. Demo habilitada en ese proceso; Local Testing Lab deshabilitado, lista vacía, navegación arbitraria/remota deshabilitada. Las pruebas del catálogo local usan configuración y servidores temporales, sin habilitar ese modo en la instancia del usuario.

## GitHub Actions

El workflow usa permisos contents:read, checkout sin credenciales persistidas, acciones fijadas por SHA, runtimes exactos, dependencias fijadas y hashes Python, caché de descargas pip/npm, timeout de 20 minutos y cancelación de ejecuciones anteriores por ref. Solo un job ejecuta las etapas secuencialmente. Incluye pull_request; no usa pull_request_target, no necesita secretos, no hace push/merge ni analiza sitios externos. El modo comercial de IA está deshabilitado y su clave vacía.

La primera ejecución real, [42866851770](https://github.com/Landerpro05/blackbox-ai/actions/runs/42866851770), instaló runtimes/dependencias/Chromium y migró correctamente, pero terminó con 279 passed y 3 failed porque el workflow activaba globalmente la demo y contradecía las pruebas de configuración deshabilitada. Se corrigió el workflow: mantiene demo false para tests y la activa exclusivamente en el paso CLI. No se cambiaron las expectativas de esas tres pruebas.

La segunda ejecución, [42867412478](https://github.com/Landerpro05/blackbox-ai/actions/runs/42867412478), superó **282 pruebas en 104,99 s**, pero el script de integración terminó con código 13 después de imprimir sus PASS. La limpieza intentaba esperar por segunda vez el evento exit de un proceso ya terminado por señal en Linux. Se hizo idempotente comprobando también `signalCode`, según el [contrato de ChildProcess de Node](https://nodejs.org/api/child_process.html#subprocesssignalcode), sin modificar las aserciones funcionales.

La tercera ejecución, [42868228652](https://github.com/Landerpro05/blackbox-ai/actions/runs/42868228652), comprobó correctamente todo el flujo sobre `3cf0ecd54e21b7c8a94ac020978a19ace7c1b63a`: **282 passed en 98,69 s**, migraciones sincronizadas, dependencias compatibles, integración cliente correcta, build frontend correcto, CLI completed con cuatro casos pass y artifacts cargados. Se observó success en todas las etapas, incluidos los pasos finales.

La ejecución final, [42869082791](https://github.com/Landerpro05/blackbox-ai/actions/runs/42869082791), sobre **`24a42534c12abc16f472750b6dccb6c30975fba9`**, terminó **completed / success**. Incluye el último ajuste que vincula el consentimiento al origen exacto y la regresión de edición concurrente. Se observó success en todas las etapas: backend/Chromium, integración del cliente, build, migraciones, dependencias y CLI. El artifact [verification-42869082791](https://github.com/Landerpro05/blackbox-ai/actions/runs/42869082791/artifacts/13787154959) está disponible con retención de 7 días.

El commit posterior contiene únicamente esta documentación, README y arquitectura; conserva el mismo código verificado. Los push que solo cambian Markdown no repiten CI; los Pull Requests sí están cubiertos por el trigger general. No se ha creado ni fusionado ningún PR. La UI no consulta GitHub y conserva su estado etiquetado como sin consultar, aunque la comprobación manual de esta entrega sí ha observado el resultado remoto real.

## Límites y pendientes

- **Solo catálogo del proyecto:** no se habilitan aplicaciones locales arbitrarias, staging remoto ni Internet. El contenido local debe coincidir con la versión del repositorio. No existe una frontera de aislamiento de red/sistema operativo certificada frente a aplicaciones maliciosas; Playwright por sí solo no la proporciona.
- Cada ejecución requiere consentimiento para su origen exacto y respeta el opt-in/lista del servidor. Guardar un entorno no accede a su URL. No se almacenan credenciales de aplicaciones.
- El servidor incluido es HTTP IPv4 loopback; HTTPS requiere certificado válido y réplica del catálogo, sin excepciones TLS. IPv6 literal se valida, pero el lanzador incluido no crea un servidor IPv6.
- Workspace local no es autenticación multiusuario. API/frontend permanecen en loopback, sin despliegue público.
- LLM real comercial no probado ni usado; se mantienen las evaluaciones controladas de Fase 5, consentimiento independiente y cuotas.
- Sin consulta automática de GitHub en la UI. El trigger pull_request está configurado; no se ha creado ni fusionado un PR para esta entrega.
- No se han medido formalmente RAM/CPU; no se publican cifras de consumo ni garantías basadas en la GPU. El motor usa Chromium sin GPU y los límites anteriores.
- No se ha iniciado la Fase 7.
