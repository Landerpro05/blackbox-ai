# Fase 3 — motor real con demostración controlada

Fecha: 9 de noviembre de 2026 (Europe/Madrid).

## Alcance entregado

Se ha elegido la alternativa autorizada en el encargo: analizar exclusivamente una aplicación de demostración local integrada. Chromium ejecuta HTML/JS real, detecta incidencias y genera capturas. Los resultados no se simulan ni se insertan por adelantado.

La navegación por Internet y hacia otros servicios locales permanece deshabilitada. Esta entrega no constituye un crawler remoto ni un sandbox SSRF general. No se ha iniciado la fase 4 ni se ha integrado IA.

## Cambios por componente

| Componente | Archivos principales |
| --- | --- |
| Modelos y migración | `backend/app/models/entities.py`, `models/__init__.py`, `alembic/versions/c39d87a4e620_testing_engine.py` |
| Coordinación y exclusión | `backend/app/services/run_manager.py`, `worker_lock.py`, `backend/app/core/errors.py` |
| Motor y política | `backend/app/testing/engine.py`, `demo.py`, `policy.py`, `evidence.py` |
| API y persistencia | `backend/app/api/runs.py`, `repositories/runs.py`, `schemas/runs.py` |
| Integración con la base existente | `backend/app/main.py`, `core/config.py`, `api/projects.py`, `repositories/projects.py` |
| Instalación y arranque | `backend/requirements.txt`, ambos `.lock`, `.env.example`, `pyproject.toml`, `scripts/start-backend.ps1`, `.gitignore` |
| Interfaz de proyecto | `frontend/src/components/RunStartPanel.tsx`, `RunHistory.tsx`, `DemoProject.tsx`, `pages/ProjectDetail.tsx`, `Projects.tsx` |
| Historial y resultados | `frontend/src/pages/Analyses.tsx`, `RunDetail.tsx`, `frontend/src/runs.css` |
| Cliente y navegación | `frontend/src/services/runs.ts`, `api.ts`, `hooks/usePollingResource.ts`, `types/api.ts`, `App.tsx`, `main.tsx`, `components/Layout.tsx`, `pages/Dashboard.tsx`, `Settings.tsx` |
| Verificación | `backend/tests/test_engine.py`, `test_browser_ui.py` |

`Run` e `Issue` se amplían y se reutilizan como `TestRun`/`TestIssue`; no se crean tablas duplicadas ni se cambia el enum histórico de estado. Se añade `TestPage`. Las rutas existentes y los 67 tests anteriores se conservan.

No se modifican los archivos ajenos `lambda_insert_incendio.py` ni `best.pt`. Los navegadores, bases, evidencias y capturas de QA no se publican en Git.

## Entorno y resultados reales

- Windows con Python 3.12.16 y Node 24.22.2.
- Playwright Python 1.64.1 y Chrome Headless Shell 156.0.8078.4.
- Caché de navegador del workspace: `.tools/browsers`; sin GPU ni contenedores.

| Comprobación ejecutada | Resultado observado |
| --- | --- |
| `python -m pytest` | **118 passed**, sin avisos; incluye los 67 casos anteriores |
| Chromium sobre la demo | HTTP 404/500, JavaScript, consola, enlaces rotos, etiquetas de formulario, redirección y subrecursos bloqueados registrados |
| Límites de recorrido | Máximo de páginas, profundidad y presupuesto comprobados con Chromium real |
| Timeout y cancelación | Comprobados con motor real y dobles de prueba; navegador desconectado al finalizar |
| Error al persistir una página | Estado failed, navegador cerrado y PNG no asociado eliminado |
| Aislamiento | Acceso, incidencias, páginas, cancelación y PNG de otro workspace devuelven 404 |
| Concurrencia | Segundo análisis rechazado; edición/borrado del proyecto activo rechazados; slot SQLite y bloqueo de proceso comprobados |
| Reinicio | Pendientes/en curso pasan a failed, con y sin demo habilitada; no se reanudan |
| Consentimiento | Solo JSON `true`; se rechazan false, 1, strings y valores nulos |
| `npm.cmd run build` | TypeScript y Vite correctos, sin aviso de chunks grandes |
| `npm.cmd run test:integration` | Cliente CRUD existente contra FastAPI temporal correcto |
| `python -m alembic check` | Sin diferencias de esquema pendientes |
| `python -m pip check` | Sin dependencias incompatibles |
| `PRAGMA foreign_key_check` | Sin inconsistencias en la base local |

