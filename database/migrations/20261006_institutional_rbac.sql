-- Alinear usuarios existentes con autenticación institucional y RBAC.
-- Ejecutar una sola vez antes de desplegar la versión nueva.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'usuarios' AND column_name = 'password_hash'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'usuarios' AND column_name = 'password'
    ) THEN
        ALTER TABLE usuarios RENAME COLUMN password_hash TO password;
    END IF;
END $$;

ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS institucion VARCHAR(120) NOT NULL DEFAULT 'individual';
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS permisos VARCHAR(500) NOT NULL DEFAULT '[]';
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS is_active INTEGER NOT NULL DEFAULT 1;

ALTER TABLE plan_catalog ADD COLUMN IF NOT EXISTS included_users INTEGER NOT NULL DEFAULT 1;
ALTER TABLE plan_catalog ADD COLUMN IF NOT EXISTS extra_seat_price DOUBLE PRECISION NOT NULL DEFAULT 0;

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
CREATE INDEX IF NOT EXISTS idx_institution_invites_institution
    ON institution_invites (institution_name);
CREATE INDEX IF NOT EXISTS idx_institution_invites_email ON institution_invites (email);

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
CREATE INDEX IF NOT EXISTS idx_institution_applications_ruc ON institution_applications (ruc);
CREATE INDEX IF NOT EXISTS idx_institution_applications_status ON institution_applications (status);

CREATE TABLE IF NOT EXISTS platform_admin_accounts (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    password_hash VARCHAR(255) NOT NULL,
    must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
    password_updated_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
