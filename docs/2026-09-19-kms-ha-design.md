# KMS HA Design - Active/Standby con Keepalived + VIP

**Fecha:** 2026-09-19
**Estado:** Aprobado
**Autor:** Edmundocuevas

---

## 1. Resumen Ejecutivo

Diseñar alta disponibilidad (HA) para la API KMS de MundoGo utilizando **Keepalived + VIP** para failover automático entre dos servidores (activo/standby).

## 2. Objetivos

- **Disponibilidad:** 99.9% uptime (< 8.76 horas downtime/año)
- **Failover automático:** < 5 segundos de interrupción
- **Simplicidad:** Mínimo de componentes nuevos
- **Sin cambios significativos** en la lógica de negocio existente

## 3. Arquitectura Actual

```
┌─────────────────────────────────────────┐
│           KMS Server (172.16.222.240)   │
│  ┌─────────────────────────────────┐   │
│  │  FastAPI (main.py)              │   │
│  │  - /health                      │   │
│  │  - /kms/generate                │   │
│  │  - /wv/license                  │   │
│  │  - /api/vip/users               │   │
│  └─────────────────────────────────┘   │
│                                         │
│  ┌──────────────┐  ┌──────────────┐   │
│  │    Redis     │  │    MySQL     │   │
│  │  (local)     │  │  (local)     │   │
│  └──────────────┘  └──────────────┘   │
└─────────────────────────────────────────┘
```

**Problema:** Punto único de falla.

## 4. Arquitectura Propuesta (HA)

```
                        ┌─────────────────┐
                        │   VIP           │
                        │ 172.16.222.250  │
                        └────────┬────────┘
                                 │
            ┌────────────────────┴────────────────────┐
            │                                         │
   ┌────────▼────────┐                   ┌───────────▼──────────┐
   │  KMS Server A   │                   │  KMS Server B        │
   │  172.16.222.241 │                   │  172.16.222.242      │
   │  MASTER         │◄─────────────────►│  BACKUP               │
   │  (keepalived)   │    heartbeat      │  (keepalived)         │
   └────────┬────────┘                   └───────────┬──────────┘
            │                                         │
            └────────────────────┬────────────────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            │                    │                    │
   ┌────────▼────────┐  ┌───────▼───────┐  ┌────────▼────────┐
   │  Redis Externo  │  │ MySQL Externo │  │  Proveedor DRM  │
   │  (HA propio)    │  │ (HA propio)   │  │  (externo)      │
   └─────────────────┘  └───────────────┘  └─────────────────┘
```

## 5. Especificación de Componentes

### 5.1 Servidores

| Componente | IP | Rol | OS |
|-----------|-----|-----|-----|
| **KMS Server A** | 172.16.222.241 | Activo (MASTER) | Ubuntu 22.04 |
| **KMS Server B** | 172.16.222.242 | Standby (BACKUP) | Ubuntu 22.04 |
| **VIP** | 172.16.222.250 | Flotante | - |

### 5.2 Software por Servidor

| Componente | Versión | Propósito |
|-----------|---------|-----------|
| Python | 3.11+ | Runtime de la API |
| FastAPI | latest | Framework web |
| uvicorn | latest | ASGI server |
| keepalived | 2.2.7+ | Failover HA |
| curl | latest | Health checks |

### 5.3 Keepalived Configuration

**Servidor A (MASTER) - `/etc/keepalived/keepalived.conf`:**
```conf
vrrp_script chk_kms {
    script "/opt/kms/health-check.sh"
    interval 2
    weight -20
    fall 3
    rise 2
}

vrrp_instance VI_1 {
    state MASTER
    interface eth0
    virtual_router_id 51
    priority 101
    advert_int 1
    authentication {
        auth_type PASS
        auth_pass kmssecret
    }
    virtual_ipaddress {
        172.16.222.250
    }
    track_script {
        chk_kms
    }
}
```

**Servidor B (BACKUP) - `/etc/keepalived/keepalived.conf`:**
```conf
vrrp_script chk_kms {
    script "/opt/kms/health-check.sh"
    interval 2
    weight -20
    fall 3
    rise 2
}

vrrp_instance VI_1 {
    state BACKUP
    interface eth0
    virtual_router_id 51
    priority 100
    advert_int 1
    authentication {
        auth_type PASS
        auth_pass kmssecret
    }
    virtual_ipaddress {
        172.16.222.250
    }
    track_script {
        chk_kms
    }
}
```

### 5.4 Health Check Script

**`/opt/kms/health-check.sh`:**
```bash
#!/bin/bash
# Health check para KMS API
# Retorna 0 si OK, 1 si FAIL

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health --max-time 3)

if [ "$HTTP_CODE" == "200" ]; then
    exit 0
else
    logger -t kms-health "Health check failed: HTTP $HTTP_CODE"
    exit 1
fi
```

### 5.5 Systemd Service

**`/etc/systemd/system/kms-api.service`:**
```ini
[Unit]
Description=KMS API Service
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=kms
Group=kms
WorkingDirectory=/opt/kms
ExecStart=/opt/kms/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60

EnvironmentFile=/opt/kms/.env

# Security
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/opt/kms/logs

[Install]
WantedBy=multi-user.target
```

