# Verificación - Fase 4: informes, analítica y regresiones

Fecha: 9 de noviembre de 2026. Trabajo sobre la implementación existente, en `feature/phase-4-reporting`. No se hace merge automático a `main` ni se inicia la fase 5.

## Cambios

| Componente | Archivos |
| --- | --- |
| Informes, redacción, renderizado, comparación y agregaciones | `backend/app/services/reporting.py` |
| Endpoints y exclusión de generaciones concurrentes | `backend/app/api/reporting.py`, `backend/app/main.py` |
| Protección frente a enlaces/junctions entre evidencias | `backend/app/testing/evidence.py` |
| Dependencias fijadas | `backend/requirements*.txt`, `backend/requirements*.lock` |
| Pruebas de API y servicio | `backend/tests/test_reporting.py` |
| Descargas y resumen de una ejecución | `frontend/src/components/ReportPanel.tsx`, `pages/RunDetail.tsx` |
| Comparación y selección paginada | `frontend/src/components/ComparisonPanel.tsx`, `pages/Analyses.tsx` |
| Gráficas y agregados de proyecto | `frontend/src/components/ProjectAnalytics.tsx`, `AnalyticsChart.tsx`, `pages/ProjectDetail.tsx` |
| Contratos, cliente y estilo | `frontend/src/types/reporting.ts`, `services/reporting.ts`, `services/api.ts`, `reporting.css` |
| Navegación e integración | `frontend/src/App.tsx`, `main.tsx`, `components/Layout.tsx` |
| Flujo real de navegador | `backend/tests/test_browser_ui.py` |
| Documentación | `README.md`, `docs/architecture.md`, este registro |

No se modifican los modelos, las migraciones ni el alcance de navegación del motor. Se reutiliza el esquema existente. Los archivos ajenos `lambda_insert_incendio.py` y `best.pt`, bases, entornos, navegadores y evidencias no se publican.

## Resultados observados

Entorno: Windows, Python 3.12.16, Node 24.22.2, Playwright 1.64.1, Chromium headless 156.0.8078.4. ReportLab 4.5.1 y Pillow 13.0.0 para generación; pypdf 6.21.4 para comprobación de PDF. Ninguna dependencia frontend nueva.

| Comprobación | Resultado real |
| --- | --- |
| Suite completa `python -m pytest` | **158 passed**, sin avisos, 58,97 s en esta ejecución |
| Regresión de fases anteriores | Conservados y superados los 118 casos existentes |
| Nuevas pruebas | 39 casos de informes/API/servicio y 1 flujo React con navegador real |
| TypeScript + Vite `npm.cmd run build` | Correcto; sin avisos de chunks grandes |
| Integración del cliente `npm.cmd run test:integration` | CRUD, validación, 404, sincronización de dashboard y error de conexión correctos |
| `npm.cmd ls --depth=0` | Árbol de dependencias directas válido |
| `python -m alembic check` | No new upgrade operations detected |
| `python -m pip check` | No broken requirements found |
| `uv pip check` | Dependencias instaladas compatibles |
| `PRAGMA foreign_key_check` | Sin inconsistencias; head `c39d87a4e620` |
| Ruff de los nuevos módulos Python y test de informes | Sin errores |
| `git diff --check` | Sin errores de espacios o parches |

El build generó un JS principal de 335,47 kB (103,14 kB gzip) y un chunk compartido de gráficas de 359,78 kB, cargado de forma diferida. Estos son tamaños de artefactos, no mediciones de RAM. No se ha medido consumo de memoria ni CPU, por lo que no se publican estimaciones de recursos.

## Casos cubiertos

- HTML autónomo válido mediante parser: sin scripts, iframes, objetos, enlaces externos de recursos ni atributos de evento. Texto malicioso escapado.
- PDF legible con pypdf, varias páginas, cabeceras/paginación, sin anotaciones ni OpenAction. Caracteres españoles, sustitución de glifos no soportados y ausencia de incidencias comprobadas.
- JSON con datos persistidos, resumen SQL y referencias sin rutas internas; CSV con BOM, citas y neutralización de fórmulas `=`, `+`, `-`, `@`, espacios, tabuladores y saltos iniciales. CSV vacío conserva metadatos y ceros.
- Redacción de secretos históricos en título/descripción/reproducción/URL y exportaciones, incluyendo credenciales entre comillas, correo, consultas URL y rutas locales.
- 404 en todas las descargas para otro workspace o UUID inexistente; 422 en UUID inválido. Comparación entre proyectos y workspace inconsistente rechazados; analítica excluye esas ejecuciones.
- Evidencia asociada a otro análisis, traversal, PNG corrupto, archivo excesivo y presupuesto de bytes/capturas comprobados. El test de symlink se ejerce solo si Windows permite crearlo; la validación de rutas se mantiene en el código y los casos de traversal son obligatorios.
- NEW, RESOLVED, PERSISTENT y UNCONFIRMED; histórico sin escrituras, duplicados agrupados, misma huella pese a UUID/fecha/duración variables, distinto código HTTP conservado.
- Cancelación y fallo en base o destino nunca afirman resolución. Páginas no revisitadas, distintos límites o detalles truncados dejan ausencias sin confirmar. Ejecuciones activas y comparación consigo misma rechazadas.
- Históricos sin URL de destino muestran «Destino no registrado»; no heredan la URL actual de un proyecto editado ni prueban resoluciones.
- Totales, medias, severidades/tipos y paginación SQL. Proyecto vacío devuelve `null` para media/regresión, sin datos de ejemplo. Los contadores HTTP siguen correctos incluso si su tipo queda fuera del desglose de 50 grupos.
- Informes con más de 200 incidencias o 20 páginas comunican omisiones y mantienen totales reales. Límite de respuesta 413 y semáforo de generación 409 comprobados; el aislamiento se evalúa antes de comunicar contención.

