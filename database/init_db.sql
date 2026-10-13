-- ====================================================================
-- QuantumGeoRescue AI - Script de Inicialización de Base de Datos
-- Motor: PostgreSQL 14+ con Extensión Espacial PostGIS
-- ====================================================================

-- 1. Habilitar extensión espacial PostGIS
CREATE EXTENSION IF NOT EXISTS postgis;

-- 2. Tabla de Usuarios (Soporte B2C Ciudadano y B2G Centro de Mando)
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    usuario VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    rol VARCHAR(50) NOT NULL DEFAULT 'ciudadano',
    institucion VARCHAR(120) NOT NULL DEFAULT 'individual',
    permisos VARCHAR(500) NOT NULL DEFAULT '[]',
    is_active INTEGER NOT NULL DEFAULT 1,
    codigo_enlace VARCHAR(50) UNIQUE NOT NULL,    -- Código para vinculación familiar
    correo_seguridad VARCHAR(255),                -- Correo para alertas antirrobo (opcional)
    correo_seguridad_bloqueado_hasta TIMESTAMP,   -- No se puede cambiar el correo antes de esta hora (UTC)
    creado_en TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_usuarios_nombre ON usuarios(usuario);

-- 3. Tabla de Red de Protección Familiar
CREATE TABLE IF NOT EXISTS red_familiar (
    id SERIAL PRIMARY KEY,
    usuario_responsable VARCHAR(100) NOT NULL,
    nombre VARCHAR(150) NOT NULL,
    parentesco VARCHAR(80) NOT NULL,
    dispositivo_id VARCHAR(100),
    familiar_usuario VARCHAR(100),
    consentimiento_en TIMESTAMP,
    revocado_en TIMESTAMP,
    revocado_por VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_red_familiar_responsable ON red_familiar(usuario_responsable);
CREATE INDEX IF NOT EXISTS idx_red_familiar_familiar_usuario ON red_familiar(familiar_usuario);

CREATE TABLE IF NOT EXISTS family_invitations (
    id SERIAL PRIMARY KEY,
    invitante_usuario VARCHAR(100) NOT NULL,
    invitado_usuario VARCHAR(100) NOT NULL,
    parentesco VARCHAR(80) NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE',
    creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    respondido_en TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_family_invitations_invitado
    ON family_invitations(invitado_usuario, estado);

CREATE TABLE IF NOT EXISTS institution_invites (
    id SERIAL PRIMARY KEY,
    institution_name VARCHAR(120) NOT NULL,
    member_name VARCHAR(120) NOT NULL,
    email VARCHAR(120) NOT NULL,
    role VARCHAR(60) NOT NULL,
    token_hash VARCHAR(64) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    accepted_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_institution_invites_institution ON institution_invites (institution_name);

CREATE TABLE IF NOT EXISTS institution_applications (
    id SERIAL PRIMARY KEY,
    institution_name VARCHAR(120) NOT NULL,
    ruc VARCHAR(11) UNIQUE NOT NULL,
    institution_type VARCHAR(60) NOT NULL,
    region VARCHAR(100) NOT NULL,
    official_email VARCHAR(200) NOT NULL,
    contact_name VARCHAR(120) NOT NULL,
    contact_phone VARCHAR(40) NOT NULL,
    evidence_url VARCHAR(500) NOT NULL,
    applicant_username VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    verification_source VARCHAR(500),
    review_notes TEXT,
    reviewed_by VARCHAR(120),
    submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP NULL
);
CREATE INDEX IF NOT EXISTS idx_institution_applications_status ON institution_applications (status);

CREATE TABLE IF NOT EXISTS platform_admin_accounts (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    password_hash VARCHAR(255) NOT NULL,
    must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
    password_updated_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 4. Tabla de Alertas de Emergencia con Geometría PostGIS (SRID 4326 - WGS84)
CREATE TABLE IF NOT EXISTS alertas_emergencia (
    id SERIAL PRIMARY KEY,
    client_alert_id VARCHAR(36) UNIQUE,
    dispositivo_id VARCHAR(100) NOT NULL,
    usuario VARCHAR(100),
    tipo_emergencia VARCHAR(150) NOT NULL,
    nivel_gravedad INTEGER NOT NULL,
    origen_alerta VARCHAR(50) DEFAULT 'MANUAL' NOT NULL,        -- 'MANUAL' o 'AUTOMATICO_INERCIA'
    estado_confirmacion VARCHAR(50) DEFAULT 'CONFIRMADO' NOT NULL, -- 'CONFIRMADO', 'EXPIRADO_INCONSCIENTE'
    estado VARCHAR(40) DEFAULT 'REGISTRADA' NOT NULL,
    latitud DOUBLE PRECISION,
    longitud DOUBLE PRECISION,
    canal_entrada VARCHAR(20) NOT NULL DEFAULT 'API',
    precision_m INTEGER,
    edad_lectura_s INTEGER,
    es_simulacro BOOLEAN NOT NULL DEFAULT FALSE,
    ubicacion GEOMETRY(Point, 4326),
    timestamp_dispositivo TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    sincronizado BOOLEAN DEFAULT TRUE NOT NULL,
    creado_en TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Índice espacial GiST para consultas geoespaciales de alta velocidad
CREATE INDEX IF NOT EXISTS idx_alertas_ubicacion ON alertas_emergencia USING GIST (ubicacion);
CREATE INDEX IF NOT EXISTS idx_alertas_dispositivo ON alertas_emergencia (dispositivo_id);
CREATE INDEX IF NOT EXISTS idx_alertas_creado_en ON alertas_emergencia (creado_en DESC);

CREATE TABLE IF NOT EXISTS alert_recipients (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER NOT NULL REFERENCES alertas_emergencia(id) ON DELETE RESTRICT,
    recipient_type VARCHAR(20) NOT NULL,
    recipient_username VARCHAR(100) NOT NULL,
    available_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP,
    CONSTRAINT uq_alert_recipient UNIQUE(alert_id, recipient_type, recipient_username)
);
CREATE INDEX IF NOT EXISTS idx_alert_recipients_user
    ON alert_recipients(recipient_type, recipient_username);

CREATE TABLE IF NOT EXISTS alert_state_history (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER NOT NULL REFERENCES alertas_emergencia(id) ON DELETE RESTRICT,
    actor VARCHAR(100) NOT NULL,
    from_state VARCHAR(40),
    to_state VARCHAR(40) NOT NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_alert_state_history_alert_id ON alert_state_history(alert_id);

CREATE OR REPLACE FUNCTION reject_alert_state_history_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'alert_state_history is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_alert_state_history_immutable ON alert_state_history;
CREATE TRIGGER trg_alert_state_history_immutable
BEFORE UPDATE OR DELETE ON alert_state_history
FOR EACH ROW EXECUTE FUNCTION reject_alert_state_history_mutation();

CREATE TABLE IF NOT EXISTS alert_outbox (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER NOT NULL REFERENCES alertas_emergencia(id) ON DELETE RESTRICT,
    event_type VARCHAR(80) NOT NULL,
    payload TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_alert_outbox_due ON alert_outbox(status, available_at);

CREATE TABLE IF NOT EXISTS telefonos_verificados (
    id SERIAL PRIMARY KEY,
    usuario VARCHAR(100) NOT NULL,
    telefono VARCHAR(20) UNIQUE NOT NULL,
    verificado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    intentos_fallidos INTEGER NOT NULL DEFAULT 0,
    ultimo_intento_fallido_en TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_telefonos_verificados_usuario
    ON telefonos_verificados(usuario);

CREATE TABLE IF NOT EXISTS phone_otp_challenges (
    id SERIAL PRIMARY KEY,
    usuario VARCHAR(100) NOT NULL,
    telefono VARCHAR(20) NOT NULL,
    code_hash VARCHAR(64) NOT NULL,
    salt VARCHAR(32) NOT NULL,
    creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expira_en TIMESTAMP NOT NULL,
    intentos INTEGER NOT NULL DEFAULT 0,
    consumido_en TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_phone_otp_challenges_lookup
    ON phone_otp_challenges(usuario, telefono, expira_en);

CREATE TABLE IF NOT EXISTS dispositivos_firmantes (
    id SERIAL PRIMARY KEY,
    usuario VARCHAR(100) NOT NULL,
    dispositivo_id VARCHAR(100) NOT NULL,
    secreto_cifrado TEXT NOT NULL,
    creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revocado_en TIMESTAMP,
    CONSTRAINT uq_dispositivo_firmante UNIQUE(usuario, dispositivo_id)
);
CREATE INDEX IF NOT EXISTS idx_dispositivos_firmantes_usuario
    ON dispositivos_firmantes(usuario);

CREATE TABLE IF NOT EXISTS sms_descartados (
    id SERIAL PRIMARY KEY,
    remitente VARCHAR(40) NOT NULL,
    texto TEXT NOT NULL,
    motivo VARCHAR(40) NOT NULL,
    recibido_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sms_descartados_revision
    ON sms_descartados(motivo, recibido_en DESC);

CREATE TABLE IF NOT EXISTS sms_phone_abuse_counters (
    telefono VARCHAR(40) PRIMARY KEY,
    contador INTEGER NOT NULL DEFAULT 0,
    ultimo_motivo VARCHAR(40) NOT NULL,
    actualizado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sms_outbound_rate_limits (
    telefono VARCHAR(20) PRIMARY KEY,
    ventana_iniciada_en TIMESTAMP NOT NULL,
    cantidad INTEGER NOT NULL DEFAULT 0
);
