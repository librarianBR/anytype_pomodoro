import datetime as dt

import pytest

from pomodoro_app.task_manager import SetupError, TaskManager, parse_created_date, parse_due_date

from .conftest import FakeClient, make_config, prop


def test_setup_discovers_type_properties_and_creates_tags(manager, config):
    a = config.anytype
    assert a.task_type_key == "task"
    assert (a.status_property_id, a.status_property_key) == ("prop-status", "status")
    assert set(a.status_tag_ids) == {"To Do", "In Progress", "Done"}
    assert a.notes_property_key == "notes"


def test_setup_explains_missing_task_type():
    tm = TaskManager(FakeClient(with_task_type=False), make_config())
    with pytest.raises(SetupError, match="tipo chamado 'Task'"):
        tm.setup()


def test_setup_requires_a_space():
    with pytest.raises(SetupError, match="espaço"):
        TaskManager(FakeClient(), make_config(space_id="")).setup()


def test_create_task_with_due_date_and_story(manager, client):
    task = manager.create_task("Revisar aula", description="  Como aluno, quero revisar.  ",
                               status="To Do", due=dt.date(2026, 11, 15))
    assert task.id and task.status == "To Do"
    assert task.due == dt.date(2026, 11, 15)
    assert task.description == "Como aluno, quero revisar."
    stored = client.objects[task.id]
    # formatos que a API aceita (descobertos testando contra o Anytype real)
    assert prop(stored, "due_date")["date"] == "2026-11-15T00:00:00Z"
    assert prop(stored, "description")["text"] == "Como aluno, quero revisar."


def test_create_task_without_optional_fields(manager, client):
    task = manager.create_task("Só o nome")
    assert task.status == "To Do" and task.due is None and task.description == ""
    assert prop(client.objects[task.id], "due_date") is None


def test_set_status_syncs_native_done_checkbox(manager, client):
    task = manager.create_task("Tarefa")
    assert manager.set_status(task.id, "Done").status == "Done"
    assert prop(client.objects[task.id], "done")["checkbox"] is True
    manager.set_status(task.id, "To Do")
    assert prop(client.objects[task.id], "done")["checkbox"] is False


def test_unknown_status_is_reported(manager):
    task = manager.create_task("Tarefa")
    with pytest.raises(SetupError, match="Inexistente"):
        manager.set_status(task.id, "Inexistente")


def test_list_pending_tasks(manager):
    done = manager.create_task("Feita", status="Done")
    manager.create_task("Pendente")
    assert [t.name for t in manager.list_pending_tasks()] == ["Pendente"]
    assert done.id in {t.id for t in manager.list_tasks()}


def test_rename_and_delete(manager):
    task = manager.create_task("Nome antigo")
    assert manager.rename_task(task.id, "Nome novo").name == "Nome novo"
    manager.delete_task(task.id)
    assert manager.list_tasks() == []


def test_notes_are_appended_with_timestamp(manager):
    task = manager.create_task("Tarefa")
    manager.add_note(task.id, "primeira")
    manager.add_note(task.id, "segunda")
    lines = manager.get_task_notes(task.id).splitlines()
    assert len(lines) == 2
    assert lines[0].endswith("] primeira") and lines[1].endswith("] segunda")
    assert lines[0].startswith("[")


def test_notes_without_notes_property_explain_what_to_do():
    tm = TaskManager(FakeClient(with_notes=False), make_config())
    tm.setup()
    task = tm.create_task("Tarefa")
    with pytest.raises(SetupError, match="Notes"):
        tm.add_note(task.id, "x")


def test_select_space_forgets_previous_space(manager, config):
    manager.select_space("space-2")
    assert config.anytype.space_id == "space-2"
    assert config.anytype.task_type_key == "" and config.anytype.status_tag_ids == {}
    assert config.anytype.notes_property_key == ""


def test_status_shown_as_question_mark_when_unknown(manager):
    assert manager.to_task({"id": "x", "name": "Sem status", "properties": []}).status == "?"


def test_status_recognized_by_tag_name_when_id_is_unknown(manager):
    obj = {"id": "x", "name": "t", "properties": [{"key": "status", "select": {"id": "outra", "name": "Feito"}}]}
    assert manager.to_task(obj).status == "Feito"


def test_due_date_is_not_shifted_by_timezone():
    """Meia-noite UTC não pode virar o dia anterior no Brasil (UTC-3)."""
    assert parse_due_date({"date": "2026-11-15T00:00:00Z"}) == dt.date(2026, 11, 15)
    assert parse_due_date({"date": ""}) is None
    assert parse_due_date({"date": "lixo"}) is None
    assert parse_due_date(None) is None


def test_created_date_is_converted_to_local_time():
    created = parse_created_date({"date": "2026-06-12T18:35:57Z"})
    assert created.tzinfo is not None
    assert created.astimezone(dt.timezone.utc) == dt.datetime(2026, 6, 12, 18, 35, 57, tzinfo=dt.timezone.utc)
    assert parse_created_date({"date": "lixo"}) is None
