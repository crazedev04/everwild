"""Ecología: composición de EmocionesMixin y EcologiaFaunaMixin.

Mantenida como capa de compatibilidad: los consumidores que importan
`mundo_vivo.motor.ecologia.CANALES` o `EcologiaMixin` siguen funcionando. Toda la
implementación vive en los dos módulos de dominio; esta clase no agrega método propio.
"""
from __future__ import annotations

from .emociones import (  # noqa: F401
    CANALES, VIDA_MEDIA_EMOCION_MIN, _genero,
    EmocionesMixin,
)
from .ecologia_fauna import (  # noqa: F401
    ALCANCE_CUERPO, ALCANCE_LANZA, ALCANCE_ARCO,
    METROS_VISTA_FAUNA, RADIO_PELIGRO,
    EcologiaFaunaMixin,
)


class EcologiaMixin(EmocionesMixin, EcologiaFaunaMixin):
    """Capa de composición: todos los métodos viven en los dos módulos de dominio."""
