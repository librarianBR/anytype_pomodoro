import pytest

from pomodoro_app.anytype_client import AnytypeError
from pomodoro_app.pomodoro_timer import Phase, PomodoroStatus
from pomodoro_app.session import NOTE_LINKED, NOTE_UNLINKED, PomodoroSession


@pytest.fixture
def session(config, manager):
    return PomodoroSession(config, manager)


def notes(manager, task_id):
    return [line.split("] ", 1)[1] for line in manager.get_task_notes(task_id).splitlines()]


def status_of(manager, task_id):
    return next(t.status for t in manager.list_tasks() if t.id == task_id)


class FakeTimer:
    def __init__(self, status=None):
        self._status = status
        self.paused = False

    def status(self):
        return self._status

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False


def test_link_marks_in_progress_and_records_history(session, manager):
    task = manager.create_task("Tarefa")
    assert session.link(task.id) == []
    assert session.linked_task_id == task.id
    assert status_of(manager, task.id) == "In Progress"
    assert notes(manager, task.id) == [NOTE_LINKED]


def test_switching_tasks_records_on_both(session, manager):
    first, second = manager.create_task("A"), manager.create_task("B")
    session.link(first.id)
    session.link(second.id)
    assert notes(manager, first.id) == [NOTE_LINKED, NOTE_UNLINKED]
    assert notes(manager, second.id) == [NOTE_LINKED]


def test_linking_the_same_task_twice_does_nothing(session, manager):
    task = manager.create_task("Tarefa")
    session.link(task.id)
    session.link(task.id)
    assert notes(manager, task.id) == [NOTE_LINKED]


def test_unlink_keeps_the_status(session, manager):
    task = manager.create_task("Tarefa")
    session.link(task.id)
    session.unlink()
    assert session.linked_task_id is None
    assert status_of(manager, task.id) == "In Progress"


def test_link_reports_anytype_errors_but_still_links(session, manager, monkeypatch):
    task = manager.create_task("Tarefa")
    monkeypatch.setattr(manager, "set_status", lambda *a: (_ for _ in ()).throw(AnytypeError("fora do ar")))
    assert session.link(task.id) == ["fora do ar"]
    assert session.linked_task_id == task.id


def test_complete_marks_done_and_unlinks(session, manager):
    task = manager.create_task("Tarefa")
    session.link(task.id)
    session.complete(session.completion_note("terminei antes"))
    assert session.linked_task_id is None
    assert status_of(manager, task.id) == "Done"
    assert notes(manager, task.id)[-1] == "Tarefa concluída — terminei antes"
    assert NOTE_UNLINKED not in notes(manager, task.id)  # sem "desvinculada" redundante


def test_completion_note_mentions_the_running_focus_cycle(session):
    session.timer = FakeTimer(PomodoroStatus(Phase.WORK, 2, 4, 1500, 900, False, True))
    assert session.completion_note() == "Tarefa concluída durante o ciclo de foco 2 (10 min de foco nele)"
    session.timer = FakeTimer(PomodoroStatus(Phase.SHORT_BREAK, 2, 4, 300, 100, False, True))
    assert session.completion_note() == "Tarefa concluída"


def test_finish_focus_records_the_session_and_resumes(session, manager, config):
    config.pomodoro.work_minutes = 25
    task = manager.create_task("Tarefa")
    session.link(task.id)
    session.timer = FakeTimer()
    session.timer.paused = True
    session.finish_focus("rendeu bem", mark_done=False)
    assert notes(manager, task.id)[-1] == "Sessão de foco concluída (25 min) — rendeu bem"
    assert session.linked_task_id == task.id
    assert session.timer.paused is False


def test_finish_focus_can_complete_the_task(session, manager):
    task = manager.create_task("Tarefa")
    session.link(task.id)
    session.timer = FakeTimer()
    session.finish_focus(mark_done=True)
    assert status_of(manager, task.id) == "Done"
    assert session.linked_task_id is None


def test_finish_focus_resumes_even_if_anytype_fails(session, manager, monkeypatch):
    task = manager.create_task("Tarefa")
    session.link(task.id)
    session.timer = FakeTimer()
    session.timer.paused = True
    monkeypatch.setattr(manager, "add_note", lambda *a: (_ for _ in ()).throw(AnytypeError("fora do ar")))
    with pytest.raises(AnytypeError):
        session.finish_focus("x")
    assert session.timer.paused is False
    assert session.linked_task_id == task.id


def test_focus_end_pauses_and_asks_only_with_a_linked_task(session, manager):
    asked = []
    session.on_focus_end = asked.append
    session.timer = FakeTimer()

    session._handle_phase_end(Phase.WORK, 1)          # sem tarefa: não pergunta
    assert asked == [] and not session.timer.paused

    session.link(manager.create_task("Tarefa").id)
    session._handle_phase_end(Phase.SHORT_BREAK, 1)   # fim de pausa: não pergunta
    assert asked == []

    session._handle_phase_end(Phase.WORK, 3)
    assert asked == [3] and session.timer.paused


def test_countdown_sound_follows_the_sound_setting(session, config, monkeypatch):
    played = []
    monkeypatch.setattr("pomodoro_app.session.play_sound", played.append)
    tick = PomodoroStatus(Phase.WORK, 1, 4, 1500, 3, False, True)
    session._handle_tick(tick)
    assert played == []  # sons desligados
    config.pomodoro.sound_enabled = True
    session._handle_tick(tick)
    assert len(played) == 1