## Navegador y revisión visual

La prueba nueva arranca FastAPI/Vite propios en loopback con SQLite temporal. Crea un proyecto de demo y ejecuta dos análisis reales de una página. El navegador de QA solo admite solicitudes a esos servidores; el motor conserva su política independiente de demo interceptada.

Se verificó desde React:

1. Resumen por severidad de una ejecución finalizada.
2. Cuatro descargas reales mediante botones y eventos de descarga de Chromium: HTML, PDF, JSON y CSV, con contenido no vacío y nombre correcto.
3. PNG incrustado opcional, PDF de tres páginas y JSON con la página y sus incidencias guardadas.
4. Gráfica histórica y cifras reales de dos ejecuciones.
5. Selección automática de la pareja temporal dentro del proyecto, comparación y filtros NEW/PERSISTENT.
6. Escritorio 1440×1080 y móvil 390×844 sin desbordamiento horizontal en resultados y comparación.
7. Apertura del HTML descargado desde disco, en otro contexto offline: resumen visible, PNG cargado con ancho 1280 y cero solicitudes HTTP/HTTPS.
8. Ausencia de errores JavaScript de la interfaz y de solicitudes a destinos ajenos en el contexto de QA.

La prueba previa de fase 3 también pasa: siete páginas, filtros, evidencias, menú móvil y cancelación. Se inspeccionaron las capturas de QA de resultados, analítica, comparación y HTML offline. El PDF descargado se renderizó con Poppler 26.09.0 y se revisaron visualmente sus tres páginas: portada, tabla/resumen con incidencias y evidencia; sin cortes, solapamientos o glifos rotos en esos datos.

Artefactos locales ignorados: `.tools/qa/phase4-report.{html,pdf,json,csv}`, `phase4-pdf-{1,2,3}.png`, `phase4-run-{desktop,mobile}.png`, `phase4-comparison-{desktop,mobile}.png`, `phase4-analytics-desktop.png`, `phase4-offline-html.png`. Poppler se descargó solo para QA y no es requisito de instalación de BLACKBOX AI.

La primera suite completa detectó un selector exacto sin etiqueta accesible explícita y una prueba que asumía el orden de dos incidencias creadas casi al mismo tiempo. Se añadió la etiqueta y se identificó la fila por UUID; los casos afectados y la suite final pasaron después. Durante la implementación también se corrigió una expresión de redacción que confundía un esquema HTTP con una ruta Windows; hay una regresión específica para mantener distintas las URLs HTTP.

## Ejecución

Desde la raíz, con los runtimes portables de esta copia:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_reporting.py
Set-Location backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pip check
Set-Location ..
$env:PATH = "$(Join-Path (Get-Location).Path '.tools\node');$env:PATH"
Set-Location frontend
npm.cmd run build
npm.cmd run test:integration
npm.cmd ls --depth=0
```

La instalación habitual se mantiene en el README; hay que instalar el lock actualizado en el entorno Python existente. Los servidores y datos de prueba son temporales. No se ha realizado un análisis de ningún sitio público.

Al finalizar había un backend previo en el puerto 8000, sin ejecuciones activas ni datos registrados y con la demo deshabilitada. Su OpenAPI aún no incluía las rutas de fase 4. La revisión automática del entorno bloqueó el intento de reinicio, sin motivo detallado; el comando no llegó a ejecutarse. **Es necesario reiniciar ese proceso para cargar la nueva versión.** Esto no afecta al resultado de las pruebas: los flujos de fase 4 se verificaron con procesos propios temporales que sí cargaron el código actualizado.

## Límites conservados

La comparación es heurística, agrupada y de cobertura limitada; RESOLVED no certifica corrección y NEW no prueba causalidad temporal. JSON/CSV no incrustan imágenes. Los detalles, grupos de tipos y capturas están acotados y las omisiones se comunican. La fuente del PDF tiene un conjunto limitado de glifos. La redacción por patrones no sustituye una revisión de privacidad de capturas o texto libre. El workspace local no es autenticación multiusuario. No se incorpora IA ni navegación remota, ni infraestructura distribuida. La fase 5 queda pendiente de confirmación.
