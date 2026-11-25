-- Procedencia y certeza de cada recuerdo.
-- Hasta ahora un rumor valía lo mismo que algo visto con los propios ojos. Ahora cada recuerdo sabe de dónde
-- salió y cuánto se le cree. Los recuerdos viejos quedan como «visto» con certeza plena, que es lo que eran.
ALTER TABLE memorias ADD COLUMN de_quien INTEGER;
ALTER TABLE memorias ADD COLUMN certeza REAL NOT NULL DEFAULT 1.0;
