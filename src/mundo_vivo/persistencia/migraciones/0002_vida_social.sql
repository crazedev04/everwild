-- Migración 0002: familia/genoma, registro de diálogos y relaciones.

-- Familia y genoma de cada habitante (el genoma es JSON: rasgos + pesos de la red de reflejos).
ALTER TABLE habitantes ADD COLUMN madre_id INTEGER REFERENCES habitantes(id);
ALTER TABLE habitantes ADD COLUMN padre_id INTEGER REFERENCES habitantes(id);
ALTER TABLE habitantes ADD COLUMN genoma TEXT NOT NULL DEFAULT '{}';

-- Registro COMPLETO de todo lo que se dicen (auditoría para el observador).
-- Los habitantes NO leen esta tabla: cada uno solo recuerda lo que vivió (tabla memorias).
CREATE TABLE dialogos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    t_min        INTEGER NOT NULL,
    emisor_id    INTEGER NOT NULL REFERENCES habitantes(id),
    receptores   TEXT    NOT NULL,            -- lista JSON de ids
    mensaje      TEXT    NOT NULL,
    x REAL, y REAL, z REAL,
    sospecha     TEXT                         -- patrones detectados (JSON) o NULL
);
CREATE INDEX idx_dialogos_t ON dialogos (t_min);
CREATE INDEX idx_dialogos_emisor ON dialogos (emisor_id, t_min);

-- Cómo ve cada habitante a otro (dirigida: A->B puede diferir de B->A). Privada de cada habitante.
CREATE TABLE relaciones (
    habitante_id   INTEGER NOT NULL REFERENCES habitantes(id),
    otro_id        INTEGER NOT NULL REFERENCES habitantes(id),
    afecto         REAL    NOT NULL DEFAULT 0,   -- -1 (enemistad) .. +1 (cariño)
    confianza      REAL    NOT NULL DEFAULT 0,   -- -1 .. +1
    actualizado_min INTEGER NOT NULL DEFAULT 0,
    resumen        TEXT,                         -- último motivo del cambio
    PRIMARY KEY (habitante_id, otro_id)
) WITHOUT ROWID;
