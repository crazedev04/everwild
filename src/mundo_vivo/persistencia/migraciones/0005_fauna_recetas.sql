-- Migración 0005: origen de los conocimientos (receta del catálogo o invento propio).
ALTER TABLE conocimientos ADD COLUMN origen TEXT NOT NULL DEFAULT 'inventada';   -- 'catalogo' | 'inventada'
ALTER TABLE conocimientos ADD COLUMN receta_id TEXT;                              -- id en recetas.json si coincide
