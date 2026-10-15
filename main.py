import os
import binascii
import logging
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Response, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from redis import asyncio as aioredis
import aiomysql
import httpx
from datetime import datetime

logger = logging.getLogger("kms_logger")

REDIS_CONF = {
    "host": os.environ.get("REDIS_HOST", "localhost"),
    "port": int(os.environ.get("REDIS_PORT", "6379")),
    "db": int(os.environ.get("REDIS_DB", "0")),
}
MYSQL_CONF = {
    "host": os.environ.get("MYSQL_HOST", "localhost"),
    "user": os.environ.get("MYSQL_USER", "drm_user"),
    "password": os.environ.get("MYSQL_PASSWORD", "drm_pass_123"),
    "db": os.environ.get("MYSQL_DATABASE", "drm_system"),
}
DRM_PROVIDER_URL = os.environ.get("DRM_PROVIDER_URL", "https://35.234.128.244:8080/ConcurrentPlayback")
LOG_DIR = os.environ.get("LOG_DIR", "logs")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
CMS_API_KEY = os.environ.get("CMS_API_KEY", "a1b2c3d4e5f67890123456789abcdef0")

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=f"{LOG_DIR}/activity.log",
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

redis_pool: aioredis.ConnectionPool | None = None
mysql_pool: aiomysql.Pool | None = None
http_client: httpx.AsyncClient | None = None


async def _redis():
    if redis_pool is None:
        raise ConnectionError("Redis pool not initialized")
    return aioredis.Redis(connection_pool=redis_pool)


