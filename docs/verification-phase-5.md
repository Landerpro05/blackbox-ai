# Verificación - Fase 5: AI Intelligence Engine

Fecha: 9 de noviembre de 2026. Rama `feature/phase-5-ai-intelligence`, creada desde `18cd80e`, último commit de `feature/phase-4-reporting`. Se mantienen las fases previas, sin merge automático ni cambios en los archivos ajenos del workspace. La fase 6 no se inicia.

## Entrega y archivos

| Área | Archivos principales |
| --- | --- |
| Modelo y migración | `backend/app/models/intelligence.py`, `models/__init__.py`, `alembic/versions/d51e09a3b842_ai_intelligence.py` |
| Contratos y configuración | `backend/app/schemas/intelligence.py`, `core/config.py`, `backend/.env.example` |
| Evidencias y agrupación | `backend/app/services/ai_evidence.py`, reutilizando redacción, resumen, comparación y huellas de fase 4 |
| Reglas y plantillas seguras | `backend/app/services/ai_rules.py` |
| Interfaz de proveedor y adaptador Anthropic | `backend/app/services/ai_provider.py`, locks y requirements |
| Tareas, caché, cuotas y cancelación | `backend/app/services/ai_manager.py` |
| API e integración de ciclo de vida | `backend/app/api/intelligence.py`, `main.py`, `repositories/projects.py` |
| Interfaz | `AIIntelligencePanel.tsx`, `AIAnalysisResult.tsx`, `AIAnalysisDetail.tsx`, `RunDetail.tsx`, `Settings.tsx`, `Layout.tsx`, rutas, estilos y cliente/tipos de inteligencia |
| Evaluación | `backend/tests/fixtures/ai_evaluation_cases.json`, `test_intelligence.py`, `test_browser_ui.py` |
| Documentación | README, arquitectura y este registro |

El modo rules es determinista y funciona sin clave. El modo llm utiliza un adaptador real del protocolo Messages con JSON estructurado, configurado desde backend. **No se ha realizado una llamada comercial real con una cuenta/modelo**: las comprobaciones de proveedor usan HTTPX2 MockTransport o un proveedor controlado. Por tanto no se afirma haber evaluado la calidad de un modelo comercial, sus credenciales, disponibilidad o factura.

## Resultados ejecutados

Entorno: Windows, Python 3.12.16, Node 24.22.2, Playwright 1.64.1 y Chromium headless 156.0.8078.4. No hay dependencias frontend nuevas ni SDK/modelo local de IA. HTTPX2 2.16.0, que ya estaba en desarrollo, pasa a producción con las mismas versiones fijadas.

| Comprobación | Resultado |
| --- | --- |
| Suite completa pytest | **216 passed**, sin avisos, 108,71 s en esta ejecución |
| Pruebas específicas de inteligencia | **57 passed**, 11,99 s |
| Casos de fases 1-4 | Los 158 casos anteriores se conservan y pasan dentro de la suite final |
| Flujo nuevo de React en Chromium | Correcto; repetido tras ajuste visual del visor de código |
| `npm.cmd run build` | Correcto: TypeScript y Vite sin errores ni avisos de chunks grandes |
| `npm.cmd run test:integration` | Cliente CRUD, validación, 404, dashboard y error de conexión correctos |
| `npm.cmd ls --depth=0` | Dependencias directas válidas |
| `python -m alembic check` | No new upgrade operations detected |
| `python -m pip check` | No broken requirements found |
| Ruff de nuevos módulos Python, integración y tests de inteligencia | Sin errores |
| `git diff --check` | Sin errores |
| Arranque local actualizado | FastAPI 8000: salud/capacidades correctas; Vite 5173: HTTP 200 |

Build final observado: JS principal de 351,35 kB (107,26 kB gzip), CSS de 38,23 kB y chunk de gráficas compartido de 359,78 kB cargado de forma diferida. Son tamaños de artefactos, no mediciones de RAM/CPU. No se publica un consumo de recursos no medido.

## Evaluaciones reproducibles

