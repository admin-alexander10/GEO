-- Alinea red_familiar con el modelo ORM (RedFamiliar.created_at).
-- Solo hace falta si la tabla se creó con una versión anterior de init_db.sql,
-- donde la columna se llamaba creado_en. Es seguro ejecutarlo más de una vez.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'red_familiar' AND column_name = 'creado_en'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'red_familiar' AND column_name = 'created_at'
    ) THEN
        ALTER TABLE red_familiar RENAME COLUMN creado_en TO created_at;
    END IF;
END $$;
