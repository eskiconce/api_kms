#!/bin/bash
# ==========================================
# Deploy automático del KMS API
# Uso:
#   bash deploy-kms.sh                 # Deploy de main.py
#   bash deploy-kms.sh archivo.py      # Deploy de un archivo específico
#   bash deploy-kms.sh --test          # Solo prueba conexión
# ==========================================
set -e

SSH_USER="oymservice"
SSH_HOST="172.16.222.240"
SSH_OPTS="-o PreferredAuthentications=password -o StrictHostKeyChecking=no"
REMOTE_DIR="/opt/kms"
BACKUP_DIR="${REMOTE_DIR}/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
SERVICE="kms-api.service"

GIT_ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ "$1" == "--test" ] || [ "$1" == "--dry-run" ]; then
    echo "🧪 MODO PRUEBA — Solo verificando conexión..."
    if [ -z "${SUDO_PASS+x}" ]; then
        read -s -p "🔑 Contraseña sudo de ${SSH_USER}: " SUDO_PASS
        echo ""
    fi

    ssh ${SSH_OPTS} -t "${SSH_USER}@${SSH_HOST}" "
        echo '✅ Conexión SSH exitosa'
        echo ''
        echo '📋 Versión actual:'
        echo ${SUDO_PASS} | sudo -S head -5 ${REMOTE_DIR}/main.py
        echo ''
        echo '📂 Respaldos existentes:'
        echo ${SUDO_PASS} | sudo -S find ${BACKUP_DIR}/ -type f 2>/dev/null | sort || echo '   (sin respaldos aún)'
        echo ''
        echo '📊 Estado del servicio:'
        echo ${SUDO_PASS} | sudo -S systemctl status ${SERVICE} --no-pager 2>&1 | head -5
        echo ''
        echo '🎯 Modo prueba — No se realizaron cambios'
    "
    echo ""
    echo "🧪 Prueba completada."
    exit 0
fi

# Archivos a desplegar
if [ -n "$1" ]; then
    FILES=("$1")
else
    FILES=("main.py")
fi

echo "🚀 Deploy de ${#FILES[@]} archivo(s) a ${SSH_USER}@${SSH_HOST}:${REMOTE_DIR}"
for f in "${FILES[@]}"; do echo "   - $f"; done

# Pedir contraseña
if [ -z "${SUDO_PASS+x}" ]; then
    read -s -p "🔑 Contraseña sudo de ${SSH_USER}: " SUDO_PASS
    echo ""
fi

# Subir archivos
echo "📤 Subiendo archivos..."
for FILE in "${FILES[@]}"; do
    SRC="${GIT_ROOT}/${FILE}"
    if [ ! -f "$SRC" ]; then
        echo "⚠️  No se encuentra $SRC, omitiendo..."
        continue
    fi
    REMOTE_TMP="/tmp/${FILE}"
    echo "   → ${FILE}"
    ssh ${SSH_OPTS} "${SSH_USER}@${SSH_HOST}" "mkdir -p $(dirname ${REMOTE_TMP})"
    scp ${SSH_OPTS} "${SRC}" "${SSH_USER}@${SSH_HOST}:${REMOTE_TMP}"
done

# Instalar en servidor
echo "📦 Instalando en servidor..."
INSTALL_CMDS=""
for FILE in "${FILES[@]}"; do
    REMOTE_TMP="/tmp/${FILE}"
    REMOTE_DST="${REMOTE_DIR}/${FILE}"
    INSTALL_CMDS+="
  echo '   → ${FILE}'
  echo ${SUDO_PASS} | sudo -S mkdir -p $(dirname ${BACKUP_DIR}/${FILE}.${TIMESTAMP}.bak)
  echo ${SUDO_PASS} | sudo -S cp ${REMOTE_DST} ${BACKUP_DIR}/${FILE}.${TIMESTAMP}.bak 2>/dev/null && echo '   ✅ Respaldo: ${FILE}.${TIMESTAMP}.bak' || echo '   ℹ️  Sin respaldo previo'
  echo ${SUDO_PASS} | sudo -S mv ${REMOTE_TMP} ${REMOTE_DST}"
done

ssh ${SSH_OPTS} -t "${SSH_USER}@${SSH_HOST}" "
  echo ${SUDO_PASS} | sudo -S mkdir -p ${BACKUP_DIR}${INSTALL_CMDS}
  
  # Verificar sintaxis
  for f in ${FILES[@]}; do
    case \$f in
      *.py)
        echo ${SUDO_PASS} | sudo -S python3 -m py_compile ${REMOTE_DIR}/\$f && echo \"   ✅ Python OK: \$f\" || echo \"   ❌ Error en \$f\"
        ;;
      *)
        echo \"   📄 Copiado: \$f\"
        ;;
    esac
  done
  
  # Reiniciar servicio
  echo ${SUDO_PASS} | sudo -S systemctl restart ${SERVICE}
  echo '✅ Servicio reiniciado'
"

# Verificar estado
sleep 2
echo "📋 Estado del servicio:"
ssh ${SSH_OPTS} -t "${SSH_USER}@${SSH_HOST}" "echo ${SUDO_PASS} | sudo -S systemctl status ${SERVICE} --no-pager | head -8"

echo ""
echo "🎉 Deploy completado!"
echo "   Archivos: ${FILES[*]}"
echo "   Respaldo: ${BACKUP_DIR}/"
