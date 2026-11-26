"""Tecnologia: composicion de MaterialesMixin, EstructurasMixin y FabricacionMixin.

Mantida como capa de compatibilidad: los consumidores que importan
`mundo_vivo.motor.tecnologia.TecnologiaMixin` o sus constantes de nivel de modulo
siguen funcionando sin cambios. Toda la implementacion vive en los tres modulos
de dominio; esta clase no agrega metodo propio.
"""
from __future__ import annotations

from .materiales import (  # noqa: F401
    DIAS_REGENERAR, MIN_DIA, TIEMPO_JUNTAR_MIN, METROS_ZONA,
    _BOSQUES, _PASTOS, MaterialesMixin,
)
from .estructuras import (  # noqa: F401
    DURA_ANTORCHA_MIN, MIN_LENA, FOGATA_MIN_POR_LENA,
    METROS_CALOR_FOGATA, METROS_CALOR_REFUGIO, METROS_ALDEA,
    MAX_REFUGIOS_POR_PERSONA, DIAS_SIN_USO, DESGASTE_POR_DIA, MIN_ABRIGO,
    EstructurasMixin,
)
from .fabricacion import (  # noqa: F401
    PROVISIONES, FabricacionMixin,
)


class TecnologiaMixin(MaterialesMixin, EstructurasMixin, FabricacionMixin):
    """Capa de composicion: todos los metodos viven en los tres modulos de dominio."""
