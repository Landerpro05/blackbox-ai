# Arquitectura — fase 3

## Estructura definitiva

El workspace ya es la raíz del monorepositorio: no se añade otra carpeta `blackbox-ai/`.

```text
backend/
  app/
    api/             salud, dashboard, proyectos, ejecuciones y evidencias
    core/            configuración, motor SQLite, sesiones y ámbito de workspace
    models/          Project, Run, Issue y enumeraciones
    repositories/    proyectos, resultados, progreso y agregaciones del dashboard
    schemas/         contratos de respuesta Pydantic
    services/        coordinación de un análisis y bloqueo de proceso
    testing/         Chromium, demo integrada, política y almacén de evidencias
    main.py          aplicación ASGI, recuperación y cierre
  alembic/versions/  historial de migraciones
  tests/             integración HTTP + SQLite temporal real
  data/              datos locales ignorados por Git
frontend/
  src/
    components/      shell, formulario reutilizable, diálogo de borrado y estados
    hooks/           carga, cancelación y recarga
    pages/           dashboard, proyectos, historial y progreso/resultados de análisis
    services/        cliente HTTP con timeout
    types/           contratos TypeScript
docs/
scripts/             arranque independiente desde PowerShell
```

Las carpetas de servicios, agentes y testing se añadirán cuando contengan implementación real. Los paquetes no incluyen módulos vacíos para funciones futuras.

## Flujo

React → cliente HTTP común → FastAPI → repositorios SQLAlchemy → SQLite.

Salud y dashboard conservan sus rutas `/api/v1`. Proyectos reutiliza un router bajo `/api/v1/projects` y `/api/projects`; no hay dos implementaciones ni dos conjuntos de datos. La API devuelve listas paginadas (por defecto 20, máximo 100), y el frontend recorre páginas de 12.

Un proceso de backend y un proceso Vite. El análisis es una tarea asyncio con un Chromium headless, un contexto y una pestaña de recorrido. Las transacciones de progreso se ejecutan en hilos, con sesiones independientes y esperas protegidas frente a cancelación. No hay colas externas, contenedores, GPU ni modelos de IA.

Las migraciones se ejecutan explícitamente antes de servir (el script de arranque lo hace). El servidor no utiliza `create_all`, no borra datos ni crea registros de demostración. La ruta relativa de la base se resuelve contra `backend/`, incluso si se llama Alembic desde otra carpeta.

## Datos y semántica

- `Project`: nombre, descripción, URL base, ámbito de workspace, fechas y límites históricos de páginas (1–50), profundidad (0–5) y duración (10–300 s). Esos límites son de solo lectura en el CRUD del proyecto; las ejecuciones usan los límites propios descritos a continuación.
- Esos límites históricos de proyecto se conservan. Cada nueva ejecución recibe límites propios, con valores predeterminados 10 páginas, profundidad 2, navegación 15 s, global 120 s y 100 peticiones. Sus máximos de API son 20, 3, 30 s, 180 s y 200 respectivamente.
- `Run`: proyecto, estado, páginas visitadas y fechas. El contador «Análisis ejecutados» incluye todas las ejecuciones registradas, también en cola. «En cola o en ejecución» suma ambos estados activos.
- Se amplía `Run` con workspace, destino inmutable, límites JSON, contador de incidencias/peticiones, duración, mensaje de error, cancelación y slot activo. `TestRun` es un alias del modelo existente, no una tabla duplicada. La API presenta `pending` para el `queued` histórico, conservando restricciones y datos anteriores.
- `Issue`: ejecución, tipo, severidad, descripción, URL, evidencia opcional, reproducción, estado y fecha. El proyecto se obtiene mediante la ejecución para evitar inconsistencias entre dos claves de proyecto.
- `TestIssue` reutiliza `Issue`, añadiendo título; `TestPage` persiste URL redactada, código HTTP, tiempo, profundidad, fecha y captura. Las decisiones de política se registran como incidencias informativas y se distinguen por tipo/severidad de los fallos HTTP/JS.
- «Errores detectados» y «Errores críticos» cuentan todos los hallazgos históricos, independientemente de su estado de resolución.
- Gráfico: 14 fechas UTC, incluida hoy. Cada serie agrupa por la fecha de creación del registro correspondiente. El historial muestra las 8 ejecuciones más recientes; la vista de proyectos, los 5 proyectos más recientes.
- Las fechas se guardan en UTC y se devuelven con zona explícita; las horas de la interfaz usan la zona del navegador.
- SQLite impone claves foráneas, borrado en cascada, enumeraciones y límites. El borrado confirmado en la interfaz elimina también las ejecuciones y errores asociados. PATCH solo cambia los campos presentes y actualiza la fecha cuando hay modificaciones reales.

