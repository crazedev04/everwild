# Recetas y materiales (datos, no código)

Todo está en JSON y se puede ampliar sin tocar el código (también en `datos/extra/`). **Nadie sabe ninguna receta al empezar**: las descubren probando materiales (acción `inventar`) y el mundo comprueba que la idea funcione con las propiedades reales del material.

- `datos_base/reglas/materiales.json` — 39 materiales con propiedades (`inflamable`, `flexible`, `chispa`, `friccion`, `aislante`, `impermeable`, `estructural`, `comestible`, `medicinal`, `conservante`…).
- `datos_base/etiquetas/etiquetas.json` — etiquetas como los *tags* de Minecraft: `#lena`, `#yesca`, `#punta`, `#ligadura`… Una receta con `"#lena"` acepta cualquier material de la lista (la coincidencia exacta tiene prioridad).
- `datos_base/recetas/recetas.json` — 123 recetas. Campos: `id`, `nombre`, `ingredientes`, `propiedad`, `categoria`, `descripcion` y, opcionales, `tiempo_min`, `resultado` {item, cantidad}, `herramienta` [], `requiere_fuego`.
- Propiedades comprobables: flota, corta, perfora, arde, ilumina, enciende, conduce, abriga, ata, teje, contiene, construye, impermeabiliza, protege, dispara, pega, cura, conserva, alimenta.

Familias cargadas: fuego (frotar palos, pedernal, eslabón, yesquero, arco de fuego, antorchas, velas, lámparas), corte y puntas, armas a distancia y trampas, hilos/cuerdas/telas, ropa, protección, recipientes, refugios (choza de ramas, paja, barro, tienda, cabaña, muro, horno), impermeables y pegamentos, comida y conservas, curación.

**Todavía es solo conocimiento**: saber «fogata» o «yesquero» no enciende nada y las recetas no entregan el objeto todavía (los campos `resultado`/`tiempo_min` ya están en los datos para cuando sí). Pendiente: fogata real, antorcha tomada de un incendio, juntar materiales del mundo (palos, pedernal, arcilla, hierbas), elaborar el objeto y usarlo (ropa que abriga de verdad, armas que mejoran la caza).

## Pasajes a otras dimensiones (fase G2)

Una estructura puede **llevar a otro mapa**, igual que puede dar calor:

```json
{"type": "estructura", "id": "pozo_a_las_cavernas", "provee": {"lleva_a": "cavernas"}, "radio_m": 10.0}
```

La receta que la construye lleva `"estructura": {"abrigo": 0.0}` y el **mismo id** que la estructura.
Detalle completo en `docs/DIMENSIONES.md`.
