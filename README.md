# Mundo Vivo

Mundo 2D procedural y persistente donde habitantes controlados por IA local (Ollama) sobreviven, aprenden y evolucionan.

Plan completo: [`docs/plan-maestro-v0.1.md`](docs/plan-maestro-v0.1.md)
Cambios por versión: [`CHANGELOG.md`](CHANGELOG.md) · Decisiones y análisis: [`docs/REGISTRO_DECISIONES.md`](docs/REGISTRO_DECISIONES.md)

## Estado actual

| Fase | Estado |
|---|---|
| 0.5 Prueba del cerebro | **Hecha** con qwen3.5:4b (`pruebas_cerebro/`); falta comparar modelos en modo `--dificil` |
| 0 Cimientos (BD, migraciones, backups, exportar) | **Hecha y con pruebas** |
| 1 Continente procedural + visor 2D | **Primera versión hecha** (superficie, clima, ríos, lagos, cascadas, volcanes, biomas). Subsuelo y cuevas: pendiente |
| 2 Ecología | Pendiente |
| 3 Cuatro agentes autónomos | Pendiente |

## Usar el mundo y el visor

```bash
./iniciar.sh                 # crea el entorno la primera vez y abre el visor en http://localhost:8000
./iniciar.sh generar --semilla 42      # genera un mundo desde la terminal
./iniciar.sh listar                    # lista los mundos guardados
./iniciar.sh poblar mundo_42           # crea los 4 habitantes iniciales junto al agua
./iniciar.sh simular mundo_42 --dias 5 # avanza N días lo más rápido posible y lo guarda
./iniciar.sh correr mundo_42 --velocidad 20   # lo deja corriendo en tiempo real SIN pantalla (Ctrl+C guarda)
# Requiere Ollama con el modelo (por defecto qwen3.5:4b; se cambia en el panel "Interruptores del mundo").
# En el visor: abrí un mundo y mirá a los habitantes moverse; velocidades arriba, "Prender fuego" a la derecha.
./iniciar.sh exportar mundo_42         # paquete .zip portable en datos/exportaciones/
./iniciar.sh importar paquete.zip      # restaura un paquete como mundo nuevo (no pisa nada)
```

En el visor: mapa con zoom y arrastre, capas (biomas, altura, temperatura, humedad), datos de cada celda al pasar el mouse,
botón para generar mundos nuevos y exportar. La pestaña **Eventos** muestra el registro de lo que pasa en el mundo, con filtros.
Los mundos se guardan en `datos/mundos/`. Nunca se sobrescriben: generar con una semilla repetida crea otro archivo.

Modelo de vida social: lo que se dicen se guarda completo (tabla `dialogos`, solo para el observador); cada uno recuerda su parte; las relaciones (afecto/confianza) sobreviven a reinicios, así que una pelea puede dejar rencor. En la pestaña Eventos, filtrá por "Conversación" o "Sospecha de simulación".

Tests: `pip install -r requirements-dev.txt` y luego `PYTHONPATH=src python3 -m unittest discover -s tests`.

## Estructura

```
mundo-vivo/
  docs/                 plan maestro y registro de decisiones
  pruebas_cerebro/      Fase 0.5: prueba del modelo (corre sola)
    prueba_cerebro.py
    servidor_simulado.py   (solo para probar el script sin GPU)
    resultados/            informes y bitácoras de cada corrida
  src/mundo_vivo/
    motor/              generador procedural (ruido, biomas, hidrología, clima)
    persistencia/       SQLite, migraciones versionadas, backups, exportar/importar, memoria privada
    agentes/            genoma (temperamento + red de reflejos heredable) y vigilancia de sospechas
    api/                servidor web (FastAPI)
  ui/                   visor 2D y pantalla de eventos (HTML + JavaScript, dibujado por código)
  tests/                pruebas automáticas
  datos/                mundos y backups (NO se borra nunca solo)
```

## Correr la prueba del cerebro (Fase 0.5)

Requisitos: Python 3.8+ y Ollama corriendo con el modelo instalado. No hay que instalar paquetes.

```bash
cd pruebas_cerebro
python3 prueba_cerebro.py --horas 12     # prueba corta primero
python3 prueba_cerebro.py                # prueba completa: 48 horas simuladas
```

Para comparar con otro modelo: `python3 prueba_cerebro.py --modelo qwen2.5:7b`

Prompt: `--prompt v2` (por defecto; señales del cuerpo en palabras, acciones posibles y lenguaje del mundo) o `--prompt v1` (el original; para comparar con informes viejos).

Niveles: `--nivel normal` (fácil, por defecto), `--nivel medio` (comida limitada, más peligro de noche, lugares sin describir hasta visitarlos y hongos venenosos que hay que aprender a evitar) y `--nivel dificil` (casi imposible, solo para estresar). Usar el mismo nivel y semilla al comparar modelos.

Al terminar muestra un informe con veredicto y lo guarda en `pruebas_cerebro/resultados/`.
La bitácora `.jsonl` tiene cada decisión (qué percibió, qué respondió, qué pasó).

## Probar el script sin GPU (opcional)

```bash
python3 servidor_simulado.py --puerto 11555 &
python3 prueba_cerebro.py --host http://localhost:11555 --modelo falso:1b
```


## Animales, recetas y emociones
- Animales: `datos_base/fauna/especies.json` (42 especies). Recetas existentes: `datos_base/recetas/recetas.json`. Materiales: `datos_base/reglas/materiales.json`.
- Para agregar o cambiar sin tocar el código, creá `datos/extra/fauna/*.json`, `datos/extra/recetas/*.json` o `datos/extra/reglas/*.json` (misma forma; mismo `id` reemplaza). Otra carpeta con la variable `MUNDO_VIVO_EXTRA`.
- En el visor: panel **Recetas** (inventadas por ellos / existentes descubiertas / sin descubrir), panel **Animales** y la casilla "Animales" para verlos en el mapa (con zoom se ven como íconos).
- Interruptores nuevos: `fauna` y `emociones`. Modelo al crear el mundo: campo "modelo" en "+ Nuevo mundo"; `./iniciar.sh ajustes NOMBRE --modelo X` lo cambia después.
