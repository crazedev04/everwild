"""Fase B: las propiedades por bioma salen de `datos_base/biomas/biomas.json`, no del código.

Acá está CONGELADA a mano una copia de los tres dicts que antes vivían en Python
(`biomas.BIOMAS`, `navegacion.MULT_BIOMA`, `fuego.COMBUSTIBLE_BASE`). El test exige que lo que
sale del registro sea idéntico, bioma por bioma. Los ids numéricos están guardados en la base de
datos de cada mundo: si uno cambia, los mundos viejos se rompen.
"""
from __future__ import annotations

import unittest

import numpy as np

from mundo_vivo.motor import biomas as B
from mundo_vivo.motor import fuego as F
from mundo_vivo.motor import navegacion as N
from mundo_vivo.registro import Registro

# ------------------------------------------------------------------ copia congelada (NO regenerar)
BIOMAS_CONGELADO = {
    0: ("oceano_profundo", "Océano profundo", "#14305a"),
    1: ("oceano", "Océano", "#1d4f8f"),
    2: ("playa", "Playa", "#e5d8a3"),
    3: ("desierto", "Desierto", "#d9b36a"),
    4: ("sabana", "Sabana", "#b9b45a"),
    5: ("pradera", "Pradera", "#8fbf5a"),
    6: ("bosque_templado", "Bosque templado", "#3f8f4a"),
    7: ("selva", "Selva", "#1a6e36"),
    8: ("pantano", "Pantano", "#5a7a58"),
    9: ("bosque_frio", "Bosque frío", "#3c6e5e"),
    10: ("tundra", "Tundra", "#9aa79a"),
    11: ("nieve", "Nieve", "#f1f4f8"),
    12: ("montana", "Montaña", "#8a8580"),
    13: ("volcan", "Volcán", "#5a3a35"),
    14: ("lago", "Lago", "#3a74b8"),
}

# multiplicador de costo al caminar; los biomas que no están acá eran intransitables (inf)
MULT_BIOMA_CONGELADO = {
    2: 1.0, 3: 1.25, 4: 1.0, 5: 1.0, 6: 1.3, 7: 1.7, 8: 2.2, 9: 1.4, 10: 1.2, 11: 2.0, 12: 1.8, 13: 2.5,
}

# combustible base; los biomas que no están acá arrancaban en 0.0
COMBUSTIBLE_CONGELADO = {
    5: 0.70, 4: 0.75, 6: 0.80, 7: 0.90, 9: 0.60, 8: 0.15, 10: 0.25, 3: 0.10, 12: 0.05, 2: 0.02, 13: 0.20,
}

NOMBRES_CONSTANTES = {
    0: "OCEANO_PROFUNDO", 1: "OCEANO", 2: "PLAYA", 3: "DESIERTO", 4: "SABANA", 5: "PRADERA",
    6: "BOSQUE_TEMPLADO", 7: "SELVA", 8: "PANTANO", 9: "BOSQUE_FRIO", 10: "TUNDRA", 11: "NIEVE",
    12: "MONTANA", 13: "VOLCAN", 14: "LAGO",
}


class TestBiomasDesdeDatos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = Registro.cargar()
        cls.entradas = cls.reg.de_tipo("bioma")

    # ------------------------------------------------------------------ el JSON
    def test_estan_los_quince_de_siempre_y_los_nuevos_van_desde_100(self):
        """Los 15 originales no se tocan (sus ids están en la base de cada mundo) y los que se agreguen
        llevan id desde 100, como quedó fijado en la fase B. Así una dimensión nueva puede traer biomas
        propios sin poner en riesgo un mundo viejo."""
        por_id = {int(d["id_numerico"]): d for d in self.entradas.values()}
        self.assertEqual(len(por_id), len(self.entradas), "hay ids numéricos repetidos")
        for n in BIOMAS_CONGELADO:
            self.assertIn(n, por_id, "desapareció un bioma de los originales")
        for n in por_id:
            if n not in BIOMAS_CONGELADO:
                self.assertGreaterEqual(n, 100, "un bioma nuevo se metió en el rango de los viejos")

    def test_los_ids_numericos_no_cambiaron(self):
        """Están guardados en la base de datos de cada mundo: tocarlos rompe los mundos viejos."""
        for n, (cla, _nom, _col) in BIOMAS_CONGELADO.items():
            d = self.entradas.get(cla)
            self.assertIsNotNone(d, "falta el bioma «%s» en el registro" % cla)
            self.assertEqual(int(d["id_numerico"]), n, "cambió el id numérico de «%s»" % cla)

    def test_nombre_y_color_identicos(self):
        for n, (cla, nom, col) in BIOMAS_CONGELADO.items():
            d = self.entradas[cla]
            self.assertEqual(d["nombre"], nom, cla)
            self.assertEqual(str(d["color"]).lower(), col.lower(), cla)

    def test_velocidad_identica(self):
        for n, (cla, _nom, _col) in BIOMAS_CONGELADO.items():
            v = self.entradas[cla].get("velocidad")
            if n in MULT_BIOMA_CONGELADO:
                self.assertAlmostEqual(float(v), MULT_BIOMA_CONGELADO[n], places=9, msg=cla)
            else:
                self.assertIsNone(v, "«%s» era intransitable y ahora tiene velocidad" % cla)

    def test_combustible_identico(self):
        for n, (cla, _nom, _col) in BIOMAS_CONGELADO.items():
            c = float(self.entradas[cla].get("combustible") or 0.0)
            self.assertAlmostEqual(c, COMBUSTIBLE_CONGELADO.get(n, 0.0), places=9, msg=cla)

    # ------------------------------------------------------------------ el módulo
    def test_el_modulo_expone_lo_mismo_que_antes(self):
        viejos = {n: v for n, v in B.BIOMAS.items() if n in BIOMAS_CONGELADO}
        self.assertEqual(viejos, BIOMAS_CONGELADO)
        self.assertEqual([n for n in B.BIOMAS if n in BIOMAS_CONGELADO], sorted(BIOMAS_CONGELADO),
                         "el orden de BIOMAS cambió")

    def test_las_constantes_por_nombre_siguen_estando(self):
        for n, nombre in NOMBRES_CONSTANTES.items():
            self.assertEqual(getattr(B, nombre), n, nombre)

    # ------------------------------------------------- los arrays que arman motor y navegación
    def test_array_de_costo_de_navegacion(self):
        bioma = np.arange(15, dtype=np.uint8).reshape(3, 5)
        mult = N.mult_bioma(bioma)
        for n in BIOMAS_CONGELADO:
            esperado = MULT_BIOMA_CONGELADO.get(n, float("inf"))
            self.assertAlmostEqual(float(mult.flat[n]), esperado, places=9, msg=str(n))

    def test_array_de_combustible_de_fuego(self):
        bioma = np.arange(15, dtype=np.uint8).reshape(3, 5)
        base = F.combustible_bioma(bioma)
        for n in BIOMAS_CONGELADO:
            self.assertAlmostEqual(float(base.flat[n]), COMBUSTIBLE_CONGELADO.get(n, 0.0), places=6, msg=str(n))


if __name__ == "__main__":
    unittest.main()
