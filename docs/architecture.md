# Arquitectura — fase 2

## Estructura definitiva

El workspace ya es la raíz del monorepositorio: no se añade otra carpeta `blackbox-ai/`.

```text
backend/
  app/
    api/             salud/dashboard y router reutilizado de proyectos
    core/            configuración, motor SQLite, sesiones y ámbito de workspace
    models/          Project, Run, Issue y enumeraciones
    repositories/    CRUD de proyectos y consultas agregadas del dashboard
    schemas/         contratos de respuesta Pydantic
    main.py          aplicación ASGI y ciclo de vida
  alembic/versions/  historial de migraciones
  tests/             integración HTTP + SQLite temporal real
  data/              datos locales ignorados por Git
frontend/
  src/
    components/      shell, formulario reutilizable, diálogo de borrado y estados
    hooks/           carga, cancelación y recarga
    pages/           dashboard, listado, detalle, creación/edición y configuración
    services/        cliente HTTP con timeout
    types/           contratos TypeScript
docs/
scripts/             arranque independiente desde PowerShell
```

Las carpetas de servicios, agentes y testing se añadirán cuando contengan implementación real. Los paquetes no incluyen módulos vacíos para funciones futuras.

## Flujo

React → cliente HTTP común → FastAPI → repositorios SQLAlchemy → SQLite.

Salud y dashboard conservan sus rutas `/api/v1`. Proyectos reutiliza un router bajo `/api/v1/projects` y `/api/projects`; no hay dos implementaciones ni dos conjuntos de datos. La API devuelve listas paginadas (por defecto 20, máximo 100), y el frontend recorre páginas de 12.

Un proceso de backend, un proceso Vite, consultas síncronas pequeñas y conexiones SQLite de corta duración. El backend dispone el motor al apagarse. No hay contenedores, GPU, modelos locales, trabajadores de análisis ni navegadores automatizados.

Las migraciones se ejecutan explícitamente antes de servir (el script de arranque lo hace). El servidor no utiliza `create_all`, no borra datos ni crea registros de demostración. La ruta relativa de la base se resuelve contra `backend/`, incluso si se llama Alembic desde otra carpeta.

## Datos y semántica

- `Project`: nombre, descripción, URL base, ámbito de workspace, fechas y límites iniciales de páginas (1–50), profundidad (0–5) y duración (10–300 s). Los límites son de solo lectura en la API y todavía no existe un motor que los ejecute.
- `Run`: proyecto, estado, páginas visitadas y fechas. El contador «Análisis ejecutados» incluye todas las ejecuciones registradas, también en cola. «En cola o en ejecución» suma ambos estados activos.
- `Issue`: ejecución, tipo, severidad, descripción, URL, evidencia opcional, reproducción, estado y fecha. El proyecto se obtiene mediante la ejecución para evitar inconsistencias entre dos claves de proyecto.
- «Errores detectados» y «Errores críticos» cuentan todos los hallazgos históricos, independientemente de su estado de resolución.
- Gráfico: 14 fechas UTC, incluida hoy. Cada serie agrupa por la fecha de creación del registro correspondiente. El historial muestra las 8 ejecuciones más recientes; la vista de proyectos, los 5 proyectos más recientes.
- Las fechas se guardan en UTC y se devuelven con zona explícita; las horas de la interfaz usan la zona del navegador.
- SQLite impone claves foráneas, borrado en cascada, enumeraciones y límites. El borrado confirmado en la interfaz elimina también las ejecuciones y errores asociados. PATCH solo cambia los campos presentes y actualiza la fecha cuando hay modificaciones reales.

La migración de fase 2 añade `description` (vacía para registros anteriores) y `workspace_id` (`local` para registros anteriores), junto con un índice. No recrea la tabla de proyectos ni elimina sus relaciones. Se verifica la conservación de proyectos, ejecuciones y errores con datos de fase 1 antes de aplicar la migración.

## Red y alcance de seguridad

La API registra URLs como datos y no realiza DNS, peticiones HTTP ni navegación hacia ellas. El validador comprueba sintaxis HTTP/HTTPS, longitud y ausencia de credenciales, consultas y fragmentos. Los errores de validación no devuelven los valores de entrada. React representa nombre, descripción y URL como texto, sin HTML dinámico ni enlaces externos a la URL del proyecto. Las consultas usan SQLAlchemy y parámetros enlazados.

`get_workspace_access` proporciona un ámbito `local` controlado por el servidor. Todos los métodos del repositorio de proyectos y las agregaciones del dashboard aplican ese ámbito. Los campos de entrada prohíben propiedades adicionales, como workspace, identificadores, fechas o límites. Esta dependencia se sustituirá por membresía autenticada cuando se implemente identidad; no acepta un workspace mediante cabeceras de cliente. Registrar un proyecto no concede autorización para testing.

CORS admite únicamente los orígenes locales configurados y los métodos GET/POST/PATCH/DELETE; no sustituye autenticación. Los scripts enlazan ambos servidores a `127.0.0.1`.

La fase 3 debe introducir juntos el motor y su política de red: validación DNS, fijación/validación de destinos frente a rebinding, control de redirecciones y subrecursos, bloqueo de IP privadas/metadatos, excepciones locales explícitas, métodos no destructivos, presupuestos y redacción de evidencias. Esos controles aún no están implementados y deben verificarse antes de aceptar análisis.

No existe autenticación multiusuario ni despliegue SaaS en esta fase. No expongas este entorno local a redes públicas. El acceso a documentación API es solo de desarrollo. `frontend/.env` es configuración pública y nunca debe contener secretos.

## Referencias técnicas

- [FastAPI: CORS](https://fastapi.tiangolo.com/tutorial/cors/) para configurar orígenes explícitos.
- [Alembic: tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html) para versionar el esquema.
- [Vite: requisitos de Node y arranque](https://vite.dev/guide/) para ejecutar el frontend.
- [FastAPI: actualizaciones parciales](https://fastapi.tiangolo.com/tutorial/body-updates/) para conservar campos omitidos en PATCH mediante `exclude_unset`.
