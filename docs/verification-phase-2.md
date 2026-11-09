# Fase 2 — cambios y verificación

Fecha: 9 de noviembre de 2026 (Europe/Madrid).

## Resultado

Gestión real de proyectos sobre la arquitectura de fase 1: creación, listado paginado, detalle, edición parcial y borrado confirmado en la interfaz. Las vistas usan la API y SQLite; no se añadieron proyectos de demostración a la base de desarrollo.

Se conservan los endpoints de salud y dashboard. El router de proyectos se publica bajo `/api/v1/projects` y `/api/projects` con los mismos handlers, validaciones y datos. El frontend usa la ruta versionada existente.

## Archivos añadidos

| Área | Archivos | Función |
| --- | --- | --- |
| Backend | `backend/app/api/projects.py`, `backend/app/repositories/projects.py` | CRUD, paginación, transacciones, respuestas 201/200/204/404/422/503 |
| Contratos | `backend/app/schemas/projects.py`, `backend/app/schemas/common.py` | Validación, respuestas tipadas y fechas UTC compartidas |
| Ámbito | `backend/app/core/access.py` | Workspace asignado por el servidor; punto de integración para membresía futura |
| Migración | `backend/alembic/versions/b72c4f2810a1_project_details_and_workspace.py` | Descripción y workspace para registros nuevos y existentes |
| Tests backend | `backend/tests/test_projects.py` | 57 casos adicionales, incluidas variantes parametrizadas |
| Pantallas | `frontend/src/pages/Projects.tsx`, `ProjectDetail.tsx`, `ProjectEditor.tsx` | Listado, detalle, creación y edición |
| Componentes | `frontend/src/components/ProjectForm.tsx`, `DeleteProjectDialog.tsx`, `ResourceFeedback.tsx` | Formulario compartido, confirmación, carga y errores |
| Cliente y estado | `frontend/src/services/projects.ts`, `format.ts`, `frontend/src/hooks/useResource.ts` | Acceso tipado, fechas y lecturas cancelables |
| Estilos | `frontend/src/projects.css` | Formularios, tarjetas, detalle, diálogo y tamaños responsive |
| Integración frontend | `frontend/scripts/verify-projects-client.mjs` | Cliente TypeScript real contra FastAPI temporal |

## Archivos existentes modificados

- `backend/app/models/entities.py`: descripción y workspace de proyecto.
- `backend/app/main.py`: registro del router, métodos CORS y errores 422 sin valores de entrada.
- `backend/app/api/routes.py` y `repositories/dashboard.py`: consultas del dashboard bajo el mismo ámbito de workspace.
- `backend/app/schemas/dashboard.py`: reutilización del tipo UTC común.
- `backend/app/core/database.py`: actualización del mensaje de alcance SQLite.
- `frontend/src/services/api.ts`: cliente compartido para GET/POST/PATCH/DELETE, respuestas 204, errores tipados y errores por campo.
- `frontend/src/types/api.ts`: contratos de proyectos.
- `frontend/src/App.tsx`, `components/Layout.tsx`, `pages/Dashboard.tsx`, `pages/Settings.tsx`, `main.tsx`: rutas, navegación, enlaces y textos de fase 2.
- `frontend/package.json`: comando `test:integration`; sin nuevas dependencias.
- `README.md` y `docs/architecture.md`: uso, endpoints, migración, límites y verificación.

No se modificaron `lambda_insert_incendio.py` ni `best.pt`.

## Resultados ejecutados

| Comprobación | Resultado real |
| --- | --- |
| `python -m pytest` | **67 passed**, sin avisos; incluye las 10 pruebas originales sin modificarlas |
| `python -m alembic upgrade head` | Aplicada `b72c4f2810a1` sobre la base local de desarrollo |
| `python -m alembic check` | Sin diferencias de esquema pendientes |
| `PRAGMA foreign_key_check` | Sin inconsistencias en la base de desarrollo |
| `python -m pip check` | Sin dependencias incompatibles |
| `npm.cmd run build` | TypeScript y Vite correctos, sin avisos de tamaño de chunks |
| `npm.cmd run test:integration` | Correcto: CRUD, 204 sin JSON, 422 por campo, 404, dashboard y desconexión |

Los tests backend verifican datos válidos e inválidos, campos de solo servidor, UUIDs, nombres como texto SQL/HTML, errores sin secretos, actualización de fechas, paginación, persistencia mediante otra conexión, cascadas y CORS. Otra prueba impide DNS y conexiones de socket durante las operaciones de registro/edición/consulta/borrado para detectar accesos accidentales al destino.

Se insertaron registros de otro workspace exclusivamente en tests para comprobar que ni el CRUD ni los contadores, historial y series del dashboard los exponen en el ámbito local. Esto no equivale a implementar autenticación.

La prueba de migración crea primero un proyecto, una ejecución y un error usando el esquema de fase 1; después aplica la migración de fase 2 y comprueba que los tres permanecen relacionados y que los nuevos campos tienen sus valores iniciales.

Antes de actualizar la base de desarrollo se creó una copia consistente mediante la API de backup de SQLite en `.tools/backups/before-phase2-*.db`. Sus recuentos antes y después fueron iguales: 0 proyectos, 0 ejecuciones y 0 errores. No se borraron ni añadieron registros de demostración.

## Qué comprueba el test del frontend

`test:integration` crea un directorio temporal, migra una SQLite desechable y arranca un FastAPI con un worker en un puerto local libre. Vite carga los módulos de servicios TypeScript. El test ejecuta sus funciones exportadas con Node y comprueba respuestas y errores reales. Después detiene sus procesos y elimina únicamente su directorio temporal verificado.

No necesita un navegador instalado ni modifica la base de desarrollo. Tampoco ejecuta ninguna petición a las URLs registradas. No se han añadido dependencias a backend ni frontend en esta fase.

## Verificación visual pendiente

El host de acceso al navegador y el canal de aplicaciones no están disponibles en esta sesión. **No se verificaron visualmente el renderizado de React, los clics, la gestión de foco del diálogo ni el diseño móvil.** El build y el cliente HTTP sí se ejecutaron; no sustituyen esa revisión.

Para comprobarlo manualmente:

1. Arranca ambos servicios con los scripts del README y visita `/projects`.
2. Crea un proyecto con un nombre y una URL de tu elección; comprueba el mensaje de éxito y los datos del detalle.
3. Edita solo la descripción; comprueba que nombre, URL y creación se conservan y que cambia la fecha de actualización.
4. Vuelve al listado y al dashboard; comprueba que reflejan el proyecto.
5. Abre Eliminar y cancela: el proyecto debe permanecer. Repite y confirma para eliminarlo.
6. Reduce la ventana para revisar tarjetas, formulario y navegación móvil.
7. Detén el backend, recarga el listado, comprueba el error y reinicia para reintentar.

## Estado final y alcance pendiente

La base de desarrollo está migrada. Los procesos temporales de integración quedaron detenidos. Los comandos de arranque no cambian; `start-backend.ps1` aplica las migraciones antes de servir. No se han añadido servicios persistentes, IA, Docker ni Playwright.

La fase 3 no se inició. No existe todavía un motor de testing, política SSRF ni autorización de destinos. Registrar un proyecto solo almacena sus datos y no concede permiso para analizarlo. La aplicación sigue siendo un entorno local sin autenticación, con un workspace compartido.
