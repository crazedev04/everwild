import tempfile
from pathlib import Path
from mundo_vivo.persistencia import db, mundo_io, sim_io
import zlib

def test_metricas_telemetria_y_cache():
    with tempfile.TemporaryDirectory() as tmp:
        dir_path = Path(tmp)
        ruta = mundo_io.crear_mundo(dir_path, 42, 64, 64, tam_celda_m=50)
        con = db.abrir(ruta)
        sim = sim_io.cargar_simulacion(con)
        ter = sim.terreno
        m = ter.metricas_cache()
        assert "hits" in m
        assert "misses" in m
        assert "hit_rate" in m
        assert "cache_size" in m

def test_compresion_capas_sim_io():
    raw = b"\x00" * 1024
    comp = zlib.compress(raw, level=1)
    assert len(comp) < len(raw)
    decomp = zlib.decompress(comp)
    assert decomp == raw
