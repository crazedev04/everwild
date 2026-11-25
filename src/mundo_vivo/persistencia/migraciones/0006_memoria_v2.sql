-- Migración 0006: memoria con lugar, etiquetas, repetición y fuerza (recuperación por recencia + importancia + relevancia, olvido).
ALTER TABLE memorias ADD COLUMN x REAL;                              -- celda donde ocurrió (NULL = sin lugar)
ALTER TABLE memorias ADD COLUMN y REAL;
ALTER TABLE memorias ADD COLUMN etiquetas TEXT NOT NULL DEFAULT '';  -- raíces de palabras clave, para la relevancia
ALTER TABLE memorias ADD COLUMN veces INTEGER NOT NULL DEFAULT 1;    -- cuántas veces se repitió lo mismo
ALTER TABLE memorias ADD COLUMN ultimo_acceso INTEGER;               -- última vez que lo recordó (repasar lo fortalece)
ALTER TABLE memorias ADD COLUMN origen TEXT NOT NULL DEFAULT 'vivido';  -- 'vivido' | 'reflexion'
CREATE INDEX idx_memorias_hab_tipo ON memorias (habitante_id, tipo);
