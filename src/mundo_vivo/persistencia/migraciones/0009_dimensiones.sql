-- Migración 0009 (fase G2): dimensiones.
-- Un mundo pasa a poder tener más de un mapa (el de siempre y, por ejemplo, cavernas).
-- Todo lo viejo queda en la dimensión 0, que es el mundo de siempre: un mundo existente no cambia en nada.

-- Qué dimensiones tiene este mundo. La 0 siempre existe.
CREATE TABLE dimensiones (
    id          INTEGER PRIMARY KEY,          -- 0 = el mundo de siempre
    ident       TEXT    NOT NULL UNIQUE,      -- id de contenido (datos_base/dimensiones/): 'mundo', 'cavernas'...
    nombre      TEXT    NOT NULL,
    semilla     INTEGER NOT NULL,
    ancho       INTEGER NOT NULL,
    alto        INTEGER NOT NULL,
    tam_celda_m REAL    NOT NULL,
    hash_capas  TEXT,
    meta        TEXT    NOT NULL DEFAULT '{}',   -- lo que devuelve el generador (JSON)
    creado_en   TEXT
);

-- `capas` tenía la clave (capa, cx, cy) y es WITHOUT ROWID: para meter la dimensión en la clave
-- hay que rehacer la tabla. Se copia todo a la dimensión 0.
CREATE TABLE capas_nueva (
    dimension INTEGER NOT NULL DEFAULT 0,
    capa      TEXT    NOT NULL,
    cx        INTEGER NOT NULL,
    cy        INTEGER NOT NULL,
    datos     BLOB    NOT NULL,
    PRIMARY KEY (dimension, capa, cx, cy)
) WITHOUT ROWID;
INSERT INTO capas_nueva (dimension, capa, cx, cy, datos) SELECT 0, capa, cx, cy, datos FROM capas;
DROP TABLE capas;
ALTER TABLE capas_nueva RENAME TO capas;

-- Dónde está cada cosa. Default 0 = el mundo de siempre.
ALTER TABLE habitantes ADD COLUMN dimension INTEGER NOT NULL DEFAULT 0;
ALTER TABLE eventos    ADD COLUMN dimension INTEGER NOT NULL DEFAULT 0;

CREATE INDEX idx_eventos_dim ON eventos (dimension, t_min);

-- `estado_dinamico` (fuego, nieve, tormentas, fauna, estructuras, colonias) NO se toca: la dimensión 0 sigue
-- guardando con las claves de siempre y las otras usan el prefijo 'd<N>:'. Así un mundo viejo abre igual.

