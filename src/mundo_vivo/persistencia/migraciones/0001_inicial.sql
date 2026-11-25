-- Migración 0001: esquema inicial.
-- REGLA: una migración ya publicada NUNCA se edita. Los cambios van en una migración nueva (0002, 0003...).

-- Datos del mundo (semilla, versión del generador, tamaño, etc.)
CREATE TABLE meta (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

-- Mapa guardado por bloques (chunks) comprimidos. Una fila por capa y bloque.
CREATE TABLE capas (
    capa  TEXT    NOT NULL,
    cx    INTEGER NOT NULL,
    cy    INTEGER NOT NULL,
    datos BLOB    NOT NULL,
    PRIMARY KEY (capa, cx, cy)
) WITHOUT ROWID;

-- Reloj del mundo (una sola fila). t_min = minutos desde el inicio del mundo.
CREATE TABLE estado_mundo (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    t_min         INTEGER NOT NULL,
    velocidad     REAL    NOT NULL DEFAULT 1.0,
    actualizado_en TEXT
);
INSERT INTO estado_mundo (id, t_min, velocidad) VALUES (1, 480, 1.0);

-- Habitantes: identidad permanente. Nunca se borran (al morir se registra la muerte).
CREATE TABLE habitantes (
    id             INTEGER PRIMARY KEY,
    uuid           TEXT    NOT NULL UNIQUE,
    nombre         TEXT    NOT NULL,
    nacimiento_min INTEGER NOT NULL DEFAULT 0,
    muerte_min     INTEGER,
    causa_muerte   TEXT,
    x REAL, y REAL, z REAL,                 -- posición continua en metros (x,y) y altura (z)
    estado         TEXT    NOT NULL DEFAULT '{}',   -- necesidades, salud, inventario (JSON)
    identidad      TEXT    NOT NULL DEFAULT '{}',   -- personalidad, preferencias con historia (JSON)
    creado_en      TEXT
);

-- Historia del mundo. Una fila por cosa que ocurre.
CREATE TABLE eventos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    t_min       INTEGER NOT NULL,
    tipo        TEXT    NOT NULL,           -- p.ej. herida, muerte, descubrimiento, comercio
    actor_id    INTEGER REFERENCES habitantes(id),
    objetivo_id INTEGER,                    -- otro habitante o entidad involucrada
    x REAL, y REAL, z REAL,
    causa       TEXT,
    resultado   TEXT,
    importancia INTEGER NOT NULL DEFAULT 1, -- 1 menor ... 5 muy importante
    origen      TEXT    NOT NULL DEFAULT 'autonomo' CHECK (origen IN ('autonomo', 'usuario', 'sistema')),
    datos       TEXT    NOT NULL DEFAULT '{}',   -- detalles estructurados (JSON)
    texto       TEXT                              -- frase legible para el panel
);
CREATE INDEX idx_eventos_t     ON eventos (t_min);
CREATE INDEX idx_eventos_tipo  ON eventos (tipo);
CREATE INDEX idx_eventos_actor ON eventos (actor_id, t_min);

-- Memoria PRIVADA de cada habitante. Se accede siempre filtrando por habitante_id
-- (ver persistencia/memoria.py); nunca se mezcla la memoria de varios habitantes.
CREATE TABLE memorias (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    habitante_id    INTEGER NOT NULL REFERENCES habitantes(id),
    t_min           INTEGER NOT NULL,
    tipo            TEXT    NOT NULL CHECK (tipo IN ('episodica', 'semantica', 'resumen', 'creencia')),
    contenido       TEXT    NOT NULL,
    importancia     REAL    NOT NULL DEFAULT 0.5,
    evento_id       INTEGER REFERENCES eventos(id),
    embedding       BLOB,
    version_resumen INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX idx_memorias_hab ON memorias (habitante_id, t_min);

-- Registro explicable de decisiones: qué percibió, qué recordó, qué respondió el modelo y qué pasó.
CREATE TABLE decisiones (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    habitante_id   INTEGER NOT NULL REFERENCES habitantes(id),
    t_min          INTEGER NOT NULL,
    percepcion     TEXT,
    recuerdos      TEXT,
    respuesta_modelo TEXT,
    accion         TEXT,
    resultado      TEXT,
    ok             INTEGER,
    modelo         TEXT,
    latencia_ms    INTEGER
);
CREATE INDEX idx_decisiones_hab ON decisiones (habitante_id, t_min);