El JSON de fixtures contiene nueve casos: HTTP 404, HTTP 500, excepción JavaScript, enlace roto, duplicados de consola, evidencia incompleta, intento de prompt injection, datos con apariencia de secretos y causa desconocida. Solo se insertan en SQLite temporales de pruebas.

Se comprobó en todos ellos:

- Salida estructurada válida; proveedor `rules` y etiqueta «Análisis basado en reglas».
- Agrupación de duplicados por huella y referencias a IDs reales de las evidencias.
- Confianza baja e hipótesis sin confirmar; límites que reconocen ausencia de código/traza suficiente.
- Plantillas compatibles con el tipo de fallo; sin propuesta cuando no hay plantilla o URL utilizable.
- Neutralización del mensaje de inyección conocido antes de introducirlo en el contexto.
- Redacción de tokens, contraseña y correo sintéticos, sin incorporarlos a resultados/instantáneas.
- Análisis del AST de las propuestas para comprobar imports esperados y ausencia de llamadas de evaluación/archivos. **No se ejecuta el código sugerido**.

Estas evaluaciones comprueban reglas y validadores sobre fixtures concretos; no son un benchmark de inteligencia generativa ni una garantía universal de utilidad o resistencia a prompt injection.

## Backend y proveedor

Las pruebas específicas cubren además:

- POST en segundo plano con 202, Location, polling, lectura persistida desde otra sesión SQLite e histórico paginado; caché con 200 sin nueva llamada.
- Rules no invoca el proveedor aunque esté configurado. Capacidades nunca incluyen la clave.
- Consentimiento booleano estricto, proveedor/modelo confirmados, configuración ausente/cambiada, parámetros extra/inválidos y ejecución no finalizada.
- 404 para creación, listado, detalle y cancelación de otro workspace. UUID inexistentes/inválidos y límite de paginación.
- Contexto de hasta 12 000 bytes, 20 incidencias/10 páginas, coherencia de grupos y omisiones, sin imágenes ni rutas de disco. Solo se consulta una comparación histórica relevante.
- IDs inexistentes, plantillas incompatibles, código libre, comandos, URLs nuevas, nombres de archivos inventados, códigos HTTP no observados y declaraciones de causa confirmada rechazados. El informe original sigue disponible después del fallo.
- Cuotas por ejecución/día, cooldown separado, reserva de tokens/coste, presupuesto insuficiente antes de llamar y uso de rules después de agotar cuota LLM. Los fallos también consumen cuota; errores arbitrarios no se filtran al cliente.
- Trabajo lento sin bloquear salud, exclusión de trabajos simultáneos, guardia de borrado del proyecto, cancelación y liberación del slot. Se cubre cancelar antes de que empiece la tarea.
- Contrato Anthropic: HTTPS fijo, cabeceras esperadas, instrucciones separadas de evidencias, esquema JSON compatible sin restricciones no admitidas, sin herramientas/thinking, clave solo en autenticación y uso comunicado validado.
- Reintentos máximos ante 429/503/529; redirecciones no seguidas, respuesta excesiva, truncamiento, tool_use, JSON malformado, contenido nulo y timeout de transporte.
- URLs largas conservadas completas en contexto y código; ruta de un test elegida a partir de la incidencia citada compatible, incluso cuando se citan otros tipos antes.
- Migración reversible que conserva Run/Issue de fase 4, recuperación de una interpretación interrumpida y borrado en cascada de resultados al eliminar un proyecto sin trabajos activos.

La protección de salida es deliberadamente conservadora: puede rechazar una respuesta útil. Las respuestas inválidas no se convierten en supuestas respuestas de un LLM ni se sustituyen silenciosamente por reglas. El usuario puede pedir el modo rules explícitamente.

## Navegador y revisión visual

El nuevo caso de `test_browser_ui.py` inicia FastAPI/Vite en puertos loopback con una base temporal y proveedor externo deshabilitado explícitamente, sin heredar claves del entorno para llamadas. El navegador de QA solo permite los dos servidores propios.

Flujo real comprobado:

