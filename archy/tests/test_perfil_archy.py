import perfil_archy as P


def test_solo_quedan_las_herramientas_de_archy():
    actuales = {"execute_command": {"enabled": True, "custom_prompt": "x"},
                "search": {"enabled": True, "custom_prompt": None, "lazy_load": False}}
    nuevos = P.solo_herramientas_de_archy(actuales, ["execute_command", "search", "website", "todo"])
    activas = {n for n, v in nuevos.items() if v["enabled"]}
    assert activas == set(P.HERRAMIENTAS_ARCHY)
    for nombre in ("execute_command", "search", "website", "todo"):
        assert nuevos[nombre]["enabled"] is False
    assert nuevos["execute_command"]["custom_prompt"] == "x"      # se conservan los demás datos
    assert nuevos["search"]["lazy_load"] is False
    assert actuales["execute_command"]["enabled"] is True          # no modifica el original


def test_terminal_y_busqueda_web_siempre_en_la_lista_conocida():
    # Reglas éticas: sin terminal ni búsqueda web aunque no se puedan listar desde la app.
    for nombre in ("execute_command", "search", "website", "saludar"):
        assert nombre in P.HERRAMIENTAS_CONOCIDAS


def test_tolera_ajustes_vacios_o_raros():
    nuevos = P.solo_herramientas_de_archy({"rota": "no es dict"}, [])
    assert {n for n, v in nuevos.items() if v["enabled"]} == set(P.HERRAMIENTAS_ARCHY)


def test_prompts_que_confunden_a_qwen_se_apagan():
    for clave in ("environment", "source_attribution", "todo", "personality-prompt", "expression-prompt"):
        assert clave in P.PROMPTS_APAGADOS
    assert "tools" not in P.PROMPTS_APAGADOS          # de ahí salen las herramientas del modelo
    assert "rag_search_files" in P.HERRAMIENTAS_CONOCIDAS
