-- Estado dinámico del mundo vivo (fuego, ceniza, combustible, tormentas): se guarda como bloques binarios/JSON por clave.
CREATE TABLE IF NOT EXISTS estado_dinamico (
    clave TEXT PRIMARY KEY,
    valor BLOB NOT NULL,
    actualizado_min REAL NOT NULL DEFAULT 0
);
