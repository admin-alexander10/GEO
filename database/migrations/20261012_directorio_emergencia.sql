-- Directorio de puntos de atención locales (comisarías, bomberos, salud).
-- Migración aditiva; es seguro ejecutarla más de una vez.
CREATE TABLE IF NOT EXISTS directorio_emergencia (
    id SERIAL PRIMARY KEY,
    tipo VARCHAR(20) NOT NULL,
    nombre VARCHAR(200) NOT NULL,
    nombre_clave VARCHAR(200) NOT NULL,
    distrito_clave VARCHAR(120) NOT NULL DEFAULT '',
    telefono VARCHAR(40),
    direccion VARCHAR(300),
    distrito VARCHAR(120),
    latitud DOUBLE PRECISION NOT NULL,
    longitud DOUBLE PRECISION NOT NULL,
    fuente TEXT NOT NULL,
    verificado_en DATE NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_directorio_emergencia_tipo ON directorio_emergencia (tipo);
CREATE INDEX IF NOT EXISTS idx_directorio_emergencia_activo ON directorio_emergencia (activo);
CREATE INDEX IF NOT EXISTS idx_directorio_emergencia_nombre_clave ON directorio_emergencia (nombre_clave);
