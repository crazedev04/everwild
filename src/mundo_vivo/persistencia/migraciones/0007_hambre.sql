-- Hambre: cuarta barra, independiente de salud, agua y energía.
-- Arranca en 0 para todo el mundo que ya existía; el módulo "hambre" viene apagado en esos mundos
-- (ver agentes/ajustes.py) para no cambiarles las reglas a mitad de partida.
ALTER TABLE habitantes ADD COLUMN hambre REAL NOT NULL DEFAULT 0;
