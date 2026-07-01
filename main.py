import os
import binascii
import redis
import logging
import requests
import json
import mysql.connector
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Response, Request
from pydantic import BaseModel

# --- CONFIGURACIÓN DE LOGS ---
# Esto creará un archivo llamado api_activity.log en la misma carpeta
logging.basicConfig(
    filename='logs/activity.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("kms_logger")

app = FastAPI(title="Widevine DRM PoC - Nativos")


# --- NUEVO: CONFIGURACIÓN CORS ---
# Esto le dice al navegador "Sí, permito que reproductores web me pidan licencias"
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, aquí pondrías "https://tu-ott.com"
    allow_credentials=True,
    allow_methods=["*"],  # Permite POST y OPTIONS
    allow_headers=["*"],  # Permite cabeceras personalizadas de Widevine
)

# --- CONFIGURACIONES ---
REDIS_CONF = {"host": "localhost", "port": 6379, "db": 0}
MYSQL_CONF = {
    "host": "localhost", "user": "drm_user", 
    "password": "drm_pass_123", "database": "drm_system"
}

cache = redis.Redis(**REDIS_CONF)

def get_db_conn():
    return mysql.connector.connect(**MYSQL_CONF)

class KeyRequest(BaseModel):
    channel_id: str

class LicenseRequest(BaseModel):
    token: str
    kid: str
    challenge: str

def generate_hex(length=16):
    return binascii.hexlify(os.urandom(length)).decode()

# --- SERVICIO 1: KMS (USADO POR PACKAGERS) ---

# -------- version 1
# @app.post("/kms/generate")
# async def kms_generate(req: KeyRequest):
#     try:
#         active_key_cache = cache.get(f"drm:active_channel:{req.channel_id}")
        
#         if active_key_cache:
#             kid, key = active_key_cache.decode('utf-8').split(":")
#             logger.info(f"LLAVE EXISTENTE: Canal {req.channel_id} recuperada de caché. KID: {kid}")
#             return {"status": "retrieved", "kid": kid, "key": key, "channel": req.channel_id}

#         kid = generate_hex()
#         key = generate_hex()
        
#         conn = get_db_conn()
#         cursor = conn.cursor()
#         cursor.execute(
#             "INSERT INTO content_keys (kid, content_key, channel_id) VALUES (%s, %s, %s)",
#             (kid, key, req.channel_id)
#         )
#         conn.commit()
#         cursor.close()
#         conn.close()

#         cache.setex(f"drm:key:{kid}", 21600, key)
#         cache.setex(f"drm:active_channel:{req.channel_id}", 600, f"{kid}:{key}")
        
#         logger.info(f"NUEVA LLAVE: Generada para {req.channel_id}. KID: {kid} --> Guardada en MySQL y Redis.")
#         return {"status": "created", "kid": kid, "key": key, "channel": req.channel_id}

#     except Exception as e:
#         logger.error(f"ERROR EN KMS: Fallo al generar llave para {req.channel_id} Detalle: {str(e)}")
#         raise HTTPException(status_code=500, detail="Error interno del servidor KMS")

# --------- version 2 04.may.26  21.00 hrs
@app.post("/kms/generate")
async def kms_generate(req: KeyRequest):
    try:
        # --- PASO 1: Buscar en Redis (Caché Rápida) ---
        active_key_cache = cache.get(f"drm:active_channel:{req.channel_id}")
        
        if active_key_cache:
            kid, key = active_key_cache.decode('utf-8').split(":")
            logger.info(f"LLAVE EXISTENTE: Canal {req.channel_id} recuperada de caché. KID: {kid}")
            return {"status": "retrieved", "kid": kid, "key": key, "channel": req.channel_id}

        # --- PASO 2: Buscar en MySQL (Respaldo) ---
        conn = get_db_conn()
        cursor = conn.cursor()
        # Buscamos si ya existe una llave para este canal en la BD
        cursor.execute("SELECT kid, content_key FROM content_keys WHERE channel_id = %s LIMIT 1", (req.channel_id,))
        result = cursor.fetchone()
        
        if result:
            kid = result[0]
            # Decodificamos si la base de datos lo retorna en formato binario
            key = result[1].decode('utf-8') if isinstance(result[1], bytes) else result[1]
            
            # Restauramos la llave en Redis para no golpear MySQL en las siguientes peticiones
            cache.setex(f"drm:key:{kid}", 21600, key)
            cache.setex(f"drm:active_channel:{req.channel_id}", 600, f"{kid}:{key}")
            
            logger.info(f"LLAVE EXISTENTE: Canal {req.channel_id} recuperada de MySQL (restaurada en caché). KID: {kid}")
            
            cursor.close()
            conn.close()
            return {"status": "retrieved_from_db", "kid": kid, "key": key, "channel": req.channel_id}

        # --- PASO 3: Solo si NO existe en caché ni en BD, generamos una NUEVA ---
        kid = generate_hex()
        key = generate_hex()
        
        cursor.execute(
            "INSERT INTO content_keys (kid, content_key, channel_id) VALUES (%s, %s, %s)",
            (kid, key, req.channel_id)
        )
        conn.commit()
        cursor.close()
        conn.close()

        # Guardamos la nueva llave en caché
        cache.setex(f"drm:key:{kid}", 21600, key)
        cache.setex(f"drm:active_channel:{req.channel_id}", 600, f"{kid}:{key}")
        
        logger.info(f"NUEVA LLAVE: Generada para {req.channel_id}. KID: {kid} --> Guardada en MySQL y Redis.")
        return {"status": "created", "kid": kid, "key": key, "channel": req.channel_id}

    except Exception as e:
        logger.error(f"ERROR EN KMS: Fallo al generar/recuperar llave para {req.channel_id} Detalle: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor KMS")