1. Crear proyecto de demo y completar una ejecución real de una página.
2. Abrir «Analizar con IA», comprobar modo local por defecto y enviar al backend real.
3. Esperar análisis completado con dos hipótesis y dos propuestas, basadas en los errores JS/consola reales de la demo.
4. Copiar el código al portapapeles y comprobar contenido, normalizando CRLF de Windows en la aserción.
5. Abrir las evidencias citadas, consultar la vista de interpretación y recargar: resultado persistido.
6. Revisar escritorio 1440×1080 y móvil 390×844; sin desbordamiento horizontal. El visor de código tiene desplazamiento propio.
7. Simular únicamente capacidades LLM y un fallo de envío desde el navegador: el botón permanece deshabilitado sin consentimiento, envía nombres confirmados tras marcarlo y muestra el error conservando el análisis por reglas. La petición se intercepta en QA: **no llega a una API comercial**.
8. Confirmar ausencia de errores JavaScript y solicitudes a otros destinos en el navegador de QA.

Se inspeccionaron las tarjetas de hipótesis/código en escritorio, una tarjeta móvil y el modal de consentimiento móvil. Se corrigió el estilo global inline de code que afectaba al bloque de código; después se repitió el flujo y el build. El modal admite desplazamiento interno en pantallas pequeñas. Artefactos ignorados: `.tools/qa/phase5-rules-{desktop,mobile}.png`, `phase5-finding-{desktop,mobile}.png`, `phase5-test-desktop.png`, `phase5-consent-mobile.png`, `phase5-consent-dialog.png`.

## Migración local y puesta en marcha

Se creó una copia SQLite consistente mediante `Connection.backup` en `.tools/backups/before-phase5-20261109-172631.db`, antes de migrar la base de desarrollo. Se aplicó `c39d87a4e620 -> d51e09a3b842`. Recuentos anteriores/posteriores: 0 proyectos, 0 ejecuciones, 0 incidencias y 0 páginas; nueva tabla AIAnalysis vacía. `PRAGMA foreign_key_check` no encontró inconsistencias y Alembic no detectó diferencias con los modelos.

La instalación y variables del proveedor están en README y `backend/.env.example`. Para usar reglas, deja `BLACKBOX_AI_PROVIDER=disabled`. Para LLM, configura proveedor, un modelo compatible y una clave local, reinicia el backend y autoriza cada análisis desde el modal. No se ha añadido ni publicado una clave real.

Al comprobar el estado final, los puertos 8000 y 5173 estaban libres. Se arrancaron FastAPI y Vite actualizados como procesos ocultos, sin detener otros procesos. La salud confirmó SQLite conectado; `/ai/capabilities` confirmó rules habilitado, proveedor disabled y modelo vacío; el frontend respondió HTTP 200. La demo y navegación remota permanecen deshabilitadas. No se insertaron datos de ejemplo en la base de desarrollo. Los logs locales quedan en `.tools/logs/phase5-*`, ignorados por Git. Las pruebas de interfaz anteriores usaron procesos temporales separados. Si cambias variables del proveedor después, reinicia FastAPI para cargar esa configuración.

Comandos ejecutables desde la raíz con los runtimes de esta copia:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_intelligence.py
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

## Costes y límites conocidos

No se ha incurrido ni medido un coste comercial durante estas pruebas. Las tarifas de 3/15 USD usadas en fixtures son valores sintéticos para comprobar la fórmula, **no precios actuales ni recomendaciones de modelo**. La reserva por bytes y salida máxima contempla ambos intentos y se contrasta con cuotas/budget antes de enviar; su método completo está documentado en README. No representa una factura, descuentos, caché de proveedor ni cargos no comunicados; se recomienda limitar también el gasto en la cuenta externa.

Las conclusiones LLM necesitan revisión: IDs válidos y JSON correcto no prueban que toda frase sea cierta. Los filtros de secretos/inyección son heurísticos y pueden fallar; no hay análisis de capturas ni OCR. Solo hay un adaptador inicial y debe configurarse un modelo compatible. Se guardan resultados finales estructurados, sin razonamientos internos. Las plantillas no cubren flujos o selectores no registrados, y la demo virtual requiere sustituir BASE_URL. El workspace local no es autenticación. No se habilita navegación remota, modelos grandes, GPU, infraestructura distribuida ni ejecución automática de tests propuestos.
