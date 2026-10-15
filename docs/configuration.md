# Configuración

## Variables de Entorno

KMS API se configura mediante variables de entorno. Usa `.env` o define las variables en el sistema.

### Template (.env.example)

```env
# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# MySQL
MYSQL_HOST=localhost
MYSQL_USER=drm_user
MYSQL_PASSWORD=your_password_here
MYSQL_DATABASE=drm_system

# DRM Provider
DRM_PROVIDER_URL=https://your-drm-provider.com/AcquireLicense

# CMS Webhook (API Key que el CMS debe enviar en X-API-Key)
CMS_API_KEY=cms_secret_key_2024

# Logging
LOG_DIR=logs
LOG_LEVEL=INFO
```

---

## Referencia Completa

### Redis

| Variable | Default | Descripción |
|----------|---------|-------------|
| `REDIS_HOST` | `localhost` | Host de Redis |
| `REDIS_PORT` | `6379` | Puerto de Redis |
| `REDIS_DB` | `0` | Base de datos Redis (0-15) |

### MySQL

| Variable | Default | Descripción |
|----------|---------|-------------|
| `MYSQL_HOST` | `localhost` | Host de MySQL |
| `MYSQL_USER` | `drm_user` | Usuario de MySQL |
| `MYSQL_PASSWORD` | `drm_pass_123` | Contraseña de MySQL |
| `MYSQL_DATABASE` | `drm_system` | Nombre de la base de datos |

### DRM Provider

| Variable | Default | Descripción |
|----------|---------|-------------|
| `DRM_PROVIDER_URL` | `https://35.234.128.244:8080/ConcurrentPlayback` | URL del proveedor DRM para firmar licencias |

### Seguridad

| Variable | Default | Descripción |
|----------|---------|-------------|
| `CMS_API_KEY` | `a1b2c3d4e5f67890123456789abcdef0` | API key para webhook CMS (header `X-API-Key`) |

### Logging

| Variable | Default | Descripción |
|----------|---------|-------------|
| `LOG_DIR` | `logs` | Directorio donde se escriben los logs |
| `LOG_LEVEL` | `INFO` | Nivel: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## Configuración por Ambiente

### Desarrollo

```env
REDIS_HOST=localhost
MYSQL_HOST=localhost
MYSQL_PASSWORD=dev_password
DRM_PROVIDER_URL=https://test-drm.example.com/AcquireLicense
CMS_API_KEY=dev_cms_key
LOG_LEVEL=DEBUG
```

### Producción

```env
REDIS_HOST=172.16.222.100
MYSQL_HOST=172.16.222.101
MYSQL_PASSWORD=<strong_password>
DRM_PROVIDER_URL=https://35.234.128.244:8080/ConcurrentPlayback
CMS_API_KEY=<random_32_chars_hex>
LOG_LEVEL=INFO
```

---

## Seguridad

### API Key del CMS

El webhook CMS (`/api/cms/webhook`) requiere header `X-API-Key`:

```bash
curl -X POST http://localhost:8000/api/cms/webhook \
  -H "X-API-Key: tu-api-key-secreta" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "usr123", "max_screens": 3}'
```

**Generar API key segura:**

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Tokens de Licencia

Los endpoints de licencia (`/wv-v1/license`, `/wv-v2/license`) validan token. Actualmente usa valor hardcoded `user_valid_token`. En producción, implementar JWT validation.

### CORS

CORS está configurado para permitir todos los orígenes (`*`). En producción, restringir:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://tu-dominio.com"],  # Restringir
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