@app.post("/wv-v1/license")
async def wv_proxy(req: LicenseRequest):
    try:
        if not req.token == "user_valid_token":
            logger.warning(f"ACCESO DENEGADO: Token inválido proporcionado. KID solicitado: {req.kid}")
            raise HTTPException(status_code=403, detail="Token inválido")

        key = cache.get(f"drm:key:{req.kid}")
        source = "cache"

        if not key:
            conn = get_db_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT content_key FROM content_keys WHERE kid = %s", (req.kid,))
            result = cursor.fetchone()
            if result:
                key = result[0].encode() if isinstance(result[0], str) else result[0]
                source = "database"
                cache.setex(f"drm:key:{req.kid}", 3600, key)
            conn.close()

        if not key:
            logger.error(f"KEY NOT FOUND: El KID {req.kid} no existe en ninguna base de datos.")
            raise HTTPException(status_code=404, detail="Key ID no encontrado")
        
        logger.info(f"LICENCIA ENTREGADA: KID {req.kid} servido desde {source}.")
        return {"license": "BASE64_SIGNED_WIDEVINE_LICENSE_PAYLOAD", "info": f"Key retrieved from {source}"}

    except Exception as e:
        logger.error(f"ERROR EN PROXY: Fallo al procesar licencia para KID {req.kid}. Detalle: {str(e)}")
        raise HTTPException(status_code=500, detail="Error en servidor de licencias")

@app.post("/wv-v2/license")
async def wv_proxy(req: LicenseRequest):
    try:
        # 1. Validación de tu usuario (Entitlements)
        if not req.token == "user_valid_token":
            logger.warning(f"ACCESO DENEGADO: Token inválido. KID: {req.kid}")
            raise HTTPException(status_code=403, detail="Token inválido")

        # 2. Búsqueda de la llave en Redis/MySQL
        key = cache.get(f"drm:key:{req.kid}")
        source = "cache"

        if not key:
            conn = get_db_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT content_key FROM content_keys WHERE kid = %s", (req.kid,))
            result = cursor.fetchone()
            if result:
                key = result[0].encode() if isinstance(result[0], str) else result[0]
                source = "database"
                cache.setex(f"drm:key:{req.kid}", 3600, key)
            conn.close()

        if not key:
            logger.error(f"KEY NOT FOUND: El KID {req.kid} no existe.")
            raise HTTPException(status_code=404, detail="Key ID no encontrado")

        # 3. COMUNICACIÓN CON EL PROVEEDOR DRM EXTERNO (Notario)
        key_str = key.decode('utf-8') if isinstance(key, bytes) else key
        
        logger.info(f"KID {req.kid} encontrado en {source}. Solicitando firma a DRM Provider...")

        # --- LÓGICA DE INTEGRACIÓN (Ejemplo genérico BYOK) ---
        # En la vida real, aquí usas el SDK/Token de Axinom o PallyCon.
        # Proveedor_URL = "https://drm-widevine-licensing.axinom.com/AcquireLicense"
        
        # Para evitar que el código falle sin una cuenta real, vamos a simular 
        # el reenvío HTTP exacto que harías hacia el proveedor:
        
        """
        # CÓDIGO REAL DE PRODUCCIÓN (Comentado hasta que tengas la cuenta)
        headers = {
            "X-AxDRM-Message": "TU_TOKEN_JWT_GENERADO_CON_EL_KID_Y_LA_KEY",
            "Content-Type": "application/octet-stream"
        }
        
        # req.challenge viene en base64 desde nuestro HTML, lo decodificamos a bytes
        challenge_bytes = binascii.a2b_base64(req.challenge)
        
        drm_response = requests.post(Proveedor_URL, data=challenge_bytes, headers=headers)
        
        if drm_response.status_code == 200:
            logger.info("Firma exitosa. Entregando licencia binaria al reproductor.")
            # DEVOLVEMOS BYTES PUROS AL REPRODUCTOR
            return Response(content=drm_response.content, media_type="application/octet-stream")
        else:
            logger.error(f"Error del Proveedor DRM: {drm_response.text}")
            raise HTTPException(status_code=500, detail="Fallo en la firma de la licencia")
        """
        
        # MOCK DE RESPUESTA PARA LA POC (Para que la API no colapse hoy)
        return {"status": "Integration Ready", "message": "Código listo para inyectar credenciales del proveedor DRM"}

    except Exception as e:
        logger.error(f"ERROR EN PROXY: {str(e)}")
        raise HTTPException(status_code=500, detail="Error en servidor de licencias")

