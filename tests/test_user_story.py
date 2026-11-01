from pomodoro_app import user_story


def test_template_has_placeholders_until_filled():
    assert user_story.has_placeholders(user_story.TEMPLATE)
    filled = "Como estudante, quero revisar a aula para fixar o conteúdo."
    assert not user_story.has_placeholders(filled)
    assert not user_story.has_placeholders("")


def test_build_story_with_criteria():
    story = user_story.build_story("estudante", "revisar a aula 12", "fixar o conteúdo", ["Resumo escrito", " ", "Exercícios feitos"])
    assert story == (
        "Como estudante, quero revisar a aula 12 para fixar o conteúdo.\n\n"
        "Critérios de aceitação:\n- Resumo escrito\n- Exercícios feitos"
    )


def test_build_story_without_benefit_or_criteria():
    assert user_story.build_story(" estudante ", " revisar ") == "Como estudante, quero revisar."
