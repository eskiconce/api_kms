# Monitoreo

## Health Check

### GET /health

Endpoint principal de salud. Retorna `200` si todo está OK, `503` si hay problemas.

```bash
curl http://localhost:8000/health
```

**Response OK:**
```json
{
  "status": "UP",
  "api": "UP",
  "redis": "UP",
  "database": "UP",
  "healthy": true
}
```

**Response Degraded:**
```json
{
  "status": "UP",
  "api": "UP",
  "redis": "DOWN",
  "database": "UP",
  "healthy": false
}
```

**Códigos de respuesta:**
- `200` — Todos los componentes UP
- `503` — Al menos un componente DOWN

---

## Estadísticas

### GET /api/stats

```bash
curl http://localhost:8000/api/stats
```

```json
{
  "total_keys": 150,
  "active_vip_users": 45,
  "total_vip_users": 52,
  "license_requests_24h": 1234
}
```

---

## Logs

### Ubicación

- **Archivo:** `/opt/kms/logs/activity.log`
- **Formato:** `YYYY-MM-DD HH:MM:SS - LEVEL - message`
- **Nivel configurable:** `LOG_LEVEL=INFO`

### Tipos de Eventos

| Evento | Nivel | Ejemplo |
|--------|-------|---------|
| Key generada | INFO | `NUEVA: Canal hd-1 -> KID abc123` |
| Key cacheada | INFO | `CACHE: Canal hd-1 -> KID abc123` |
| Key rotada | INFO | `ROTADA: Canal hd-1 -> Nuevo KID xyz` |
| Licencia servida | INFO | `V1: KID abc123 servido desde cache` |
| Redis caído | WARNING | `Redis no disponible, fallback a MySQL` |
| Token inválido | WARNING | `Token invalido KID=abc123` |
| Error KMS | ERROR | `KMS canal-hd-1: connection refused` |

### Ver Logs en Tiempo Real

```bash
# En servidor
tail -f /opt/kms/logs/activity.log

# Via API
curl "http://localhost:8000/api/logs?lines=100"
```

### Filtrar por Nivel

```bash
grep "ERROR" /opt/kms/logs/activity.log
grep "WARNING" /opt/kms/logs/activity.log
```

---

## Systemd Monitoring

```bash
# Estado del servicio
sudo systemctl status kms-api.service

# Logs del sistema
sudo journalctl -u kms-api.service -f

# Últimos 100 eventos
sudo journalctl -u kms-api.service -n 100
```

---

## Métricas Externas (Opcional)

### Script de Monitoreo

```bash
#!/bin/bash
# /opt/kms/monitor.sh

HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)

if [ "$HEALTH" != "200" ]; then
    echo "ALERT: KMS API health check failed (HTTP $HEALTH)"
    # Enviar notificación (email, Slack, etc.)
fi
```

### Cron para Monitoreo

```bash
# Cada 5 minutos
*/5 * * * * /opt/kms/monitor.sh
```

---

## Alertas Sugeridas

| Condición | Acción |
|-----------|--------|
| Health check falla 3 veces | Notificación urgente |
| Redis DOWN > 5 min | Verificar Redis |
| MySQL DOWN | Verificar MySQL |
| Error rate > 10% | Revisar logs |
| CPU > 80% por 10 min | Escalar capacidad |
| Disk > 85% | Limpiar logs |

---

## Dashboard (Opcional)

Para visualización en tiempo real, integrar con:

- **Grafana** — Conectar a MySQL/Redis como data sources
- **Prometheus** — Exportar métricas custom
- **Zabbix** — Agent monitoring

### Endpoint para Dashboard

```bash
# Estadísticas agregadas
curl http://localhost:8000/api/stats

# Actividad reciente
curl "http://localhost:8000/api/activity?limit=50"

# Logs
curl "http://localhost:8000/api/logs?lines=200"
```
