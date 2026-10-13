-- Pago reportado por el usuario (Yape / Plin / transferencia) para validación manual.
-- El backend aplica estas columnas automáticamente al arrancar; este archivo queda como
-- registro y para ejecutarlo a mano si hiciera falta. Es seguro ejecutarlo más de una vez.
ALTER TABLE user_subscriptions ADD COLUMN IF NOT EXISTS payment_method VARCHAR(40);
ALTER TABLE user_subscriptions ADD COLUMN IF NOT EXISTS payment_reference VARCHAR(120);