La migración de fase 2 añade `description` (vacía para registros anteriores) y `workspace_id` (`local` para registros anteriores), junto con un índice. No recrea la tabla de proyectos ni elimina sus relaciones. Se verifica la conservación de proyectos, ejecuciones y errores con datos de fase 1 antes de aplicar la migración.

La migración de fase 3 añade columnas e índices a `runs`, título a `issues` y la tabla `test_pages`, sin reconstruir las tablas anteriores. Rellena el workspace/destino de ejecuciones antiguas desde su proyecto y cuenta sus incidencias existentes. Los tests verifican conservación y downgrade/upgrade. Los datos de desarrollo se respaldaron antes de aplicar cada migración.

## Ejecución y ciclo de vida

1. La API verifica workspace, consentimiento booleano explícito, activación de demo y origen permitido. Congela URL/límites y guarda una ejecución pendiente con `active_slot=1`.
2. `RunManager` crea una tarea y responde 202. No hay cola en memoria: una segunda ejecución recibe 409.
3. El slot único de SQLite es global, incluso entre workspaces. Un bloqueo de archivo por base impide dos procesos API/coordinadores simultáneos. Las mutaciones del proyecto y la creación de análisis se serializan con transacciones SQLite inmediatas.
4. El worker marca running y arranca `DemoEngine`. El recorrido BFS usa URLs normalizadas, conjunto de visitadas, profundidad, máximo de páginas/peticiones y deadline.
5. Cada página escribe una transacción con sus incidencias y progreso. La cancelación espera a terminar una escritura ya iniciada, evitando finalizar el run antes de sus registros.
6. Cancelar o vencer el deadline interrumpe el trabajo; el `finally` cancela handlers pendientes, cierra contexto/navegador y detiene el driver. Solo entonces se guarda el estado final y se libera el slot. Los tiempos incluyen preparación y limpieza; la limpieza puede exceder el deadline de navegación.
7. Un cierre normal solicita cancelación. En el siguiente arranque, cualquier pending/running interrumpido pasa a failed por reinicio, aun si se arranca sin habilitar la demo. No hay reintentos de navegación ni reanudación automáticos.

En Windows, la ejecución requiere ProactorEventLoop. Uvicorn con recarga o múltiples workers usa un bucle distinto en la versión instalada; la demo rechaza ese modo de arranque con un mensaje explícito. El script y la documentación usan un worker sin recarga.

Se mantienen resultados parciales al fallar o cancelar. Las capturas se escriben de forma atómica bajo IDs UUID y se eliminan si falla su persistencia de página. La eliminación confirmada de un proyecto finalizado borra sus filas por cascada y sus archivos conocidos; fallos del sistema de archivos pueden dejar evidencias huérfanas para limpieza administrativa. No se hace borrado recursivo de rutas introducidas por usuarios.

## Red y alcance de seguridad

El CRUD registra URLs como datos y no realiza DNS, peticiones HTTP ni navegación hacia ellas. El validador comprueba sintaxis HTTP/HTTPS, longitud y ausencia de credenciales, consultas y fragmentos. Los errores de validación no devuelven los valores de entrada. React representa nombre, descripción y URL como texto, sin HTML dinámico ni enlaces externos a la URL del proyecto. Las consultas usan SQLAlchemy y parámetros enlazados.

`get_workspace_access` proporciona un ámbito `local` controlado por el servidor. Todos los métodos del repositorio de proyectos y las agregaciones del dashboard aplican ese ámbito. Los campos de entrada de proyectos prohíben propiedades adicionales, como workspace, identificadores, fechas o límites. Esta dependencia se sustituirá por membresía autenticada cuando se implemente identidad; no acepta un workspace mediante cabeceras de cliente. Registrar un proyecto no concede autorización para testing.