async def _ensure_tables():
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS content_keys (
                    kid VARCHAR(64) NOT NULL PRIMARY KEY,
                    content_key VARCHAR(64) NOT NULL,
                    channel_id VARCHAR(128) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_channel (channel_id)
                )
            """)
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS vip_users (
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
                )
            """)
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS license_activity (
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
                )
            """)
            await conn.commit()

            await cursor.execute("""
                INSERT IGNORE INTO vip_users (user_id, username, max_screens)
                SELECT user_id, user_id, limite_pantallas FROM usuarios
                WHERE user_id IS NOT NULL
            """)
            await conn.commit()


async def _get_key(kid: str, cache_ttl: int = 3600) -> tuple[str | None, str]:
    redis_ok = False
    try:
        r = await _redis()
        key = await r.get(f"drm:key:{kid}")
        if key:
            return key.decode(), "cache"
        redis_ok = True
    except Exception:
        logger.warning(f"Redis no disponible, fallback a MySQL directo")

    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT content_key FROM content_keys WHERE kid = %s", (kid,))
            result = await cursor.fetchone()
            if result:
                raw = result[0]
                key_str = raw.decode() if isinstance(raw, bytes) else raw
                if redis_ok:
                    try:
                        r = await _redis()
                        await r.setex(f"drm:key:{kid}", cache_ttl, key_str)
                    except Exception:
                        pass
                return key_str, "database"
    return None, "none"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_pool, mysql_pool, http_client
    try:
        redis_pool = aioredis.ConnectionPool(**REDIS_CONF, max_connections=20)
        r = aioredis.Redis(connection_pool=redis_pool)
        await r.ping()
        logger.info("Redis conectado OK")
    except Exception as e:
        logger.warning(f"Redis no disponible al iniciar: {e}. Se usara MySQL como fallback.")
        redis_pool = None

    mysql_pool = await aiomysql.create_pool(**MYSQL_CONF, minsize=2, maxsize=10, autocommit=True)
    await _ensure_tables()
    http_client = httpx.AsyncClient(timeout=30.0, verify=False)
    logger.info("KMS API iniciada correctamente")
    yield
    if redis_pool:
        await redis_pool.disconnect()
    mysql_pool.close()
    await mysql_pool.wait_closed()
    await http_client.aclose()


app = FastAPI(title="MundoGo KMS API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────
# HEALTH
# ──────────────────────────────────────────
@app.get("/health")
async def health():
    statuses = {"status": "UP", "api": "UP"}
    healthy = True
    try:
        r = await _redis()
        await r.ping()
        statuses["redis"] = "UP"
    except Exception:
        statuses["redis"] = "DOWN"
        healthy = False
    try:
        async with mysql_pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT 1")
        statuses["database"] = "UP"
    except Exception:
        statuses["database"] = "DOWN"
        healthy = False
    statuses["healthy"] = healthy
    return JSONResponse(content=statuses, status_code=200 if healthy else 503)


# ──────────────────────────────────────────
# MODELS
# ──────────────────────────────────────────
class KeyRequest(BaseModel):
    channel_id: str


class LicenseRequest(BaseModel):
    token: str
    kid: str
    challenge: str


class VipUserCreate(BaseModel):
    user_id: str
    username: str = ""
    email: str = ""
    max_screens: int = 1


class VipUserUpdate(BaseModel):
    username: str | None = None
    email: str | None = None
    max_screens: int | None = None
    status: str | None = None


class CmsWebhookPayload(BaseModel):
    user_id: str
    username: str = ""
    email: str = ""
    max_screens: int = 1
    action: str = "upsert"


def generate_hex(length=16):
    return binascii.hexlify(os.urandom(length)).decode()


# ──────────────────────────────────────────
# CONTENT KEYS
# ──────────────────────────────────────────
@app.post("/kms/generate")
async def kms_generate(req: KeyRequest):
    try:
        r = None
        redis_ok = False
        try:
            r = await _redis()
            active = await r.get(f"drm:active_channel:{req.channel_id}")
            if active:
                kid, key = active.decode().split(":")
                logger.info(f"CACHE: Canal {req.channel_id} -> KID {kid}")
                return {"status": "retrieved", "kid": kid, "key": key, "channel": req.channel_id}
            redis_ok = True
        except Exception:
            logger.warning(f"Redis no disponible durante generate, usando MySQL directo")

        async with mysql_pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT kid, content_key FROM content_keys WHERE channel_id = %s ORDER BY created_at DESC LIMIT 1",
                    (req.channel_id,)
                )
                result = await cursor.fetchone()
                if result:
                    kid, key_raw = result
                    key = key_raw.decode() if isinstance(key_raw, bytes) else key_raw
                    if redis_ok:
                        await r.setex(f"drm:key:{kid}", 21600, key)
                        await r.setex(f"drm:active_channel:{req.channel_id}", 600, f"{kid}:{key}")
                    logger.info(f"MySQL: Canal {req.channel_id} -> KID {kid}")
                    return {"status": "retrieved_from_db", "kid": kid, "key": key, "channel": req.channel_id}

                kid = generate_hex()
                key = generate_hex()
                await cursor.execute(
                    "INSERT INTO content_keys (kid, content_key, channel_id) VALUES (%s, %s, %s)",
                    (kid, key, req.channel_id)
                )
                await conn.commit()

        if redis_ok:
            await r.setex(f"drm:key:{kid}", 21600, key)
            await r.setex(f"drm:active_channel:{req.channel_id}", 600, f"{kid}:{key}")
        logger.info(f"NUEVA: Canal {req.channel_id} -> KID {kid}")
        return {"status": "created", "kid": kid, "key": key, "channel": req.channel_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"KMS {req.channel_id}: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor KMS")


@app.post("/api/keys/rotate")
async def rotate_key(req: KeyRequest):
    try:
        channel_id = req.channel_id
        new_kid = generate_hex()
        new_key = generate_hex()

        async with mysql_pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT kid FROM content_keys WHERE channel_id = %s ORDER BY created_at DESC LIMIT 1",
                    (channel_id,)
                )
                old_row = await cursor.fetchone()
                prev_kid = old_row[0].decode() if old_row and isinstance(old_row[0], bytes) else (old_row[0] if old_row else None)

                # INSERT nueva fila (la anterior se conserva para VOD)
                await cursor.execute(
                    "INSERT INTO content_keys (kid, content_key, channel_id) VALUES (%s, %s, %s)",
                    (new_kid, new_key, channel_id)
                )
                await conn.commit()

        # Actualizar Redis: mantener key vieja en cache (sigue siendo valida),
        # solo actualizar el canal activo para que nuevos packagers tomen la nueva
        try:
            r = await _redis()
            await r.setex(f"drm:key:{new_kid}", 21600, new_key)
            await r.setex(f"drm:active_channel:{channel_id}", 600, f"{new_kid}:{new_key}")
        except Exception:
            pass

        logger.info(f"ROTADA: Canal {channel_id} -> Nuevo KID {new_kid} (anterior {prev_kid or 'ninguno'})")
        return {"status": "rotated", "kid": new_kid, "key": new_key, "channel": channel_id, "previous_kid": prev_kid}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ROTATE {req.channel_id}: {e}")
        raise HTTPException(status_code=500, detail="Error interno rotando llave")


@app.get("/api/keys")
async def list_keys(limit: int = Query(50, ge=1, le=500)):
    async with mysql_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT @rownum := @rownum + 1 AS pos, kid, channel_id, created_at FROM content_keys, (SELECT @rownum := 0) r ORDER BY created_at DESC LIMIT %s", (limit,))
            rows = await cursor.fetchall()
            for r in rows:
                if r.get('created_at'):
                    r['created_at'] = r['created_at'].isoformat() if hasattr(r['created_at'], 'isoformat') else str(r['created_at'])
            return {"count": len(rows), "keys": rows}


# ──────────────────────────────────────────
# VIP USERS CRUD
# ──────────────────────────────────────────
@app.get("/api/vip/users")
async def list_vip_users(status: str | None = None, limit: int = Query(100, ge=1, le=1000)):
    async with mysql_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            if status:
                await cursor.execute("SELECT * FROM vip_users WHERE status = %s ORDER BY username ASC LIMIT %s", (status, limit))
            else:
                await cursor.execute("SELECT * FROM vip_users ORDER BY username ASC LIMIT %s", (limit,))
            rows = await cursor.fetchall()
            for r in rows:
                for k in ('created_at', 'updated_at', 'last_activity'):
                    if r.get(k):
                        r[k] = r[k].isoformat() if hasattr(r[k], 'isoformat') else str(r[k])
            return {"count": len(rows), "users": rows}


@app.get("/api/vip/users/{user_id}")
async def get_vip_user(user_id: str):
    async with mysql_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT * FROM vip_users WHERE user_id = %s", (user_id,))
            row = await cursor.fetchone()
            if not row:
                raise HTTPException(404, "Usuario VIP no encontrado")
            for k in ('created_at', 'updated_at', 'last_activity'):
                if row.get(k):
                    row[k] = row[k].isoformat() if hasattr(row[k], 'isoformat') else str(row[k])
            return row


@app.post("/api/vip/users")
async def create_vip_user(req: VipUserCreate):
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            try:
                await cursor.execute(
                    "INSERT INTO vip_users (user_id, username, email, max_screens) VALUES (%s, %s, %s, %s)",
                    (req.user_id, req.username, req.email, req.max_screens)
                )
                await conn.commit()
                logger.info(f"VIP creado: user_id={req.user_id} screens={req.max_screens}")
                return {"status": "created", "user_id": req.user_id}
            except Exception as e:
                if "Duplicate" in str(e):
                    raise HTTPException(409, f"El usuario {req.user_id} ya existe")
                raise HTTPException(500, f"Error creando usuario VIP: {e}")


@app.put("/api/vip/users/{user_id}")
async def update_vip_user(user_id: str, req: VipUserUpdate):
    updates = {}
    if req.username is not None:
        updates["username"] = req.username
    if req.email is not None:
        updates["email"] = req.email
    if req.max_screens is not None:
        updates["max_screens"] = req.max_screens
    if req.status is not None:
        updates["status"] = req.status
    if not updates:
        raise HTTPException(400, "No hay campos para actualizar")

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [user_id]
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(f"UPDATE vip_users SET {set_clause} WHERE user_id = %s", values)
            await conn.commit()
            if cursor.rowcount == 0:
                raise HTTPException(404, "Usuario VIP no encontrado")
            logger.info(f"VIP actualizado: user_id={user_id} campos={list(updates.keys())}")
            return {"status": "updated", "user_id": user_id}


@app.delete("/api/vip/users/{user_id}")
async def delete_vip_user(user_id: str):
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("DELETE FROM vip_users WHERE user_id = %s", (user_id,))
            await conn.commit()
            if cursor.rowcount == 0:
                raise HTTPException(404, "Usuario VIP no encontrado")
            logger.info(f"VIP eliminado: user_id={user_id}")
            return {"status": "deleted", "user_id": user_id}


# ──────────────────────────────────────────
# CMS WEBHOOK
# ──────────────────────────────────────────
@app.post("/api/cms/webhook")
async def cms_webhook(req: CmsWebhookPayload, request: Request):
    api_key = request.headers.get("X-API-Key", "")
    if api_key != CMS_API_KEY:
        logger.warning(f"Intento de webhook con API key invalida: {api_key[:10]}...")
        raise HTTPException(403, "API Key invalida")

    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            if req.action == "delete":
                await cursor.execute("DELETE FROM vip_users WHERE user_id = %s", (req.user_id,))
                await conn.commit()
                logger.info(f"CMS webhook: eliminado user_id={req.user_id}")
                return {"status": "deleted", "user_id": req.user_id}

            await cursor.execute(
                """INSERT INTO vip_users (user_id, username, email, max_screens)
                   VALUES (%s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE username=VALUES(username), email=VALUES(email),
                   max_screens=VALUES(max_screens), status='active'""",
                (req.user_id, req.username, req.email, req.max_screens)
            )
            await conn.commit()
            logger.info(f"CMS webhook: upsert user_id={req.user_id} screens={req.max_screens}")
            return {"status": "upserted", "user_id": req.user_id}


# ──────────────────────────────────────────
# LICENSE ENDPOINTS
# ──────────────────────────────────────────
@app.post("/wv-v1/license")
async def wv_proxy_v1(req: LicenseRequest):
    try:
        if req.token != "user_valid_token":
            logger.warning(f"Token invalido KID={req.kid}")
            raise HTTPException(status_code=403, detail="Token invalido")

        key, source = await _get_key(req.kid)
        if not key:
            logger.error(f"KID {req.kid} no encontrado")
            raise HTTPException(status_code=404, detail="Key ID no encontrado")

        logger.info(f"V1: KID {req.kid} servido desde {source}")
        return {"license": "BASE64_SIGNED_WIDEVINE_LICENSE_PAYLOAD", "info": f"Key retrieved from {source}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"V1: KID {req.kid} -> {e}")
        raise HTTPException(status_code=500, detail="Error en servidor de licencias")


@app.post("/wv-v2/license")
async def wv_proxy_v2(req: LicenseRequest):
    try:
        if req.token != "user_valid_token":
            logger.warning(f"Token invalido KID={req.kid}")
            raise HTTPException(status_code=403, detail="Token invalido")

        key, source = await _get_key(req.kid)
        if not key:
            logger.error(f"KID {req.kid} no encontrado")
            raise HTTPException(status_code=404, detail="Key ID no encontrado")

        logger.info(f"V2: KID {req.kid} desde {source}. Listo para firmar con proveedor DRM.")
        return {"status": "Integration Ready", "message": "Listo para inyectar credenciales del proveedor DRM"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"V2: {e}")
        raise HTTPException(status_code=500, detail="Error en servidor de licencias")


@app.post("/wv/license")
async def wv_proxy(request: Request):
    try:
        kid = request.headers.get("X-DRM-KID")
        if not kid:
            logger.error("Falta X-DRM-KID header")
            raise HTTPException(status_code=400, detail="Missing X-DRM-KID header")

        challenge_bytes = await request.body()
        logger.info(f"Challenge para KID {kid}, {len(challenge_bytes)} bytes")

        key, source = await _get_key(kid)
        if not key:
            logger.error(f"KID {kid} no encontrado")
            raise HTTPException(status_code=404, detail="Key ID no encontrado")

        logger.info(f"Key desde {source}. Contactando proveedor DRM...")
        headers = {"Content-Type": "application/octet-stream"}
        respuesta = await http_client.post(DRM_PROVIDER_URL, content=challenge_bytes, headers=headers, timeout=30.0)

        if respuesta.status_code == 200:
            logger.info(f"Proveedor OK. Entregando licencia ({len(respuesta.content)} bytes)")
            return Response(content=respuesta.content, media_type="application/octet-stream")
        else:
            logger.error(f"Proveedor error {respuesta.status_code}: {respuesta.text[:200]}")
            raise HTTPException(status_code=502, detail="Error del proveedor (Bad Gateway)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WV: {e}")
        raise HTTPException(status_code=500, detail="Error interno en el servidor proxy de licencias")


# ──────────────────────────────────────────
# LOGS
# ──────────────────────────────────────────
@app.get("/api/logs")
async def get_logs(lines: int = Query(100, ge=1, le=5000)):
    log_file = f"{LOG_DIR}/activity.log"
    if not os.path.exists(log_file):
        return {"lines": 0, "content": ""}
    try:
        with open(log_file, "r") as f:
            all_lines = f.readlines()
        last_lines = all_lines[-lines:]
        return {"lines": len(last_lines), "total_lines": len(all_lines), "content": "".join(last_lines)}
    except Exception as e:
        raise HTTPException(500, f"Error leyendo logs: {e}")


# ──────────────────────────────────────────
# LICENSE ACTIVITY
# ──────────────────────────────────────────
@app.get("/api/activity")
async def list_activity(limit: int = Query(100, ge=1, le=1000), user_id: str | None = None):
    async with mysql_pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            if user_id:
                await cursor.execute(
                    "SELECT * FROM license_activity WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
                    (user_id, limit)
                )
            else:
                await cursor.execute(
                    "SELECT * FROM license_activity ORDER BY created_at DESC LIMIT %s", (limit,)
                )
            rows = await cursor.fetchall()
            for r in rows:
                if r.get('created_at'):
                    r['created_at'] = r['created_at'].isoformat() if hasattr(r['created_at'], 'isoformat') else str(r['created_at'])
            return {"count": len(rows), "activity": rows}


# ──────────────────────────────────────────
# DASHBOARD STATS
# ──────────────────────────────────────────
@app.get("/api/stats")
async def kms_stats():
    async with mysql_pool.acquire() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT COUNT(*) FROM content_keys")
            total_keys = (await cursor.fetchone())[0]
            await cursor.execute("SELECT COUNT(*) FROM vip_users WHERE status = 'active'")
            active_vip = (await cursor.fetchone())[0]
            await cursor.execute("SELECT COUNT(*) FROM vip_users")
            total_vip = (await cursor.fetchone())[0]
            await cursor.execute("SELECT COUNT(*) FROM license_activity WHERE created_at >= NOW() - INTERVAL 24 HOUR")
            act_24h = (await cursor.fetchone())[0]
            return {
                "total_keys": total_keys,
                "active_vip_users": active_vip,
                "total_vip_users": total_vip,
                "license_requests_24h": act_24h,
            }
