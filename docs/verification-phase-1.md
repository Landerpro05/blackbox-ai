# Verificación de la fase 1

Fecha: 9 de noviembre de 2026 (Europe/Madrid).

## Entorno usado

- Windows, PowerShell.
- Python 3.12.16 en un runtime portable del workspace.
- Node.js 24.22.2, npm 11.19.1.
- SQLite local; sin GPU, contenedores, Playwright ni claves de IA.
- Dependencias fijadas en `backend/requirements.lock`, `backend/requirements-dev.lock` y `frontend/package-lock.json`.

## Comprobaciones ejecutadas

| Comprobación | Resultado observado |
| --- | --- |
| `python -m pytest` | 10 pruebas correctas, sin avisos en la ejecución final |
| `python -m alembic upgrade head` | Migración inicial aplicada a la base de desarrollo |
| `python -m alembic check` | Sin diferencias entre modelos y migración |
| Upgrade → downgrade → upgrade | Correcto en una base temporal; incluido en pytest |
| `python -m pip check` | Sin dependencias incompatibles |
| `npm.cmd run build` | TypeScript y build Vite correctos; sin aviso de chunks grandes tras separar el gráfico |
| `start-backend.ps1` | FastAPI escuchando en `127.0.0.1:8000` |
| `start-frontend.ps1` | Vite escuchando en `127.0.0.1:5173` |
| Salud por HTTP real | 200; `status=ok`, `database=connected` |
| Dashboard por HTTP real | 200; contadores a cero, 14 fechas, proyectos e historial vacíos |
| CORS en respuesta HTTP real | `Access-Control-Allow-Origin: http://127.0.0.1:5173` |
| HTML servido por Vite | 200 |
| Cliente frontend real → API real | `fetchOverview` recibió salud y dashboard correctamente |
| Cliente frontend con backend detenido | Devolvió el mensaje controlado de fallo de conexión |

La prueba del cliente frontend cargó el módulo `src/services/api.ts` transformado por Vite y ejecutó su función exportada con Node, mediante peticiones HTTP reales. Esto verifica el cliente de datos, no el renderizado de React en un navegador.

Los diez tests cubren salud, estado vacío, agregaciones con varias relaciones, límite y orden de historial, persistencia al reconectar, claves foráneas y límites, cascadas, migraciones reversibles, respuesta 503 ante tablas ausentes y orígenes CORS permitidos/rechazados. Los registros de prueba solo se insertaron en bases temporales.

## Límite de verificación visual

Se intentó abrir el entorno con la herramienta de navegador, pero el host de acceso al navegador y el canal de aplicaciones no estaban disponibles. **No se verificaron visualmente el renderizado, los tamaños móviles ni las interacciones de React en un navegador.**

Para completar esa revisión manual, arranca ambos servicios con los comandos del README, abre `http://127.0.0.1:5173`, comprueba los estados vacíos, pulsa Actualizar, visita Configuración y reduce el ancho de la ventana para revisar el menú móvil. Detén FastAPI para probar Reintentar conexión y vuelve a arrancarlo.

## Estado al finalizar

Los procesos de preview propios de esta verificación quedaron detenidos para liberar memoria. La base de desarrollo conserva el esquema migrado y ningún proyecto, ejecución ni error de demostración. Los scripts permiten arrancar ambos servicios de nuevo de forma independiente.

La fase 2 no se inició. El CRUD, el motor de testing, la política SSRF, las evidencias, los informes y la IA están pendientes de sus fases correspondientes.
