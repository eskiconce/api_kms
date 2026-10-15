# Arquitectura del Sistema

## Vista General

KMS API es una aplicación **FastAPI** async que funciona como servidor de gestión de llaves DRM Widevine. La arquitectura sigue un patrón **stateless** con caché Redis y persistencia MySQL.

```
                        ┌─────────────────┐
                        │    Clients      │
                        │  (Packagers,    │
                        │   Players, CMS) │
                        └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │    KMS API      │
                        │   (FastAPI)     │
                        │   Port 8000     │
                        └────────┬────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
        ┌──────────┐      ┌──────────┐      ┌──────────┐
        │  Redis   │      │  MySQL   │      │  DRM     │
        │  Cache   │◄────►│  Store   │      │ Provider │
        │  :6379   │      │  :3306   │      │(Widevine)│
        └──────────┘      └──────────┘      └──────────┘
```

## Componentes

### 1. KMS API (FastAPI)

La aplicación principal maneja:

- **Content Key Management** — Generación, rotación y lookup de llaves
- **License Proxy** — Enrutamiento de requests al proveedor DRM
- **VIP Users CRUD** — Gestión de usuarios con sync CMS
- **Monitoring** — Health checks y estadísticas

**Stack:**
- Python 3.11+
- FastAPI (async)
- Uvicorn (ASGI server)
- aiomysql (async MySQL)
- redis-py (async Redis)
- httpx (async HTTP client)

### 2. Redis (Cache)

Redis actúa como capa de caché para:

- **Keys activas** — `drm:key:{kid}` → content_key (TTL: 6h)
- **Canales activos** — `drm:active_channel:{channel_id}` → `{kid}:{key}` (TTL: 10min)

**Patrón de fallback:** Si Redis no está disponible, la API consulta MySQL directamente.

### 3. MySQL (Persistencia)

Base de datos relacional con 3 tablas principales:

- `content_keys` — Almacena todas las keys generadas
- `vip_users` — Usuarios VIP con límites de pantallas
- `license_activity` — Log de actividad de licencias

Ver [database.md](database.md) para el esquema completo.

### 4. DRM Provider (Externo)

Proveedor Widevine externo que firma licencias. La API actúa como proxy:
1. Recibe challenge del cliente
2. Valida token y KID
3. Envía challenge al proveedor
4. Retorna licencia firmada

## Flujo de Datos

### Generación de Keys

```
Client ──POST /kms/generate──► KMS API
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                              ▼
              Redis HIT?                    MySQL Lookup
                    │                              │
                    ▼                              ▼
              Return cached              Generate new / Return existing
```

### Entrega de Licencias

```
Player ──POST /wv/license──► KMS API
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                             ▼
              Validate KID                  Get Key from cache/DB
                    │                             │
                    └─────────────┬─────────────┘
                                  ▼
                          Forward to DRM Provider
                                  │
                                  ▼
                          Return signed license
```

## Consideraciones de Diseño

### Statelessness

La API no mantiene estado en memoria entre requests. Todo el estado vive en Redis/MySQL. Esto permite:
- Múltiples instancias detrás de load balancer
- Failover rápido sin pérdida de datos
- Escalado horizontal horizontal

### Caché Strategy

- **Read-through cache** — Primero Redis, fallback a MySQL
- **Write-through** — Escritura a MySQL + actualización Redis
- **TTL-based invalidation** — Keys expiran automáticamente

### Error Handling

- Redis caído → Fallback a MySQL (log warning)
- MySQL caído → HTTP 503
- DRM Provider caído → HTTP 502

## Seguridad

- **API Key** — Webhook CMS requiere `X-API-Key` header
- **Token validation** — License endpoints validan tokens
- **CORS** — Configurable (actualmente `*` para desarrollo)
- **No secrets en código** — Variables de entorno via `.env`

## HA (Alta Disponibilidad)

El diseño HA propuesto utiliza **Keepalived + VIP** para failover activo/standby. Ver [ha-design.md](ha-design.md) para detalles.
