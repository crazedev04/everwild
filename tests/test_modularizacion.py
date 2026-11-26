"""Tests de límites arquitectónicos y desacoplamiento estructural entre los 4 sistemas:
1. Generador de Mundo
2. Motor de Simulación Física
3. Cerebro Cognitivo
4. Render y Presentación Web
"""

import sys
import inspect
from mundo_vivo.generador import pipeline
from mundo_vivo.motor.simulacion import Simulacion
from mundo_vivo.api import presentador


def test_frontera_generador_aislado():
    """El generador no debe acoplarse a WebSocket, red, ni ejecución de simulación viva."""
    mod_text = inspect.getsource(pipeline)
    assert "WebSocket" not in mod_text
    assert "Simulacion" not in mod_text
    assert "HabitanteSim" not in mod_text


def test_frontera_motor_ticks_separados():
    """El motor debe tener explícitamente separados los ticks rápidos y amortizados."""
    assert hasattr(Simulacion, "_tick_rapido_fisica")
    assert hasattr(Simulacion, "_tick_amortizado_sistemas")
    assert hasattr(Simulacion, "_tick_cerebro")


def test_frontera_cerebro_desacoplado():
    """El cerebro cognitivo se comunica mediante buffer/propuestas sin trabar la simulación."""
    sim = Simulacion.__new__(Simulacion)
    sim._propuestas_cerebro = {42: {"tipo": "esperar", "min": 5}}
    
    class FakeHabitante:
        id = 42

    propuesta = sim._tick_cerebro(FakeHabitante())
    assert propuesta == {"tipo": "esperar", "min": 5}
    assert 42 not in sim._propuestas_cerebro


def test_frontera_presentador_snapshots_livianos():
    """El presentador ofrece contratos limpios de serialización desacoplada."""
    assert hasattr(presentador, "estado_liviano")
    assert hasattr(presentador, "estado_completo")
    assert hasattr(presentador, "estado_base")