@app.post("/wv/license")
async def wv_proxy(request: Request):
    try:
        # 1. Extraemos el KID que nos envía el Shaka Player en la cabecera
        kid = request.headers.get("X-DRM-KID")
        if not kid:
            logger.error("Petición rechazada: Falta el header X-DRM-KID")
            raise HTTPException(status_code=400, detail="Missing X-DRM-KID header")

        # 2. Leemos los BYTES CRUDOS del Challenge de Widevine
        challenge_bytes = await request.body()

        logger.info(f"Challenge binario recibido para KID: {kid}. Tamaño: {len(challenge_bytes)} bytes.")

        # 3. Buscamos la KEY secreta en nuestra base de datos (Cache o MySQL)
        key = cache.get(f"drm:key:{kid}")
        source = "cache"

        if not key:
            conn = get_db_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT content_key FROM content_keys WHERE kid = %s", (kid,))
            result = cursor.fetchone()
            if result:
                key = result[0].encode() if isinstance(result[0], str) else result[0]
                source = "database"
                cache.setex(f"drm:key:{kid}", 3600, key)
            conn.close()

        if not key:
            logger.error(f"KEY NOT FOUND: El KID {kid} no existe en la base de datos.")
            raise HTTPException(status_code=404, detail="Key ID no encontrado")

        key_str = key.decode('utf-8') if isinstance(key, bytes) else key
        logger.info(f"Llave secreta recuperada desde {source}. Conectando con Proveedor DRM...")

        # =====================================================================
        # 4. COMUNICACIÓN CON EL PROVEEDOR DRM EXTERNO
        # =====================================================================
        # Reemplaza esta variable con el link que obtuviste
        DRM_PROVIDER_URL = "https://35.234.128.244:8080/ConcurrentPlayback"

        # Dependiendo de tu proveedor (Axinom, PallyCon, etc.), te pedirán 
        # enviar la llave secreta en los Headers o como parámetros en la URL.
        # Aquí configuramos las cabeceras estándar para enviar el Challenge.
        headers = {
            "Content-Type": "application/octet-stream", # Le decimos que mandamos binario
            # "X-Custom-Key": key_str, # <--- Descomenta y ajusta si el proveedor pide la llave en el header
            # "Authorization": "Bearer TU_TOKEN_DE_PROVEEDOR" # <--- Si requiere token
        }

        # Enviamos el Challenge binario al servidor Widevine certificado
        respuesta_proveedor = requests.post(
            DRM_PROVIDER_URL,
            data=challenge_bytes,
            headers=headers,
            timeout=10, # Buena práctica para evitar que el proxy se quede colgado
            verify=False
        )

        # 5. Entregamos la licencia al reproductor
        if respuesta_proveedor.status_code == 200:

        # --- AGREGA ESTA LÍNEA PARA VER EL FORMATO ---
            logger.info(f"Respuesta cruda del proveedor (primeros 200 char): {respuesta_proveedor.text[:200]}")

            logger.info("¡Licencia firmada exitosamente por el proveedor! Entregando al reproductor.")
            # Widevine necesita que le devolvamos los bytes exactamente como llegaron
            return Response(
                content=respuesta_proveedor.content,
                media_type="application/octet-stream"
            )
        else:
            logger.error(f"El proveedor DRM rechazó la firma. Status: {respuesta_proveedor.status_code}. Detalle: {respuesta_proveedor.text}")
            raise HTTPException(status_code=502, detail="Error del proveedor (Bad Gateway)")

    except Exception as e:
        logger.error(f"ERROR FATAL EN PROXY: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno en el servidor proxy de licencias")