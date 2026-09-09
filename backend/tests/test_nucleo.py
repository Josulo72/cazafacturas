import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.nucleo.esquema import (
    DesgloseIVA,
    Direccion,
    Empresa,
    Factura,
    LineaFactura,
    TipoFactura,
)
from backend.nucleo.evaluador import (
    EstadoCampo,
    evaluar_factura,
    evaluar_respuesta_json,
)


def factura_valida() -> Factura:
    emisor = Empresa(
        nombre="Tecnología del Sur S.L.",
        nif="B12345678",
        direccion=Direccion(
            calle="Calle Gran Vía 42",
            ciudad="Madrid",
            provincia="Madrid",
            codigo_postal="28001",
        ),
    )
    receptor = Empresa(
        nombre="Materiales Hermanos S.A.",
        nif="A99887766",
        direccion=Direccion(
            calle="Ctra. de Barcelona km 12",
            ciudad="Valencia",
            provincia="Valencia",
            codigo_postal="46001",
        ),
    )
    linea = LineaFactura(
        descripcion="Licencia software anual",
        cantidad=2,
        precio_unitario=450.0,
        importe=900.0,
    )
    return Factura(
        numero="F/2025/0123",
        fecha_emision=date(2025, 3, 15),
        fecha_vencimiento=date(2025, 4, 14),
        emisor=emisor,
        receptor=receptor,
        lineas=[linea],
        base_imponible=900.0,
        iva=[DesgloseIVA(porcentaje=21.0, base_imponible=900.0, cuota=189.0)],
        total=1089.0,
    )


class TestEsquema(unittest.TestCase):
    def test_factura_valida(self):
        factura = factura_valida()
        self.assertEqual(factura.numero, "F/2025/0123")

    def test_importe_incorrecto_rechazado(self):
        with self.assertRaises(ValueError):
            LineaFactura(
                descripcion="prueba",
                cantidad=2,
                precio_unitario=450.0,
                importe=999.0,
            )

    def test_base_incoherente_rechazada(self):
        factor = factura_valida()
        datos = factor.model_dump()
        datos["base_imponible"] = 1000.0
        with self.assertRaises(ValueError):
            Factura(**datos)

    def test_completa_requiere_receptor(self):
        factor = factura_valida()
        datos = factor.model_dump()
        datos["receptor"] = None
        with self.assertRaises(ValueError):
            Factura(**datos)

    def test_simplificada_sin_receptor_valida(self):
        factor = factura_valida()
        datos = factor.model_dump()
        datos["tipo"] = TipoFactura.SIMPLIFICADA
        datos["receptor"] = None
        factura = Factura(**datos)
        self.assertEqual(factura.tipo, TipoFactura.SIMPLIFICADA)


class TestEvaluador(unittest.TestCase):
    def setUp(self):
        esperado = factura_valida().model_dump(mode="json")
        self.esperado = esperado

    def test_respuesta_identica_todo_aciertos(self):
        resultado = evaluar_factura(self.esperado, self.esperado)
        self.assertEqual(resultado.precision, 1.0)
        self.assertEqual(resultado.tasa_invencion, 0.0)
        self.assertEqual(len(resultado.fallos), 0)
        self.assertEqual(len(resultado.invenciones), 0)

    def test_campo_inventado_detectado(self):
        obtenido = dict(self.esperado)
        obtenido["clave_operacion"] = "N1"
        resultado = evaluar_factura(self.esperado, obtenido)
        self.assertEqual(len(resultado.invenciones), 1)
        self.assertTrue(
            any(c.campo == "clave_operacion" for c in resultado.invenciones)
        )

    def test_campo_con_esperado_vacio_e_inventado(self):
        esperado = dict(self.esperado)
        esperado["observaciones"] = None
        obtenido = dict(esperado)
        obtenido["observaciones"] = "Descuento aplicado del 5%"
        resultado = evaluar_factura(esperado, obtenido)
        self.assertTrue(
            any(c.campo == "observaciones" and c.estado == EstadoCampo.INVENCION
                for c in resultado.campos)
        )

    def test_valor_incorrecto_cae_como_fallo(self):
        obtenido = dict(self.esperado)
        obtenido["total"] = 2000.0
        resultado = evaluar_factura(self.esperado, obtenido)
        self.assertTrue(
            any(c.campo == "total" and c.estado == EstadoCampo.FALLO
                for c in resultado.campos)
        )

    def test_normaliza_fechas_formato_espanol(self):
        obtenido = dict(self.esperado)
        obtenido["fecha_emision"] = "15/03/2025"
        resultado = evaluar_factura(self.esperado, obtenido)
        self.assertTrue(
            any(c.campo == "fecha_emision" and c.estado == EstadoCampo.ACIERTO
                for c in resultado.campos)
        )

    def test_normaliza_nif_con_guiones(self):
        obtenido = dict(self.esperado)
        obtenido["emisor"]["nif"] = "B-12345678"
        resultado = evaluar_factura(self.esperado, obtenido)
        self.assertTrue(
            any(c.campo == "emisor.nif" and c.estado == EstadoCampo.ACIERTO
                for c in resultado.campos)
        )

    def test_respuesta_json_en_bloque_markdown(self):
        import json

        texto = '```json\n' + json.dumps(self.esperado, ensure_ascii=False) + '\n```'
        resultado = evaluar_respuesta_json(texto, self.esperado, "f1")
        self.assertEqual(resultado.precision, 1.0)

    def test_respuesta_json_invalida(self):
        resultado = evaluar_respuesta_json("esto no es json", self.esperado, "f1")
        self.assertGreater(len(resultado.fallos_validacion), 0)
        self.assertLess(resultado.precision, 1.0)


if __name__ == "__main__":
    unittest.main()