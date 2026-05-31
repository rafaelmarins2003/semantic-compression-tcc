"""Tests for BPMN 2.0 XSD validation of transpiler output."""

from src.transpiler import transpile
from src.transpiler.xsd import validate_bpmn_xsd


def test_valid_process_passes_xsd():
    xml = transpile('process "P" { start "Begin" -> task "A" -> end "Done" }')
    assert validate_bpmn_xsd(xml) == []


def test_xor_gateway_passes_xsd():
    xml = transpile(
        'process "P" { start -> xor "D" { [yes] -> task "A" [no] -> () } -> end }'
    )
    assert validate_bpmn_xsd(xml) == []


def test_malformed_xml_is_reported_not_raised():
    errs = validate_bpmn_xsd("<definitions><process></definitions>")
    assert errs and "not well-formed" in errs[0]


def test_unicode_name_yields_valid_xs_id():
    # Regressão: 'º' (U+00BA) é alnum no Python mas inválido como xs:ID/NCName.
    # O id do processo é derivado do nome via _safe_id; deve continuar XSD-válido.
    xml = transpile('process "Clientes Antes de 1º de Fevereiro" { start -> end }')
    assert validate_bpmn_xsd(xml) == []
