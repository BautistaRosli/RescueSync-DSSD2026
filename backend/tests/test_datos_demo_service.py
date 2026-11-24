from types import SimpleNamespace

from app.services.datos_demo_service import _aportes_demo_por_organizacion


def test_aportes_demo_reparte_el_total_entre_participantes():
    oferta = SimpleNamespace(
        organizacion_id=7,
        organizaciones=[SimpleNamespace(id=3)],
        es_conjunta=True,
    )
    item = SimpleNamespace(cantidad_ofrecida=5)

    aportes = _aportes_demo_por_organizacion(oferta, item)

    assert aportes == {7: 3, 3: 2}
    assert sum(aportes.values()) == item.cantidad_ofrecida
