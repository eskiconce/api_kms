# Esquema de Base de Datos

## Motor

- **MySQL 8.x** (o compatible)
- **Database:** `drm_system`
- **User:** `drm_user`

## Tablas

### content_keys

Almacena las content keys DRM generadas para cada canal.

```sql
CREATE TABLE content_keys (
    kid VARCHAR(64) NOT NULL PRIMARY KEY,
    content_key VARCHAR(64) NOT NULL,
    channel_id VARCHAR(128) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_channel (channel_id)
);
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `kid` | VARCHAR(64) | Key ID (hex, 32 chars) — PK |
| `content_key` | VARCHAR(64) | Content key (hex, 32 chars) |
| `channel_id` | VARCHAR(128) | Identificador del canal |
| `created_at` | TIMESTAMP | Fecha de creación |

**Notas:**
- Se pueden tener múltiples keys por canal (historial para VOD)
- La key "activa" es la más reciente por `channel_id`
- KID y Key son generados como hex de 16 bytes (32 caracteres)

---

### vip_users

Usuarios VIP con límites de pantallas concurrentes.

```sql
CREATE TABLE vip_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL UNIQUE,
    username VARCHAR(128) NOT NULL DEFAULT '',
    email VARCHAR(128) NOT NULL DEFAULT '',
    max_screens INT NOT NULL DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    last_activity TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_status (status)
);
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | INT | Auto-increment PK |
| `user_id` | VARCHAR(64) | ID del usuario (externo, único) |
| `username` | VARCHAR(128) | Nombre del usuario |
| `email` | VARCHAR(128) | Email del usuario |
| `max_screens` | INT | Máximo de pantallas simultáneas |
| `status` | VARCHAR(20) | Estado: `active` / `inactive` |
| `last_activity` | TIMESTAMP | Última actividad |
| `created_at` | TIMESTAMP | Fecha de creación |
| `updated_at` | TIMESTAMP | Última actualización (auto) |

**Origen de datos:**
- Webhook CMS (`POST /api/cms/webhook`)
- API CRUD (`POST/PUT/DELETE /api/vip/users`)
- Migración inicial desde tabla `usuarios`

---

### license_activity

Log de actividad de entrega de licencias.

```sql
CREATE TABLE license_activity (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    kid VARCHAR(64) NOT NULL,
    action VARCHAR(32) NOT NULL,
    ip_address VARCHAR(45) DEFAULT '',
    device_info VARCHAR(255) DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user (user_id),
    INDEX idx_kid (kid),
    INDEX idx_created (created_at)
);
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | INT | Auto-increment PK |
| `user_id` | VARCHAR(64) | ID del usuario |
| `kid` | VARCHAR(64) | Key ID utilizada |
| `action` | VARCHAR(32 | Acción: `license_granted`, `key_generated`, etc. |
| `ip_address` | VARCHAR(45) | IP del cliente (IPv4/IPv6) |
| `device_info` | VARCHAR(255) | Info del dispositivo |
| `created_at` | TIMESTAMP | Timestamp del evento |

---

## Migración Inicial

Al iniciar la API, se ejecuta automáticamente:

1. **Creación de tablas** — `CREATE TABLE IF NOT EXISTS`
2. **Migración desde `usuarios`** — Copia usuarios existentes:

```sql
INSERT IGNORE INTO vip_users (user_id, username, max_screens)
SELECT user_id, user_id, limite_pantallas FROM usuarios
WHERE user_id IS NOT NULL;
```

## Redis Schema

Redis almacena datos de caché con TTL:

| Key Pattern | Valor | TTL |
|-------------|-------|-----|
| `drm:key:{kid}` | content_key | 6 horas (21600s) |
| `drm:active_channel:{channel_id}` | `{kid}:{key}` | 10 minutos (600s) |

## Consultas Comunes

### Keys activas por canal

```sql
SELECT kid, content_key, created_at
FROM content_keys
WHERE channel_id = 'canal-hd-1'
ORDER BY created_at DESC
LIMIT 1;
```

### Usuarios VIP activos

```sql
SELECT user_id, username, max_screens
FROM vip_users
WHERE status = 'active'
ORDER BY username;
```

### Actividad de licencias últimas 24h

```sql
SELECT COUNT(*) as total
FROM license_activity
WHERE created_at >= NOW() - INTERVAL 24 HOUR;
```
