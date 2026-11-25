import unittest
from mundo_vivo.motor.vida import VidaMixin
from mundo_vivo.motor.simulacion import HabitanteSim

class MockSim(VidaMixin):
    def __init__(self):
        self.habitantes = {}
        self.t = 1000.0
        self.r_habla = 10.0
        self.eventos = []
        self.hitos = set()
    def modulo(self, m):
        return True
    def _evento(self, *args, **kwargs):
        self.eventos.append((args, kwargs))
    def _recuerdo(self, *args, **kwargs):
        pass
    def sentir(self, *args, **kwargs):
        pass
    def experiencia(self, *args, **kwargs):
        pass
    def _interrumpir(self, h):
        pass

class TestRelacionesFase8(unittest.TestCase):
    def test_colapso_genetico_permite_medio_hermanos(self):
        sim = MockSim()
        h1 = HabitanteSim(1, "H1", 0.0, 0.0)
        h1.sexo = "M"
        h1.nac = 0.0
        h1.padre_id = 10
        h1.madre_id = 11

        h2 = HabitanteSim(2, "H2", 0.0, 0.0)
        h2.sexo = "F"
        h2.nac = 0.0
        h2.padre_id = 10
        h2.madre_id = 12

        sim.habitantes = {1: h1, 2: h2}
        sim.t = 25 * 1440.0 # 25 días (adultos)
        
        # Con población baja (<10), _colapso_genetico da True y parentesco_cercano permite medio hermanos
        self.assertTrue(sim._colapso_genetico(sim))
        par = sim.parentesco_cercano(h1, h2, sim=sim)
        self.assertIsNone(par, "En colapso genético, medio hermanos deben permitirse para evitar extinción")

    def test_infidelidad_dispara_traicion_en_pareja(self):
        sim = MockSim()
        sim.t = 25 * 1440.0
        h1 = HabitanteSim(1, "Hombre", 0.0, 0.0)
        h1.sexo = "M"
        h2 = HabitanteSim(2, "Mujer1", 0.0, 0.0)
        h2.sexo = "F"
        h3 = HabitanteSim(3, "Mujer2", 0.0, 0.0)
        h3.sexo = "F"
        for h in (h1, h2, h3):
            h.nac = 0.0
            h.padre_id = None
            h.madre_id = None
            h.embarazo = None
            h.sin_concebir_hasta = 0.0
            h.propuesta = None

        # Pareja formal: h1 y h2
        h1.pareja_id = 2
        h2.pareja_id = 1

        sim.habitantes = {1: h1, 2: h2, 3: h3}

        # h1 le propone familia a h3 (engaña a h2)
        ok, msg = sim._accion_proponer_hijo(h1, {"a": 3})
        self.assertTrue(ok)
        
        # Verificar evento de relación con traición
        traiciones = [ev for ev in sim.eventos if ev[1].get("datos", {}).get("motivo", "").startswith("traición")]
        self.assertEqual(len(traiciones), 1)
        self.assertEqual(traiciones[0][1]["datos"]["hab"], 2) # Mujer1 fue notificada

if __name__ == "__main__":
    unittest.main()
