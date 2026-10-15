# Referencia de API

## Base URL

```
http://localhost:8000
```

En producción: `http://<server-ip>:8000`

---

## Health & Monitoring

### GET /health

Verifica el estado de todos los componentes.

**Response:** `200 OK` o `503 Service Unavailable`

```json
{
  "status": "UP",
  "api": "UP",
  "redis": "UP",
  "database": "UP",
  "healthy": true
}
```

### GET /api/stats

Estadísticas generales del sistema.

**Response:** `200 OK`

```json
{
  "total_keys": 150,
  "active_vip_users": 45,
  "total_vip_users": 52,
  "license_requests_24h": 1234
}
```

### GET /api/logs

Logs de actividad recientes.

**Parámetros:**
- `lines` (query, optional) — Número de líneas (default: 100, max: 5000)

**Response:** `200 OK`

```json
{
  "lines": 100,
  "total_lines": 5000,
  "content": "2026-09-21 10:00:00 - INFO - NUEVA: Canal hd-1 -> KID abc123..."
}
```

### GET /api/activity

Actividad de licencias.

**Parámetros:**
- `limit` (query, optional) — Límite de registros (default: 100, max: 1000)
- `user_id` (query, optional) — Filtrar por usuario

**Response:** `200 OK`

```json
{
  "count": 2,
  "activity": [
    {
      "id": 1,
      "user_id": "usr123",
      "kid": "abc123",
      "action": "license_granted",
      "ip_address": "192.168.1.100",
      "created_at": "2026-09-21T10:00:00"
    }
  ]
}
```

---

## Content Keys

### POST /kms/generate

Genera o recupera una content key para un canal.

**Request Body:**

```json
{
  "channel_id": "canal-hd-1"
}
```

**Response:** `200 OK`

```json
{
  "status": "created",
  "kid": "a1b2c3d4e5f67890123456789abcdef",
  "key": "00112233445566778899aabbccddeeff",
  "channel": "canal-hd-1"
}
```

**Valores de `status`:**
- `created` — Nueva key generada
- `retrieved` — Key desde caché Redis
- `retrieved_from_db` — Key desde MySQL

**Ejemplo curl:**

```bash
curl -X POST http://localhost:8000/kms/generate \
  -H "Content-Type: application/json" \
  -d '{"channel_id": "canal-hd-1"}'
```

### POST /api/keys/rotate

Rota la key de un canal (genera nueva, conserva anterior para VOD).

**Request Body:**

```json
{
  "channel_id": "canal-hd-1"
}
```

**Response:** `200 OK`

```json
{
  "status": "rotated",
  "kid": "new_kid_abc123",
  "key": "new_key_def456",
  "channel": "canal-hd-1",
  "previous_kid": "old_kid_xyz789"
}
```

**Ejemplo curl:**

```bash
curl -X POST http://localhost:8000/api/keys/rotate \
  -H "Content-Type: application/json" \
  -d '{"channel_id": "canal-hd-1"}'
```

### GET /api/keys

Lista las keys más recientes.

**Parámetros:**
- `limit` (query, optional) — Límite (default: 50, max: 500)

**Response:** `200 OK`

```json
{
  "count": 2,
  "keys": [
    {
      "pos": 1,
      "kid": "a1b2c3d4...",
      "channel_id": "canal-hd-1",
      "created_at": "2026-09-21T10:00:00"
    }
  ]
}
```

---

## Licencias Widevine

### POST /wv-v1/license

Endpoint de licencias Widevine v1.

**Request Body:**

```json
{
  "token": "user_valid_token",
  "kid": "a1b2c3d4e5f67890123456789abcdef",
  "challenge": "base64_encoded_challenge"
}
```

**Response:** `200 OK`

```json
{
  "license": "BASE64_SIGNED_WIDEVINE_LICENSE_PAYLOAD",
  "info": "Key retrieved from cache"
}
```

**Errores:**
- `403` — Token inválido
- `404` — KID no encontrado

### POST /wv-v2/license

Endpoint de licencias Widevine v2 (listo para integración).

**Request Body:** Igual que v1

**Response:** `200 OK`

```json
{
  "status": "Integration Ready",
  "message": "Listo para inyectar credenciales del proveedor DRM"
}
```

### POST /wv/license

Proxy completo al proveedor DRM. Recibe challenge binario.

**Headers:**
- `X-DRM-KID` — Key ID (requerido)
- `Content-Type: application/octet-stream`

**Request Body:** Challenge binario (octet-stream)

**Response:** `200 OK`
- Licencia firmada (application/octet-stream)

**Errores:**
- `400` — Falta header X-DRM-KID
- `404` — KID no encontrado
- `502` — Error del proveedor DRM

**Ejemplo curl:**

```bash
curl -X POST http://localhost:8000/wv/license \
  -H "X-DRM-KID: a1b2c3d4..." \
  -H "Content-Type: application/octet-stream" \
  --data-binary @challenge.bin
```

---

## VIP Users

### GET /api/vip/users

Lista usuarios VIP.

**Parámetros:**
- `status` (query, optional) — Filtrar por estado (`active`, `inactive`)
- `limit` (query, optional) — Límite (default: 100, max: 1000)

**Response:** `200 OK`

```json
{
  "count": 2,
  "users": [
    {
      "id": 1,
      "user_id": "usr123",
      "username": "Juan Pérez",
      "email": "juan@example.com",
      "max_screens": 3,
      "status": "active",
      "created_at": "2026-09-21T10:00:00"
    }
  ]
}
```

### GET /api/vip/users/{user_id}

Obtiene un usuario VIP específico.

**Response:** `200 OK` o `404 Not Found`

```json
{
  "id": 1,
  "user_id": "usr123",
  "username": "Juan Pérez",
  "email": "juan@example.com",
  "max_screens": 3,
  "status": "active"
}
```

### POST /api/vip/users

Crea un nuevo usuario VIP.

**Request Body:**

```json
{
  "user_id": "usr123",
  "username": "Juan Pérez",
  "email": "juan@example.com",
  "max_screens": 3
}
```

**Response:** `201 Created`

```json
{
  "status": "created",
  "user_id": "usr123"
}
```

**Errores:**
- `409` — Usuario ya existe

### PUT /api/vip/users/{user_id}

Actualiza un usuario VIP.

**Request Body:** (todos los campos son opcionales)

```json
{
  "username": "Juan C. Pérez",
  "email": "nuevo@example.com",
  "max_screens": 5,
  "status": "inactive"
}
```

**Response:** `200 OK`

```json
{
  "status": "updated",
  "user_id": "usr123"
}
```

### DELETE /api/vip/users/{user_id}

Elimina un usuario VIP.

**Response:** `200 OK`

```json
{
  "status": "deleted",
  "user_id": "usr123"
}
```

---

## CMS Webhook

### POST /api/cms/webhook

Webhook para sincronización desde CMS. Requiere autenticación.

**Headers:**
- `X-API-Key` — API key del CMS (requerido)

**Request Body:**

```json
{
  "user_id": "usr123",
  "username": "Juan Pérez",
  "email": "juan@example.com",
  "max_screens": 3,
  "action": "upsert"
}
```

**Valores de `action`:**
- `upsert` — Crear o actualizar
- `delete` — Eliminar usuario

**Response:** `200 OK`

```json
{
  "status": "upserted",
  "user_id": "usr123"
}
```

**Errores:**
- `403` — API key inválida

**Ejemplo curl:**

```bash
curl -X POST http://localhost:8000/api/cms/webhook \
  -H "X-API-Key: your-cms-api-key" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "usr123", "max_screens": 3, "action": "upsert"}'
```
