import json

from pomodoro_app.config import AppConfig, AnytypeConfig, load_config, save_config


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    config = AppConfig()
    config.pomodoro.work_minutes = 50
    config.gui.theme = "menta"
    save_config(config, str(path))
    loaded = load_config(str(path))
    assert loaded.pomodoro.work_minutes == 50
    assert loaded.gui.theme == "menta"


def test_load_ignores_unknown_keys(tmp_path):
    """Um config.json de outra versão (com chaves que não existem mais) não
    pode impedir a aplicação de abrir."""
    path = tmp_path / "config.json"
    data = AppConfig().to_dict()
    data["anytype"]["chave_antiga"] = "x"
    data["gui"]["outra"] = 1
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_config(str(path)).anytype.base_url == AnytypeConfig().base_url


def test_load_creates_file_on_first_run(tmp_path):
    path = tmp_path / "config.json"
    load_config(str(path))
    assert path.exists()


def test_legacy_portuguese_status_names_are_migrated(tmp_path):
    path = tmp_path / "config.json"
    data = AppConfig().to_dict()
    data["anytype"].update(status_options=["A Fazer", "Fazendo", "Feito"], status_tag_ids={"A Fazer": "t1"},
                           in_progress_status_name="Fazendo", done_status_name="Feito")
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = load_config(str(path))
    assert loaded.anytype.status_options == ["To Do", "In Progress", "Done"]
    assert loaded.anytype.done_status_name == "Done"
    assert loaded.anytype.status_tag_ids == {}


def test_reset_space_cache_forgets_everything_space_specific():
    a = AnytypeConfig(task_type_key="task", status_property_id="p1", status_property_key="status",
                      status_tag_ids={"Done": "t"}, done_checkbox_property_id="d1", done_checkbox_property_key="x",
                      notes_property_id="n1", notes_property_key="notes", api_key="segredo")
    a.reset_space_cache()
    assert (a.task_type_key, a.status_property_id, a.status_property_key, a.status_tag_ids) == ("", "", "", {})
    assert (a.notes_property_id, a.notes_property_key, a.done_checkbox_property_id) == ("", "", "")
    assert a.done_checkbox_property_key == "done"
    assert a.api_key == "segredo"  # o pareamento não depende do espaço


def test_set_status_options():
    a = AnytypeConfig(status_tag_ids={"To Do": "t"})
    assert not a.set_status_options(["To Do", "In Progress", "Done"])  # igual: nada muda
    assert a.status_tag_ids == {"To Do": "t"}
    assert a.set_status_options([" A fazer ", "Feito", ""])
    assert a.status_options == ["A fazer", "Feito"]
    assert a.status_tag_ids == {}
    assert not a.set_status_options([" ", ""])  # vazio é ignorado