La migración se aplicó a la base de desarrollo después de crear un backup consistente en `.tools/backups/before-phase3-*.db`. Se conservaron los recuentos: 0 proyectos, 0 ejecuciones y 0 incidencias. Las pruebas de migración sí insertan registros anteriores en bases temporales, incluyendo workspace distinto y una incidencia existente, y comprueban la conservación y el relleno correcto de los nuevos campos.

## Prueba de React en navegador

`test_browser_ui.py` arranca FastAPI y Vite en puertos locales libres con una SQLite temporal y demo habilitada. El navegador de QA solo permite solicitudes a esos dos servidores propios. El Chromium del motor mantiene su política separada de demo integrada.

La prueba completó estos pasos:

1. Crear un proyecto mediante el botón de demostración de React.
2. Configurar 7 páginas y un timeout de navegación de 1 segundo.
3. Marcar autorización y pulsar Iniciar análisis.
4. Esperar estado Completado y consultar las 7 páginas registradas, sus incidencias y capturas.
5. Filtrar por severidad alta y comprobar que todas las tarjetas visibles son altas.
6. Cargar un PNG de evidencia real; ancho observado de 1280 píxeles.
7. Revisar viewport de escritorio 1440×1080 y móvil 390×844, sin desbordamiento horizontal; abrir/cerrar menú móvil.
8. Editar la URL del proyecto a la ruta lenta integrada, iniciar otra ejecución y cancelarla desde React; esperar estado Cancelado.
9. Comprobar que no hubo errores JavaScript de la interfaz ni solicitudes a otros destinos en el navegador de QA.

Se inspeccionaron las capturas `.tools/qa/phase3-results-desktop.png`, `phase3-results-mobile.png` y `phase3-demo-form.png`. La evidencia de formulario muestra máscaras sobre email, contraseña y el bloque sensible de la demo. La revisión es específica de esas pantallas y viewports, no una auditoría visual de todos los dispositivos.

Durante la verificación inicial se corrigieron dos fallos observados: la reutilización de pestañas tras navegaciones bloqueadas y la lectura de un archivo ya bloqueado en Windows. Los tests de regresión y la suite final pasaron después de corregirlos.

## Seguridad comprobada y límites

- Origen virtual fijo; el catálogo de respuestas es código del repositorio. No se sirve contenido aportado por usuarios.
- Cada solicitud del contexto se cumple desde el catálogo o se aborta. No hay peticiones HTTP de upstream ni DNS de destino.
- Location se valida antes de seguir una redirección; la demo con metadatos cloud se bloquea sin contactar el endpoint.
- Se bloquean subrecursos externos, localhost/privadas/metadatos como destinos, iframes, WebSockets y métodos de escritura. Service Workers y descargas deshabilitados.
- El ensayo de rebinding proporciona un resolver cambiante y comprueba que nunca se invoca: los dominios remotos son rechazados. Esto no verifica un sistema de fijación DNS/IP para Internet, que no se ha implementado.
- No se rellenan ni envían formularios. No hay compras, cambios de datos ni comandos del sistema derivados de la página.
- Mensajes y URLs se redactan antes de guardar; no se conservan cuerpos, cookies ni cabeceras. Máscaras de capturas comprobadas para la demo, sin prometer detección universal de secretos en contenido ajeno.
- Un contexto y una pestaña de análisis a la vez; se cierra una pestaña fallida antes de crear su reemplazo. El navegador de QA de la interfaz es adicional únicamente durante su prueba automatizada, igual que el navegador del usuario al usar la aplicación.

La configuración de proxy sin salida y resolución deshabilitada es una defensa adicional, no un firewall del sistema operativo. No se acepta navegación remota arbitraria. Los topes de trabajo pueden ir seguidos de un breve tiempo de limpieza; solicitudes ya emitidas que exceden el presupuesto se abortan y pueden figurar en el contador observado.

La aplicación sigue sin autenticación, con un ámbito local compartido. Se exige un único proceso de API por SQLite; no es una cola distribuida. Si la base deja de estar disponible y no se puede guardar el estado final, la recuperación al reiniciar es la vía de reconciliación. Una limpieza de evidencias que falle por permisos de disco puede requerir intervención administrativa.

## Probar manualmente

Desde la raíz, en dos terminales distintas:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-backend.ps1 -Demo
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-frontend.ps1
```

Abre `http://127.0.0.1:5173/projects`, crea el proyecto de demostración, autoriza e inicia. La instalación de Chromium y todos los comandos desde cero están en el README. Para la demo en Windows no uses `--reload` ni múltiples workers.

Los procesos de verificación se detuvieron al terminar. La base de desarrollo queda migrada y sin resultados de demostración preinsertados. La fase 4 y la IA quedan pendientes de autorización posterior.
