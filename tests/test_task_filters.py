import datetime as dt

from pomodoro_app import task_filters as tf
from pomodoro_app.task_manager import Task


def task(name, status="To Do", created=None, due=None):
    return Task(id=name, name=name, status=status, raw={}, created=created, due=due)


def names(tasks):
    return [t.name for t in tasks]


TASKS = [
    task("Estudar Linguística", "In Progress", dt.datetime(2026, 8, 30), dt.date(2026, 11, 20)),
    task("estudar linguistica 2", "Done", dt.datetime(2026, 8, 31)),
    task("Arrumar a casa", "To Do", dt.datetime(2026, 6, 1), dt.date(2026, 11, 2)),
    task("Sem data", "To Do"),
]


def test_normalize_ignores_case_and_accents():
    assert tf.normalize("Linguística ÁÉ") == tf.normalize("linguistica ae")


def test_search_ignores_case_and_accents():
    assert names(tf.filter_tasks(TASKS, query="LINGUISTICA", sort="name_asc")) == [
        "Estudar Linguística", "estudar linguistica 2",
    ]


def test_status_filters():
    assert names(tf.filter_tasks(TASKS, status_filter=tf.STATUS_PENDING, sort="name_asc")) == [
        "Arrumar a casa", "Estudar Linguística", "Sem data",
    ]
    assert names(tf.filter_tasks(TASKS, status_filter="Done")) == ["estudar linguistica 2"]
    assert len(tf.filter_tasks(TASKS, status_filter=tf.STATUS_ALL)) == len(TASKS)


def test_sort_by_creation_keeps_undated_last():
    assert names(tf.sort_tasks(TASKS, "created_desc")) == [
        "estudar linguistica 2", "Estudar Linguística", "Arrumar a casa", "Sem data",
    ]
    assert names(tf.sort_tasks(TASKS, "created_asc"))[-1] == "Sem data"


def test_sort_by_due_date_keeps_tasks_without_due_last():
    assert names(tf.sort_tasks(TASKS, "due_asc"))[:2] == ["Arrumar a casa", "Estudar Linguística"]


def test_sort_by_title_ignores_case_and_accents():
    assert names(tf.sort_tasks(TASKS, "name_desc"))[0] == "Sem data"


def test_sort_does_not_change_the_original_list():
    original = list(TASKS)
    tf.sort_tasks(TASKS, "name_asc")
    assert TASKS == original


def test_limit():
    assert len(tf.limit_tasks(TASKS, 2)) == 2
    assert len(tf.limit_tasks(TASKS, 0)) == len(TASKS)  # 0 = todas


def test_every_sort_option_is_handled():
    for key in tf.SORT_KEYS:
        assert len(tf.sort_tasks(TASKS, key)) == len(TASKS)
