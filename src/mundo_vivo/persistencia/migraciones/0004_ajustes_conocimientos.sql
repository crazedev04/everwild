-- Migración 0004: interruptores del mundo y conocimientos descubiertos.

-- Ajustes por mundo (qué módulos están prendidos, modelo de lenguaje, etc.). Valor en JSON.
CREATE TABLE ajustes (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

-- Conocimientos descubiertos por los habitantes (recetas validadas contra las reglas de materiales).
CREATE TABLE conocimientos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre      TEXT    NOT NULL UNIQUE,
    descripcion TEXT,
    materiales  TEXT    NOT NULL DEFAULT '[]',   -- lista JSON de ids de material
    propiedad   TEXT,                            -- qué se comprobó (flota, corta, arde, conduce...)
    creador_id  INTEGER REFERENCES habitantes(id),
    t_min       INTEGER NOT NULL
);

-- Quién sabe qué, y de quién lo aprendió (NULL = lo descubrió él).
CREATE TABLE conoce (
    habitante_id   INTEGER NOT NULL REFERENCES habitantes(id),
    conocimiento_id INTEGER NOT NULL REFERENCES conocimientos(id),
    aprendido_de   INTEGER REFERENCES habitantes(id),
    t_min          INTEGER NOT NULL,
    PRIMARY KEY (habitante_id, conocimiento_id)
) WITHOUT ROWID;