### 5.6 Variables de Entorno

**`/opt/kms/.env`:**
```env
# Redis (externo)
REDIS_HOST=172.16.222.100
REDIS_PORT=6379
REDIS_DB=0

# MySQL (externo)
MYSQL_HOST=172.16.222.101
MYSQL_USER=drm_user
MYSQL_PASSWORD=<secure_password>
MYSQL_DATABASE=drm_system

# DRM Provider
DRM_PROVIDER_URL=https://35.234.128.244:8080/ConcurrentPlayback

# CMS Webhook
CMS_API_KEY=<cms_key>

# Logging
LOG_DIR=/opt/kms/logs
LOG_LEVEL=INFO
```

## 6. Flujo de Failover

```
1. Servidor A falla (proceso cae, red, etc.)
2. Health check en A falla 3 veces consecutivas (6 segundos)
3. Keepalived en B detecta timeout del MASTER
4. B envía paquete VRRP con prioridad más alta
5. B toma control de la VIP (172.16.222.250)
6. Tráfico ahora llega a B (~3-5 segundos total)
7. B sirve requests normalmente
8. Cuando A se recupera:
   a. Health check de A pasa
   b. Keepalived en A detecta que B tiene la VIP
   c. A toma control de la VIP (preempt)
   d. Tráfico vuelve a A
```

## 7. Scripts de Deploy

### 7.1 deploy-kms-ha.sh

```bash
#!/bin/bash
set -e

SERVERS=("172.16.222.241" "172.16.222.242")
SSH_USER="oymservice"
REMOTE_DIR="/opt/kms"

for SERVER in "${SERVERS[@]}"; do
    echo "═══════════════════════════════════════"
    echo "Deploying to $SERVER"
    echo "═══════════════════════════════════════"
    
    # Crear directorio
    ssh "$SSH_USER@$SERVER" "sudo mkdir -p $REMOTE_DIR/logs"
    
    # Subir archivos
    scp main.py "$SSH_USER@$SERVER:/tmp/main.py"
    scp .env "$SSH_USER@$SERVER:/tmp/.env"
    scp health-check.sh "$SSH_USER@$SERVER:/tmp/health-check.sh"
    scp keepalived.conf."$(echo $SERVER | awk -F. '{print $4}')" \
        "$SSH_USER@$SERVER:/tmp/keepalived.conf"
    
    # Instalar
    ssh "$SSH_USER@$SERVER" "
        sudo mv /tmp/main.py $REMOTE_DIR/
        sudo mv /tmp/.env $REMOTE_DIR/
        sudo mv /tmp/health-check.sh $REMOTE_DIR/
        sudo chmod +x $REMOTE_DIR/health-check.sh
        sudo mv /tmp/keepalived.conf /etc/keepalived/keepalived.conf
        sudo systemctl restart keepalived
        sudo systemctl restart kms-api
    "
    
    echo "✅ $SERVER deployed"
done

echo ""
echo "🎉 HA Deployment complete"
echo "VIP: 172.16.222.250"
```

## 8. Verificación Post-Deploy

### 8.1 Checklist

- [ ] Ambos servidores corriendo KMS API
- [ ] Health check retorna 200 en ambos
- [ ] Keepalived corriendo en ambos
- [ ] VIP (172.16.222.250) respondiendo
- [ ] Failover manual funciona (apagar A, verificar B toma VIP)
- [ ] Failback funciona (encender A, verificar A toma VIP de vuelta)

### 8.2 Comandos de Verificación

```bash
# Verificar VIP
ip addr show | grep 172.16.222.250

# Verificar keepalived
sudo systemctl status keepalived

# Verificar health check
curl http://172.16.222.250/health

# Simular failover (en Server A)
sudo systemctl stop kms-api
# Verificar en B que VIP se movió
ip addr show | grep 172.16.222.250
```

## 9. Monitoreo

### 9.1 Métricas Clave

| Métrica | Alerta si |
|---------|-----------|
| Health check failures | > 3 consecutivos |
| Failover events | Cualquier cambio |
| Request latency | > 500ms |
| Error rate | > 1% |

### 9.2 Logs

- **KMS API:** `/opt/kms/logs/activity.log`
- **Keepalived:** `/var/log/syslog` (filtro: `keepalived`)
- **Health Check:** syslog (tag: `kms-health`)

## 10. Riesgos y Mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Split-brain (ambos creen ser MASTER) | `virtual_router_id` único, authentication PASS |
| Health check false positive | `fall 3` (3 fallos antes de failover) |
| Red cae entre servidores | Keepalived solo funciona en misma VLAN |
| VIP no se mueve | Verificar `net.ipv4.ip_forward=1` |

## 11. Próximos Pasos

1. **Provisionar servidores** (241, 242) con Ubuntu 22.04
2. **Configurar red** (misma VLAN, IPs estáticas)
3. **Instalar dependencias** en ambos servidores
4. **Deploy keepalived** en ambos
5. **Deploy KMS API** en ambos
6. **Probar failover** manual
7. **Documentar IP final** del VIP para clientes
