"""
Comportamiento congelado de las propiedades que se pueden comprobar al inventar.

Las 19 primeras se escribieron ANTES de pasar las reglas a datos
(`datos_base/propiedades/propiedades.json`): describen exactamente lo que hacían las lambdas de
`agentes/conocimiento.py`, para que la mudanza a JSON no cambie ni una decisión ni un mensaje de error.

Las 8 últimas son la fase 1 del plan del motor (el vocabulario de la edad de los metales). Cada caso
fija también lo que NO se cumple, que es lo que importa al agregar una propiedad: una condición floja
convierte en válidas combinaciones que no deberían serlo.
"""
from __future__ import annotations

import unittest

from mundo_vivo.agentes import conocimiento as C
from mundo_vivo.reglas import Reglas


def reglas_con(**materiales) -> Reglas:
    """Un mundo de mentira con los materiales que haga falta."""
    return Reglas(dict(materiales), [], "prueba")


# Cada caso: propiedad -> (descripción esperada, mensaje de error esperado, [materiales que SÍ], [materiales que NO])
# Los materiales son dicts sueltos; cada lista de listas es una combinación a probar.
CASOS = {
    "flota": (
        "todos los materiales son menos densos que el agua",
        "No flota: algún material es más pesado que el agua.",
        [[{"densidad_kg_m3": 600}],
         [{"densidad_kg_m3": 600}, {"densidad_kg_m3": 999.9}],
         [{"densidad_kg_m3": 0}]],
        [[{"densidad_kg_m3": 1000}],                                  # igual que el agua no flota
         [{"densidad_kg_m3": 600}, {"densidad_kg_m3": 2700}],
         [{}],                                                        # sin densidad conocida: no flota
         [{"densidad_kg_m3": 600}, {}]],
    ),
    "corta": (
        "alguno de los materiales es duro (dureza Mohs >= 5)",
        "No corta: ningún material es lo bastante duro.",
        [[{"dureza_mohs": 5}], [{"dureza_mohs": 7}], [{"dureza_mohs": 2}, {"dureza_mohs": 6}]],
        [[{"dureza_mohs": 4.9}], [{}], [{"dureza_mohs": 2}, {"dureza_mohs": 3}]],
    ),
    "perfora": (
        "alguno de los materiales aguanta una punta (dureza Mohs >= 3.5)",
        "No perfora: nada de eso aguanta una punta.",
        [[{"dureza_mohs": 3.5}], [{"dureza_mohs": 2}, {"dureza_mohs": 4}]],
        [[{"dureza_mohs": 3.4}], [{}]],
    ),
    "arde": (
        "alguno de los materiales es inflamable",
        "No arde: ningún material es inflamable.",
        [[{"inflamable": True}], [{}, {"inflamable": True}]],
        [[{"inflamable": False}], [{}], [{}, {"inflamable": False}]],
    ),
    "ilumina": (
        "algo arde y algo hace que dure (resina, grasa, carbón)",
        "No ilumina: hace falta algo que arda y algo que arda despacio (resina, grasa).",
        [[{"inflamable": True, "lento": True}],
         [{"inflamable": True}, {"lento": True}]],
        [[{"inflamable": True}], [{"lento": True}], [{}], [{"inflamable": False}, {"lento": True}]],
    ),
    "enciende": (
        "alguno de los materiales da chispas o brasa al frotarlo",
        "No enciende: nada de eso da chispas ni brasa.",
        [[{"chispa": True}], [{"friccion": True}], [{}, {"chispa": True}]],
        [[{"chispa": False, "friccion": False}], [{}]],
    ),
    "conduce": (
        "alguno de los materiales conduce la electricidad",
        "No conduce: ningún material conduce la electricidad.",
        [[{"conduce_electricidad": True}], [{}, {"conduce_electricidad": True}]],
        [[{"conduce_electricidad": False}], [{}]],
    ),
    "abriga": (
        "alguno de los materiales es aislante (guarda el calor del cuerpo)",
        "No abriga: ningún material guarda el calor.",
        [[{"aislante": True}], [{}, {"aislante": True}]],
        [[{"aislante": False}], [{}]],
    ),
    "ata": (
        "alguno de los materiales es flexible (sirve para atar)",
        "No ata: ningún material es flexible.",
        [[{"flexible": True}], [{}, {"flexible": True}]],
        [[{"flexible": False}], [{}]],
    ),
    "teje": (
        "alguno de los materiales es fibroso (se puede hilar o tejer)",
        "No teje: nada de eso se puede hilar.",
        [[{"fibroso": True}], [{}, {"fibroso": True}]],
        [[{"fibroso": False}], [{}]],
    ),
    "contiene": (
        "alguno de los materiales sirve de envase (se trenza, moldea o cose)",
        "No contiene: nada de eso sirve de envase.",
        [[{"envase": True}], [{}, {"envase": True}]],
        [[{"envase": False}], [{}]],
    ),
    "construye": (
        "alguno de los materiales sirve para levantar paredes o techo",
        "No construye: nada de eso aguanta como estructura.",
        [[{"estructural": True}], [{}, {"estructural": True}]],
        [[{"estructural": False}], [{}]],
    ),
    "impermeabiliza": (
        "alguno de los materiales repele el agua",
        "No impermeabiliza: nada de eso repele el agua.",
        [[{"impermeable": True}], [{}, {"impermeable": True}]],
        [[{"impermeable": False}], [{}]],
    ),
    "protege": (
        "alguno de los materiales resiste golpes",
        "No protege: nada de eso resiste golpes.",
        [[{"resistente": True}], [{}, {"resistente": True}]],
        [[{"resistente": False}], [{}]],
    ),
    "dispara": (
        "alguno de los materiales es elástico (guarda fuerza al tensarlo)",
        "No dispara: nada de eso es elástico.",
        [[{"elastico": True}], [{}, {"elastico": True}]],
        [[{"elastico": False}], [{}]],
    ),
    "pega": (
        "alguno de los materiales es adhesivo",
        "No pega: nada de eso es pegajoso.",
        [[{"adhesivo": True}], [{}, {"adhesivo": True}]],
        [[{"adhesivo": False}], [{}]],
    ),
    "cura": (
        "alguno de los materiales es medicinal",
        "No cura: nada de eso tiene efecto medicinal.",
        [[{"medicinal": True}], [{}, {"medicinal": True}]],
        [[{"medicinal": False}], [{}]],
    ),
    "conserva": (
        "algo es conservante (sal, ceniza, miel) y algo se puede comer",
        "No conserva: hace falta un conservante (sal, ceniza, miel) junto a algo comestible.",
        [[{"conservante": True, "comestible": True}],
         [{"conservante": True}, {"comestible": True}]],
        [[{"conservante": True}], [{"comestible": True}], [{}]],
    ),
    "alimenta": (
        "alguno de los materiales se puede comer",
        "No alimenta: nada de eso se puede comer.",
        [[{"comestible": True}], [{}, {"comestible": True}]],
        [[{"comestible": False}], [{}]],
    ),
    # --- fase 1 del plan del motor: el vocabulario de la edad de los metales.
    # `funde` se apoya en el campo que YA existía (`punto_fusion_C`): una magnitud, un solo nombre.
    "funde": (
        "alguno de los materiales se derrite con bastante calor",
        "No funde: nada de eso se derrite, por más fuego que se le ponga.",
        [[{"punto_fusion_C": 1200}], [{}, {"punto_fusion_C": 330}]],
        [[{}], [{"punto_ignicion_C": 300}]],
    ),
    "golpea": (
        "alguno de los materiales es pesado y duro (sirve para un pico o una maza)",
        "No golpea: nada de eso es lo bastante pesado y duro.",
        [[{"densidad_kg_m3": 2700, "dureza_mohs": 6}],
         [{"densidad_kg_m3": 2500, "dureza_mohs": 5}],
         [{"densidad_kg_m3": 600}, {"densidad_kg_m3": 2600, "dureza_mohs": 7}]],
        [[{"densidad_kg_m3": 2400, "dureza_mohs": 7}],            # liviano: no sirve de maza
         [{"densidad_kg_m3": 7870, "dureza_mohs": 4}],            # pesado pero blando
         [{"densidad_kg_m3": 2700}, {"dureza_mohs": 6}],          # repartido entre dos: no vale
         [{}]],
    ),
    "clava": (
        "alguno de los materiales es dúctil y resistente (se estira en clavo sin quebrarse)",
        "No clava: nada de eso se estira sin quebrarse.",
        [[{"ductil": True, "resistente": True}],
         [{"dureza_mohs": 7}, {"ductil": True, "resistente": True}]],
        [[{"ductil": True}], [{"resistente": True}],
         [{"ductil": True}, {"resistente": True}], [{}]],
    ),
    "mezcla": (
        "alguno de los materiales es aglomerante (une lo demás al secarse)",
        "No mezcla: nada de eso une al secarse.",
        [[{"aglomerante": True}], [{}, {"aglomerante": True}]],
        [[{"aglomerante": False}], [{}]],
    ),
    "muele": (
        "alguno de los materiales es denso y duro (aguanta moler sin desarmarse)",
        "No muele: nada de eso aguanta moler.",
        [[{"densidad_kg_m3": 2700, "dureza_mohs": 6}], [{"densidad_kg_m3": 2000, "dureza_mohs": 7}]],
        [[{"densidad_kg_m3": 1999, "dureza_mohs": 7}],
         [{"densidad_kg_m3": 2700, "dureza_mohs": 5.9}], [{}]],
    ),
    "afila": (
        "alguno de los materiales es durísimo (dureza Mohs >= 7): saca filo",
        "No afila: nada de eso es más duro que lo que se quiere afilar.",
        [[{"dureza_mohs": 7}], [{"dureza_mohs": 6}, {"dureza_mohs": 9}]],
        [[{"dureza_mohs": 6.9}], [{}]],
    ),
    "imanta": (
        "alguno de los materiales atrae al hierro por sí solo",
        "No imanta: nada de eso atrae al hierro.",
        [[{"magnetico": True}], [{}, {"magnetico": True}]],
        [[{"magnetico": False}], [{}]],
    ),
    "aisla": (
        "alguno de los materiales no pasa el calor ni la electricidad",
        "No aísla: todo eso pasa el calor o la corriente.",
        [[{"conductividad_W_mK": 0.15, "conduce_electricidad": False}],
         [{"conductividad_W_mK": 400, "conduce_electricidad": True},
          {"conductividad_W_mK": 0.04, "conduce_electricidad": False}]],
        [[{"conductividad_W_mK": 0.15, "conduce_electricidad": True}],   # el grafito pasa corriente
         [{"conductividad_W_mK": 2.5, "conduce_electricidad": False}],   # la piedra pasa el calor
         [{"conduce_electricidad": False}],                              # sin conductividad conocida: no se sabe
         [{}]],
    ),
}