Las rutas de ejecuciones, incidencias, páginas, cancelación y PNG verifican tanto el workspace de la ejecución como el de su proyecto. Los archivos no se montan como un directorio estático. El cliente recibe URLs de API, no rutas del disco.

CORS admite únicamente los orígenes locales configurados y los métodos GET/POST/PATCH/DELETE; no sustituye autenticación. Los scripts enlazan ambos servidores a `127.0.0.1`.

### Alternativa controlada adoptada

La navegación remota y otros servidores locales permanecen deshabilitados. Se usa el origen virtual fijo `http://blackbox-demo.invalid`, servido por un catálogo de HTML/JS integrado. Solo GET y ese origen se aceptan; cada solicitud se resuelve con `route.fulfill` o `route.abort`, nunca con `continue_`/`fetch` al destino. No hay resolución DNS de destino ni entradas de hosts aportadas por el cliente.

Antes de devolver una redirección se valida su Location. Una redirección prohibida produce una respuesta local bloqueada y una incidencia, sin contactar su destino. Se bloquean subrecursos externos, iframes, WebSockets, métodos de escritura y Service Workers. Las descargas se rechazan; el crawler excluye enlaces de acciones y archivos. La inspección de formularios solo observa sus etiquetas.

Chromium se inicia sin GPU, con resolución de nombres deshabilitada y proxy sin salida como defensa adicional. Esto no es un aislamiento de red del sistema operativo ni una garantía para contenido remoto arbitrario. No se permite HTML/JS suministrado por usuarios. El contenido controlado evita la superficie de páginas ajenas; las pruebas de rebinding comprueban rechazo y ausencia de resolución, no un mecanismo general de fijación de IP.

La demo tiene activación explícita (deshabilitada por defecto y prohibida en production) y consentimiento por ejecución. Para habilitar sitios reales en el futuro será necesario definir y probar aislamiento de egress, verificación DNS/IP y redirecciones/subrecursos en esa arquitectura. La fase 3 no habilita ese modo.

Los mensajes se redactan antes de persistirlos, y las URLs se guardan sin consultas, credenciales ni fragmentos. Las capturas enmascaran todos los campos y bloques sensibles conocidos de la demo; su alcance está acotado al contenido integrado. No se almacenan cuerpos de peticiones, cookies ni cabeceras de autenticación. No hay IA ni ejecución de comandos arbitrarios.

## Frontend y comprobación

El detalle del proyecto integra autorización, límites e historial. El cliente lee primero el estado de la ejecución y después sus colecciones para evitar que una lectura terminal deje datos pendientes de consultar. Mientras está activa se consulta cada 1,5 s, sin solapar consultas; se cancelan lecturas al navegar y se detiene el polling al finalizar o ante errores.

La pantalla `/runs/{id}` muestra presupuesto recorrido, contadores, duración, cancelación, incidencias filtradas y capturas. La prueba local de navegador recorre estos flujos con SQLite temporal, revisa imágenes, ausencia de errores JS y menú/desbordamiento móvil. Las capturas de QA se inspeccionan como parte de la verificación y quedan fuera de Git.

No existe autenticación multiusuario ni despliegue SaaS en esta fase. No expongas este entorno local a redes públicas. El acceso a documentación API es solo de desarrollo. `frontend/.env` es configuración pública y nunca debe contener secretos.

## Referencias técnicas

- [FastAPI: CORS](https://fastapi.tiangolo.com/tutorial/cors/) para configurar orígenes explícitos.
- [Alembic: tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html) para versionar el esquema.
- [Vite: requisitos de Node y arranque](https://vite.dev/guide/) para ejecutar el frontend.
- [FastAPI: actualizaciones parciales](https://fastapi.tiangolo.com/tutorial/body-updates/) para conservar campos omitidos en PATCH mediante `exclude_unset`.
- [Playwright: interceptación y Service Workers](https://playwright.dev/python/docs/network) para el control de solicitudes del contexto.
- [Playwright: cierre del navegador](https://playwright.dev/python/docs/api/class-browser#browser-close) para el ciclo de vida de los recursos.
