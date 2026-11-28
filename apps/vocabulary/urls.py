from django.urls import path
from .views import (
    generate_vocabulary_view,
    vocabulary_packs_list_view,
    assign_vocabulary_homework_view,
    spaced_repetition_quiz_view,
    spaced_repetition_submit_view,
    student_vocab_deck_view,
    student_vocab_quiz_view,
    student_vocab_submit_view,
    grammar_topics_view,
    grammar_topic_detail_view,
    grammar_attempt_submit_view,
)

app_name = "vocabulary"

urlpatterns = [
    path("generate/", generate_vocabulary_view, name="generate"),
    path("packs/", vocabulary_packs_list_view, name="packs_list"),
    path("assign-homework/", assign_vocabulary_homework_view, name="assign_homework"),
    path("spaced-repetition/quiz/", spaced_repetition_quiz_view, name="spaced_quiz"),
    path(
        "spaced-repetition/submit/", spaced_repetition_submit_view, name="spaced_submit"
    ),
    path("deck/", student_vocab_deck_view, name="student_deck"),
    path("student-quiz/", student_vocab_quiz_view, name="student_quiz"),
    path("student-quiz/submit/", student_vocab_submit_view, name="student_quiz_submit"),
    path("grammar/topics/", grammar_topics_view, name="grammar_topics"),
    path("grammar/topics/<slug:slug>/", grammar_topic_detail_view, name="grammar_topic_detail"),
    path("grammar/submit/", grammar_attempt_submit_view, name="grammar_submit"),
]
