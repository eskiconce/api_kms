# Changelog

Todo notable del proyecto KMS API será documentado en este archivo.

El formato se basa en [Keep a Changelog](https://keepachangelog.com/es-1.0.0/),
y el proyecto adherido a [Semantic Versioning](https://semver.org/lang/es/).

---

## [Unreleased]

### Added
- Documentación completa del proyecto
- README.md principal
- docs/architecture.md — Arquitectura del sistema
- docs/api-reference.md — Referencia completa de API
- docs/database.md — Esquema de base de datos
- docs/configuration.md — Variables de entorno
- docs/deployment.md — Proceso de despliegue
- docs/monitoring.md — Monitoreo y health checks
- docs/ha-design.md — Diseño de alta disponibilidad
- Diagrama de arquitectura HTML
- CHANGELOG.md

### Changed
- Sincronizado main.py con servidor (autocommit=True)

---

## [1.0.0] - 2026-07-16

### Added
- API KMS inicial con FastAPI
- Content Key Management (generate, rotate, list)
- License endpoints Widevine (v1, v2, proxy)
- VIP Users CRUD
- CMS Webhook con autenticación
- Health checks (Redis, MySQL)
- Redis cache con fallback a MySQL
- Logging a archivo
- Scripts de deploy (deploy-kms.sh, deploy-kms.exp)
- Sistema de respaldos automáticos

---

## [0.1.0] - 2026-07-11

### Added
- PoC inicial de KMS Widevine DRM
- Prototipo de generación de content keys
- Prueba de concepto de license proxy