class TestPropiedades(unittest.TestCase):
    def test_estan_todas_y_con_su_descripcion(self):
        self.assertEqual(len(C.PROPIEDADES), 27)        # las 19 originales + las 8 de la fase 1
        self.assertEqual(set(C.PROPIEDADES), set(CASOS))
        for prop, (desc, _err, _si, _no) in CASOS.items():
            self.assertEqual(C.PROPIEDADES[prop], desc, prop)

    def test_cada_propiedad_decide_igual_que_siempre(self):
        for prop, (desc, err, casos_si, casos_no) in CASOS.items():
            for mats in casos_si:
                reglas, nombres = self._mundo(mats)
                ok, msg = C.validar(reglas, "chuchería", nombres, prop)
                self.assertTrue(ok, "%s debería valer con %r (%s)" % (prop, mats, msg))
                self.assertEqual(msg, "Comprobado: " + desc + ".")
            for mats in casos_no:
                reglas, nombres = self._mundo(mats)
                ok, msg = C.validar(reglas, "chuchería", nombres, prop)
                self.assertFalse(ok, "%s NO debería valer con %r" % (prop, mats))
                self.assertEqual(msg, err, prop)

    # ------------------------------------------------------------ validaciones de forma
    def test_nombre_entre_2_y_40_letras(self):
        reglas, nombres = self._mundo([{"comestible": True}])
        for malo in ("", " ", "a", "x" * 41):
            ok, msg = C.validar(reglas, malo, nombres, "alimenta")
            self.assertFalse(ok)
            self.assertEqual(msg, "El nombre debe tener entre 2 y 40 letras.")
        self.assertTrue(C.validar(reglas, "  pan  ", nombres, "alimenta")[0], "se recortan los espacios")
        self.assertTrue(C.validar(reglas, "x" * 40, nombres, "alimenta")[0])

    def test_entre_1_y_5_materiales(self):
        reglas, nombres = self._mundo([{"comestible": True}] * 6)
        ok, msg = C.validar(reglas, "cosa", nombres, "alimenta")
        self.assertFalse(ok)
        self.assertEqual(msg, "Hay que usar entre 1 y 5 materiales.")
        ok, msg = C.validar(reglas, "cosa", [], "alimenta")
        self.assertFalse(ok)
        self.assertEqual(msg, "Hay que usar entre 1 y 5 materiales.")
        self.assertTrue(C.validar(reglas, "cosa", nombres[:5], "alimenta")[0])

    def test_material_inexistente(self):
        reglas, _ = self._mundo([{"comestible": True}])
        ok, msg = C.validar(reglas, "cosa", ["unobtanio"], "alimenta")
        self.assertFalse(ok)
        self.assertEqual(msg, "No existe el material 'unobtanio' en este mundo.")

    def test_propiedad_inexistente(self):
        reglas, nombres = self._mundo([{"comestible": True}])
        ok, msg = C.validar(reglas, "cosa", nombres, "teletransporta")
        self.assertFalse(ok)
        self.assertTrue(msg.startswith("Eso todavía no se puede comprobar en este mundo (se puede comprobar: "))
        for prop in CASOS:
            self.assertIn(prop, msg)

    def test_ninguna_receta_del_catalogo_queda_invalida(self):
        """La red de seguridad al tocar el vocabulario: toda receta tiene que seguir cumpliendo SU propiedad.

        Al agregar una propiedad, el riesgo es doble: una condición floja vuelve válido lo que no debería,
        y una condición apretada deja inválida una receta que venía andando. Esto corre el evaluador de
        verdad sobre las 128 recetas del catálogo con sus materiales reales.
        """
        from mundo_vivo import catalogos
        from mundo_vivo.reglas import Reglas

        reglas = Reglas.cargar()
        etiquetas = catalogos.cargar_etiquetas()
        recetas = catalogos.cargar_recetas(reglas.materiales, C.PROPIEDADES)
        for rid, r in sorted(recetas.items()):
            if any(m.startswith("#") and not etiquetas[m[1:]] for m in r["ingredientes"]):
                continue      # `#mena_desconocida` la llena cada mundo con lo que sortea de su semilla
            ing = [sorted(etiquetas[m[1:]])[0] if m.startswith("#") else m for m in r["ingredientes"]]
            ok, msg = C.validar(reglas, r["nombre"], ing, r["propiedad"])
            self.assertTrue(ok, "la receta '%s' (%s) dejó de cumplir su propiedad: %s" % (rid, ing, msg))

    # --------------------------------------------------------------------- utilidades
    @staticmethod
    def _mundo(mats):
        nombres = ["m%d" % i for i in range(len(mats))]
        return reglas_con(**{n: dict(m) for n, m in zip(nombres, mats)}), nombres


if __name__ == "__main__":
    unittest.main()
