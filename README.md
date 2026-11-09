# BLACKBOX AI

Plataforma de testing web autorizado. **Fase 2: gestión de proyectos.** Backend FastAPI y frontend React independientes, SQLite persistente, migraciones Alembic, dashboard conectado y CRUD completo de proyectos.

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

El motor Playwright y sus controles de red llegarán en la fase 3; informes en la 4; IA por API en la 5. No se necesita una clave de IA ni GPU. Registrar, editar o consultar una URL no realiza DNS, HTTP ni navegación hacia ella. No se incluyen autenticación ni despliegue público.

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
Los registros de [fase 1](docs/verification-phase-1.md) y [fase 2](docs/verification-phase-2.md) detallan los resultados comprobados y la revisión visual pendiente.

## Windows · instalación desde cero

Necesitas **Python 3.12** y **Node.js 24 LTS** con npm. No hacen falta Docker ni Chromium. Puedes instalar los runtimes desde sus sitios oficiales o usar WinGet:

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
Copy-Item backend\.env.example backend\.env
Set-Location backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Usa `requirements.lock` en lugar de `requirements-dev.lock` si no necesitas herramientas de pruebas. Los archivos `.txt` contienen los rangos de dependencias directas; los `.lock` fijan las versiones verificadas. No sobrescribas un `.env` existente con tus cambios.

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

El ajuste `Bypass` se limita al proceso que ejecuta cada script; no modifica la política del sistema. Opcionalmente añade `-Reload` al script de backend para recarga de desarrollo (crea un proceso de supervisión adicional).

Para reinstalar dependencias del frontend con el Node portable:

```powershell
Set-Location 'C:\Users\lande\Desktop\ProyectoTocho'
$env:PATH = "$(Join-Path (Get-Location).Path '.tools\node');$env:PATH"
Set-Location frontend
npm.cmd ci --no-fund --no-audit
```

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
5. **Eliminar** abre una confirmación. Cancelar no realiza ninguna petición DELETE; confirmar elimina el proyecto y sus ejecuciones y errores asociados de forma permanente.
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

`pytest` aplica las migraciones a archivos SQLite temporales: 67 casos de salud, dashboard, CRUD, entradas inválidas, historial, persistencia, ámbitos, cascadas, ausencia de red hacia destinos, conservación de datos al migrar y CORS. Mantiene las 10 pruebas originales de la fase 1. No modifica `backend/data/blackbox.db`.

`npm run build` comprueba TypeScript y genera `frontend/dist/`. `npm run test:integration` carga los módulos reales del cliente TypeScript con Vite y los ejecuta contra un FastAPI temporal con SQLite desechable: creación, listado, detalle, PATCH, DELETE/204, 422, 404, actualización del dashboard y error de conexión. El script elige un puerto libre, no necesita servidores arrancados, no toca tus proyectos y cierra sus procesos al terminar. No prueba renderizado ni clics de navegador; esa revisión se hace manualmente.

## Configuración y datos

`backend/.env` (opcional):

```dotenv
BLACKBOX_ENVIRONMENT=development
BLACKBOX_DATABASE_URL=sqlite:///./data/blackbox.db
BLACKBOX_CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
```

`frontend/.env` (opcional):

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

Sin esos archivos se utilizan los mismos valores por defecto. Reinicia los servicios después de cambiar configuración. Las rutas relativas de SQLite se resuelven contra `backend/`, no contra el directorio de la terminal. La base habitual queda en `backend/data/blackbox.db`; reiniciar los servidores conserva los datos. Alembic, no `create_all`, controla el esquema.

Las variables `VITE_` son visibles en el navegador. No guardes allí secretos. No hay campos para credenciales ni claves de IA en esta fase.

## Solución de problemas

- **`node`/`npm` no se reconoce:** instala Node o usa `start-frontend.ps1`, que añade `.tools/node` al PATH de su proceso. Invoca `npm.cmd` para evitar el bloqueo de `npm.ps1`.
- **Python 3.12 no aparece en `py`:** la instalación portable de esta copia no se registra en el lanzador Windows. Usa el entorno `backend/.venv` ya creado; en otra máquina instala Python 3.12 antes de crear el entorno.
- **API devuelve 503:** revisa que el directorio de la base sea escribible y ejecuta `python -m alembic upgrade head` usando el ejecutable del entorno y situándote en `backend/`.
- **Puerto ocupado:** detén el servicio anterior. Si cambias el puerto de FastAPI, actualiza `VITE_API_BASE_URL`; si cambias el de Vite, actualiza `BLACKBOX_CORS_ORIGINS`.
- **CORS:** el origen incluye protocolo, nombre de host y puerto. Se permiten `localhost:5173` y `127.0.0.1:5173`, no cualquier origen. Consulta [FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/).
- **No aparecen proyectos:** usa Nuevo proyecto. No se insertan ejemplos en tu base. Las ejecuciones siguen vacías porque el motor todavía no está implementado. Las pruebas usan registros únicamente en bases temporales.

Se usará un solo worker y un solo Chromium cuando llegue la fase 3. No se instalaron Playwright, Chromium, librerías LLM, DuckDB ni infraestructura distribuida en esta entrega.

**La fase 3 requiere tu confirmación. No se ha iniciado.**
