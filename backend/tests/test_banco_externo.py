"""El extractor contra facturas que no ha generado él.

Quince maquetaciones de terceros. Es la prueba que el banco interno no podía
hacer: allí el mismo código escribía y leía, aquí no.
"""

import pytest

from backend.nucleo import banco_externo

pytestmark = pytest.mark.skipif(
    not banco_externo.disponible(), reason="falta dataset/externo"
)


@pytest.fixture(scope="module")
def informe():
    return banco_externo.ejecutar()


def test_estan_las_veintitres(informe):
    assert len(informe.casos) == 23


def test_cada_campo_en_su_sitio(informe):
    fallos = [f"{c.fichero}.{x.nombre}: esperado {x.esperado!r}, leído {x.obtenido!r}"
              for c in informe.casos for x in c.campos_mal]
    assert not fallos, "\n".join(fallos)


def test_las_quince_normales_salen_conformes(informe):
    malas = [f"{c.fichero}: {c.estado} {c.ruido}"
             for c in informe.casos if c.motivo is None and not c.correcto]
    assert not malas, "\n".join(malas)


def test_las_ocho_defectuosas_caen_por_su_motivo_y_solo_por_el(informe):
    malas = [f"{c.fichero}: {c.estado}, esperaba {c.motivo}, saltó {c.errores}"
             for c in informe.casos if c.motivo is not None and not c.correcto]
    assert not malas, "\n".join(malas)


def test_ninguna_se_queda_en_no_legible(informe):
    assert informe.no_legibles == 0
