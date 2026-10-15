# MundoGo KMS API

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)]()

**Key Management Server para DRM Widevine** — Generación, rotación y entrega de content keys para protección de contenido video streaming.

---

## Visión General

KMS API es el servidor central de gestión de llaves DRM para MundoGo. Proporciona:

- **Generación de content keys** — Creación automática de KID + Key para canales
- **Rotación de llaves** — Rotación programada o bajo demanda
- **Entrega de licencias** — Proxy para proveedores DRM (Widevine)
- **Gestión de usuarios VIP** — CRUD de usuarios con sincronización CMS
- **Monitoreo** — Health checks y estadísticas en tiempo real

## Quickstart

### Requisitos

- Python 3.11+
- Redis 6+
- MySQL 8+
- Acceso a proveedor DRM (Widevine)

### Instalación

```bash
# Clonar repositorio
git clone https://github.com/eskiconce/api_kms.git
cd api_kms

# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install fastapi uvicorn redis aiomysql httpx pydantic

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tus valores

# Ejecutar
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Verificar

```bash
curl http://localhost:8000/health
```

## Endpoints

### Health & Monitoring

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/health` | Estado del sistema (Redis, MySQL) |
| GET | `/api/stats` | Estadísticas generales |
| GET | `/api/logs` | Logs de actividad |
| GET | `/api/activity` | Actividad de licencias |

### Content Keys

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/kms/generate` | Generar/obtener key para canal |
| POST | `/api/keys/rotate` | Rotar key de un canal |
| GET | `/api/keys` | Listar keys recientes |

### Licencias Widevine

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/wv-v1/license` | Licencia Widevine v1 |
| POST | `/wv-v2/license` | Licencia Widevine v2 |
| POST | `/wv/license` | Proxy a proveedor DRM |

### VIP Users

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/vip/users` | Listar usuarios VIP |
| GET | `/api/vip/users/{user_id}` | Obtener usuario VIP |
| POST | `/api/vip/users` | Crear usuario VIP |
| PUT | `/api/vip/users/{user_id}` | Actualizar usuario VIP |
| DELETE | `/api/vip/users/{user_id}` | Eliminar usuario VIP |

### CMS Webhook

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/cms/webhook` | Sincronización desde CMS |

## Ejemplos Rápidos

### Generar key para canal

```bash
curl -X POST http://localhost:8000/kms/generate \
  -H "Content-Type: application/json" \
  -d '{"channel_id": "canal-hd-1"}'
```

**Response:**
```json
{
  "status": "created",
  "kid": "a1b2c3d4e5f67890123456789abcdef",
  "key": "00112233445566778899aabbccddeeff",
  "channel": "canal-hd-1"
}
```

### Obtener licencia Widevine

```bash
curl -X POST http://localhost:8000/wv-v1/license \
  -H "Content-Type: application/json" \
  -d '{"token": "user_valid_token", "kid": "a1b2...", "challenge": "base64..."}'
```

### Crear usuario VIP

```bash
curl -X POST http://localhost:8000/api/vip/users \
  -H "Content-Type: application/json" \
  -d '{"user_id": "usr123", "username": "Juan", "max_screens": 3}'
```

## Arquitectura

```
┌─────────────────────────────────────────────────┐
│                  KMS API                        │
│  ┌─────────────────────────────────────────┐   │
│  │  FastAPI + Uvicorn                      │   │
│  │  - Content Key Management               │   │
│  │  - License Proxy                        │   │
│  │  - VIP Users CRUD                       │   │
│  └─────────────────────────────────────────┘   │
│                      │                          │
│         ┌────────────┼────────────┐            │
│         ▼            ▼            ▼            │
│   ┌──────────┐ ┌──────────┐ ┌──────────┐     │
│   │  Redis   │ │  MySQL   │ │  DRM     │     │
│   │  Cache   │ │  Store   │ │ Provider │     │
│   └──────────┘ └──────────┘ └──────────┘     │
└─────────────────────────────────────────────────┘
```

Ver [docs/architecture.md](docs/architecture.md) para detalles.

## Variables de Entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `REDIS_HOST` | localhost | Host de Redis |
| `REDIS_PORT` | 6379 | Puerto de Redis |
| `MYSQL_HOST` | localhost | Host de MySQL |
| `MYSQL_USER` | drm_user | Usuario MySQL |
| `MYSQL_PASSWORD` | - | Contraseña MySQL |
| `MYSQL_DATABASE` | drm_system | Base de datos |
| `DRM_PROVIDER_URL` | - | URL del proveedor DRM |
| `CMS_API_KEY` | - | API key para webhook CMS |
| `LOG_DIR` | logs | Directorio de logs |

Ver [docs/configuration.md](docs/configuration.md) para detalles.

## Despliegue

```bash
# Deploy a servidor de producción
./deploy-kms.sh

# Solo verificar conexión
./deploy-kms.sh --test
```

Ver [docs/deployment.md](docs/deployment.md) para el proceso completo.

## Documentación

| Documento | Descripción |
|-----------|-------------|
| [docs/architecture.md](docs/architecture.md) | Arquitectura del sistema |
| [docs/api-reference.md](docs/api-reference.md) | Referencia completa de API |
| [docs/database.md](docs/database.md) | Esquema de base de datos |
| [docs/configuration.md](docs/configuration.md) | Variables de entorno |
| [docs/deployment.md](docs/deployment.md) | Proceso de despliegue |
| [docs/monitoring.md](docs/monitoring.md) | Monitoreo y health checks |
| [docs/ha-design.md](docs/ha-design.md) | Diseño de alta disponibilidad |

## Desarrollo

### Estructura del Proyecto

```
api_kms/
├── main.py              # API principal (FastAPI)
├── deploy-kms.sh        # Script de despliegue
├── deploy-kms.exp       # Wrapper expect para deploy
├── .env.example         # Template de variables
├── docs/                # Documentación
└── openspec/            # Especificaciones OpenSpec
```

### Endpoints de Desarrollo

```bash
# Docs interactivas (Swagger)
open http://localhost:8000/docs

# ReDoc
open http://localhost:8000/redoc
```

## Licencia

Propietario — MundoGo / OYM Service. Todos los derechos reservados.
