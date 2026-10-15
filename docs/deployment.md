# Despliegue

## Servidor de Producción

- **IP:** 172.16.222.240
- **User:** oymservice
- **Ruta:** `/opt/kms`
- **Service:** `kms-api.service`

---

## Proceso de Deploy

### Usando Script Automático

```bash
# Deploy de main.py (default)
./deploy-kms.sh

# Deploy de archivo específico
./deploy-kms.sh main.py

# Solo verificar conexión
./deploy-kms.sh --test
```

Con expect (automatiza password prompt):

```bash
./deploy-kms.exp "tu_password_sudo" main.py
```

### Deploy Manual

```bash
# 1. Subir archivo
scp main.py oymservice@172.16.222.240:/tmp/main.py

# 2. Conectar y instalar
ssh oymservice@172.16.222.240

# 3. Respaldo
sudo cp /opt/kms/main.py /opt/kms/backups/main.py.$(date +%Y%m%d_%H%M%S).bak

# 4. Instalar
sudo mv /tmp/main.py /opt/kms/main.py

# 5. Verificar sintaxis
sudo python3 -m py_compile /opt/kms/main.py

# 6. Reiniciar servicio
sudo systemctl restart kms-api.service

# 7. Verificar
sudo systemctl status kms-api.service
```

---

## Estructura del Servidor

```
/opt/kms/
├── main.py              # Aplicación principal
├── .env                 # Variables de entorno (no en git)
├── logs/                # Logs de actividad
│   └── activity.log
├── backups/             # Respaldos automáticos
│   └── main.py.*.bak
├── venv/                # Entorno virtual Python
└── __pycache__/
```

---

## Systemd Service

### /etc/systemd/system/kms-api.service

```ini
[Unit]
Description=KMS API Service
After=network.target

[Service]
User=oymservice
WorkingDirectory=/opt/kms
ExecStart=/opt/kms/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
EnvironmentFile=/opt/kms/.env

[Install]
WantedBy=multi-user.target
```

### Comandos Útiles

```bash
# Ver estado
sudo systemctl status kms-api.service

# Reiniciar
sudo systemctl restart kms-api.service

# Detener
sudo systemctl stop kms-api.service

# Ver logs
sudo journalctl -u kms-api.service -f
```

---

## Verificación Post-Deploy

### 1. Health Check

```bash
curl http://172.16.222.240:8000/health
```

Esperar: `{"status": "UP", "healthy": true, ...}`

### 2. Generar Key de Prueba

```bash
curl -X POST http://172.16.222.240:8000/kms/generate \
  -H "Content-Type: application/json" \
  -d '{"channel_id": "test-deploy-check"}'
```

### 3. Verificar Logs

```bash
tail -20 /opt/kms/logs/activity.log
```

---

## Rollback

Si el deploy causa problemas:

```bash
# 1. Detener servicio
sudo systemctl stop kms-api.service

# 2. Restaurar último backup
ls -la /opt/kms/backups/
sudo cp /opt/kms/backups/main.py.TIMESTAMP.bak /opt/kms/main.py

# 3. Reiniciar
sudo systemctl start kms-api.service
```

---

## Instalación Inicial (Nuevo Servidor)

### 1. Preparar Sistema

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3.11 python3.11-venv python3-pip -y
```

### 2. Crear Directorios

```bash
sudo mkdir -p /opt/kms/logs /opt/kms/backups
sudo chown -R oymservice:oymservice /opt/kms
```

### 3. Entorno Virtual

```bash
cd /opt/kms
python3.11 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn redis aiomysql httpx pydantic
```

### 4. Configurar Variables

```bash
nano /opt/kms/.env
# Llenar con valores de producción
```

### 5. Instalar Service

```bash
sudo nano /etc/systemd/system/kms-api.service
# Copiar contenido del template de arriba
sudo systemctl daemon-reload
sudo systemctl enable kms-api.service
sudo systemctl start kms-api.service
```

### 6. Verificar

```bash
curl http://localhost:8000/health
```
