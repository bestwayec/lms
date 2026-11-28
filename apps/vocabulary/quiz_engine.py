"""Answer-safe Vocabulary Exam 3.0 quiz engine & seeded English Grammar curriculum."""

from __future__ import annotations

import hashlib
import random
import re
from typing import Any

from apps.vocabulary.models import GrammarAttempt, GrammarCategory, GrammarExercise

VOCAB_QUIZ_TYPES = ("listen_choose", "listen_type", "fill_blank", "context_meaning", "synonym")


def _canon(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _question_token(user_id: int, word: str, q_type: str) -> str:
    raw = f"{user_id}:{_canon(word)}:{q_type}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_answer_safe_vocab_questions(
    entries: list[dict[str, Any]],
    *,
    user_id: int,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """
    Build answer-safe questions (`listen_choose`, `listen_type`, `fill_blank`, `context_meaning`, `synonym`).
    Never leaks `correct_answer` or the target word in listening/fill prompts.
    """
    rng = random.Random(seed)
    meaning_pool = [str(e.get("meaning") or "").strip() for e in entries if str(e.get("meaning") or "").strip()]
    word_pool = [str(e.get("word") or "").strip() for e in entries if str(e.get("word") or "").strip()]

    questions: list[dict[str, Any]] = []
    for idx, entry in enumerate(entries):
        word = str(entry.get("word") or "").strip()
        meaning = str(entry.get("meaning") or "").strip()
        sentence = str(entry.get("context_sentence") or "").strip()
        synonyms = [str(s).strip() for s in (entry.get("synonyms") or []) if str(s).strip()]
        if not word or not meaning:
            continue

        # Choose richest eligible question type deterministically
        eligible: list[str] = []
        if synonyms:
            eligible.append("synonym")
        if sentence and re.search(rf"(?<![\w']){re.escape(word)}(?![\w'])", sentence, re.IGNORECASE):
            eligible.extend(["context_meaning", "fill_blank"])
        eligible.extend(["listen_choose", "listen_type"])

        q_type = eligible[idx % len(eligible)]
        q: dict[str, Any] = {
            "id": entry.get("id") or (idx + 1),
            "token": _question_token(user_id, word, q_type),
            "type": q_type,
            "audio_url": entry.get("audio_url") or None,
            "pronunciation_text": word if q_type in ("listen_choose", "listen_type") else None,
            "prompt": "",
            "context_sentence": None,
            "options": [],
            "streak": int(entry.get("streak") or 0),
        }

        if q_type == "listen_choose":
            distractors = [m for m in meaning_pool if _canon(m) != _canon(meaning)]
            sample = rng.sample(distractors, min(3, len(distractors)))
            opts = list(dict.fromkeys([meaning, *sample]))
            rng.shuffle(opts)
            q["options"] = opts
        elif q_type == "listen_type":
            q["hint_length"] = len(word)
        elif q_type == "fill_blank":
            blanked = re.sub(rf"(?<![\w']){re.escape(word)}(?![\w'])", "_____", sentence, count=1, flags=re.IGNORECASE)
            q["prompt"] = blanked
            q["first_letter"] = word[:1].upper()
        elif q_type == "context_meaning":
            distractors = [m for m in meaning_pool if _canon(m) != _canon(meaning)]
            sample = rng.sample(distractors, min(3, len(distractors)))
            opts = list(dict.fromkeys([meaning, *sample]))
            rng.shuffle(opts)
            q["prompt"] = word
            q["context_sentence"] = sentence
            q["options"] = opts
        elif q_type == "synonym":
            correct_syn = synonyms[0]
            distractors = [w for w in word_pool if _canon(w) != _canon(word) and _canon(w) not in {_canon(s) for s in synonyms}]
            sample = rng.sample(distractors, min(3, len(distractors)))
            opts = list(dict.fromkeys([correct_syn, *sample]))
            rng.shuffle(opts)
            q["prompt"] = word
            q["options"] = opts

        questions.append(q)

    return questions


CORE_GRAMMAR_CURRICULUM: tuple[dict[str, Any], ...] = (
    {
        "slug": "tenses",
        "title": "Verb Tenses & Aspect",
        "cefr_level": "B1",
        "description": "Choosing Present Perfect, Past Simple, and Continuous aspects accurately in essays and stories.",
        "formula": "S + have/has + V3 (unfinished time) vs S + V2 (finished past time)",
        "example_correct": "Public transit ridership has grown steadily since 2020.",
        "example_incorrect": "Public transit ridership grew steadily since 2020.",
        "error_keywords": ["tense", "past", "present perfect", "since", "zamon"],
        "exercises": [
            ("Electric bus adoption ____ significantly since the city cut fares in 2022.", ["has increased", "increased", "is increase", "increases"], "has increased", "'since 2022' connects past action to present, requiring Present Perfect."),
            ("By the time the train arrived, most commuters ____ another route.", ["had chosen", "have chosen", "choose", "choosing"], "had chosen", "Past action completed before another past point uses Past Perfect."),
        ],
    },
    {
        "slug": "conditionals",
        "title": "Conditionals (Zero–Third & Mixed)",
        "cefr_level": "B2",
        "description": "Expressing real consequences and hypothetical scenarios clearly for IELTS Task 2 arguments.",
        "formula": "If + Past Simple, would + V1 (2nd) | If + had + V3, would have + V3 (3rd)",
        "example_correct": "If governments subsidized solar batteries, rural clinics would remain powered.",
        "example_incorrect": "If governments would subsidize solar batteries, clinics remain powered.",
        "error_keywords": ["conditional", "if", "would", "shart gap"],
        "exercises": [
            ("If municipalities invested in bike lanes, traffic congestion ____ noticeably.", ["would fall", "will fell", "falls would", "had fallen"], "would fall", "Second conditional pairs Past Simple in the if-clause with 'would + base verb'."),
            ("Had the policy been enforced earlier, emissions ____ much lower last winter.", ["would have been", "will be", "are", "would be been"], "would have been", "Inverted third conditional refers to a hypothetical past outcome."),
        ],
    },
    {
        "slug": "passive_voice",
        "title": "Passive Voice & Academic Objectivity",
        "cefr_level": "B2",
        "description": "Essential for IELTS Writing Task 1 process diagrams and formal reports.",
        "formula": "Subject + be (tense) + Past Participle (V3)",
        "example_correct": "Collected plastic bottles are washed and shredded into flakes.",
        "example_incorrect": "Collected plastic bottles wash and shred into flakes.",
        "error_keywords": ["passive", "majhul", "by", "participle"],
        "exercises": [
            ("Once the cocoa beans dry, they ____ to the roasting facility.", ["are transported", "transport", "have transport", "transporting"], "are transported", "Task 1 processes use Present Simple Passive for steps acted on materials."),
            ("A new bridge ____ next spring to connect the industrial district.", ["will be built", "will build", "is build", "built"], "will be built", "Future passive requires 'will be + V3'."),
        ],
    },
    {
        "slug": "relative_clauses",
        "title": "Defining & Non-Defining Relative Clauses",
        "cefr_level": "B2",
        "description": "Joining ideas concisely with who, which, that, whose, and where.",
        "formula": "Noun, + which/who + V... (non-defining) | Noun + that/which + V... (defining)",
        "example_correct": "Solar microgrids, which lower transmission losses, benefit remote villages.",
        "example_incorrect": "Solar microgrids, that lower transmission losses, benefit villages.",
        "error_keywords": ["relative", "which", "that", "who", "whose"],
        "exercises": [
            ("The library, ____ was renovated last autumn, now opens at 7 a.m.", ["which", "that", "what", "who"], "which", "Non-defining relative clauses after a comma use 'which' (never 'that')."),
            ("Students ____ practice aloud twice a week gain confidence faster.", ["who", "which", "whom are", "whose speak"], "who", "Subject relative pronoun for people is 'who'."),
        ],
    },
    {
        "slug": "modals",
        "title": "Modal Verbs & Hedging in Academic Writing",
        "cefr_level": "B1",
        "description": "Softening claims and expressing obligation or probability accurately.",
        "formula": "Subject + may / might / could / must / should + V1",
        "example_correct": "Carbon taxes may encourage factories to adopt cleaner equipment.",
        "example_incorrect": "Carbon taxes may to encourage factories adopt cleaner equipment.",
        "error_keywords": ["modal", "may", "might", "should", "must", "can"],
        "exercises": [
            ("Excessive screen time ____ disrupt sleep quality among teenagers.", ["can", "can to", "musts", "could be disrupt"], "can", "Modals are always followed by a bare infinitive without 'to'."),
            ("Candidates ____ arrive at least thirty minutes before the listening paper starts.", ["must", "must to", "should to", "mighting"], "must", "'must + V1' expresses formal exam requirement."),
        ],
    },
    {
        "slug": "articles_determiners",
        "title": "Articles (a / an / the / zero) & Determiners",
        "cefr_level": "B1",
        "description": "Distinguishing specific, general plural, and uncountable nouns.",
        "formula": "the + specific/unique | a/an + singular countable | zero + plural/uncountable general",
        "example_correct": "Access to clean water is a fundamental priority in developing regions.",
        "example_incorrect": "The access to a clean water is fundamental priority.",
        "error_keywords": ["article", "determiner", "the", "an", "a/an", "artikl"],
        "exercises": [
            ("____ rapid urbanization has created housing shortages in major capitals.", ["Rapid (no article)", "A rapid", "An rapid", "The rapidly"], "Rapid (no article)", "General uncountable nouns modified by adjectives take zero article."),
            ("____ Sahara is the largest hot desert in the world.", ["The", "A", "An", "Zero article"], "The", "Deserts, oceans, and superlative geographical names take 'the'."),
        ],
    },
    {
        "slug": "prepositions",
        "title": "Academic Collocations & Prepositions",
        "cefr_level": "B1",
        "description": "Mastering depend on, contribute to, rise by/to, and time prepositions.",
        "formula": "Verb/Noun + exact dependent preposition (depend on, result in, focus on)",
        "example_correct": "Economic growth depends on sustained investment in vocational training.",
        "example_incorrect": "Economic growth depends from sustained investment in training.",
        "error_keywords": ["preposition", "predlog", "depend", "in", "on", "to"],
        "exercises": [
            ("The share of renewable power rose ____ 18% between 2015 and 2023.", ["by", "on", "at", "with"], "by", "Use 'rise by + amount' for magnitude of change and 'to' for end value."),
            ("Community gardens contribute ____ stronger neighborhood cohesion.", ["to", "for", "at", "with"], "to", "'contribute to + noun phrase' is standard academic collocation."),
        ],
    },
    {
        "slug": "reported_speech",
        "title": "Reported Speech & Indirect Questions",
        "cefr_level": "B2",
        "description": "Summarizing interviews, research findings, and formal email requests.",
        "formula": "Ask/Wonder + wh-word + Subject + Verb (statement word order)",
        "example_correct": "Could you let me know when the workshop begins?",
        "example_incorrect": "Could you let me know when does the workshop begin?",
        "error_keywords": ["reported", "indirect", "question", "backshift"],
        "exercises": [
            ("I would appreciate it if you could confirm where the session ____.", ["will be held", "will held", "is it held", "did hold"], "will be held", "Indirect embedded clauses keep normal subject-before-verb order."),
            ("The coordinator announced that registration ____ the following Monday.", ["would open", "will opens", "open", "was open to"], "would open", "Past reporting verb shifts 'will' back to 'would'."),
        ],
    },
    {
        "slug": "gerunds_infinitives",
        "title": "Gerunds, Infinitives & Verb Patterns",
        "cefr_level": "B2",
        "description": "Using -ing subjects and verb + gerund / verb + to-infinitive accurately.",
        "formula": "V-ing (subject / enjoy, avoid, suggest) vs to + V1 (decide, afford, enable O to V1)",
        "example_correct": "Investing early in teacher training avoids costly curriculum failures.",
        "example_incorrect": "Invest early in teacher training avoids costly curriculum failures.",
        "error_keywords": ["gerund", "infinitive", "-ing", "to +", "pattern"],
        "exercises": [
            ("The commission recommended ____ public transit corridors before adding tolls.", ["expanding", "to expand", "expand", "expanded"], "expanding", "'recommend' takes a gerund (-ing) or a 'that' clause."),
            ("Scholarships enable low-income students ____ university full-time.", ["to attend", "attending", "attend", "attended"], "to attend", "The pattern is 'enable someone to do something'."),
        ],
    },
    {
        "slug": "complex_sentences",
        "title": "Concession, Inversion & Complex Clause Linking",
        "cefr_level": "C1",
        "description": "High-band Grammatical Range with Although vs Despite, Not only... but also, and clauses.",
        "formula": "Although + S + V | Despite + Noun/V-ing | Not only + Aux + S + V",
        "example_correct": "Although remote work saves commuting time, it can weaken team mentoring.",
        "example_incorrect": "Although remote work saves commuting time, but it can weaken mentoring.",
        "error_keywords": ["although", "despite", "inversion", "complex", "comma splice", "however"],
        "exercises": [
            ("____ the higher initial cost, geothermal heating pays for itself within six years.", ["Despite", "Although", "Even", "Whereas"], "Despite", "'Despite' is followed by a noun phrase; 'Although' requires a full clause."),
            ("Not only ____ noise pollution, electric trains also lower maintenance budgets.", ["do they cut", "they cut", "cutting", "cut they"], "do they cut", "Negative adverbial 'Not only' at clause start triggers auxiliary inversion."),
        ],
    },
)


def seed_grammar_curriculum() -> list[GrammarCategory]:
    """Ensure the 10 canonical English grammar categories and exercises exist in DB."""
    categories: list[GrammarCategory] = []
    for idx, item in enumerate(CORE_GRAMMAR_CURRICULUM, start=1):
        cat, _ = GrammarCategory.objects.update_or_create(
            slug=item["slug"],
            defaults={
                "title": item["title"],
                "cefr_level": item["cefr_level"],
                "description": item["description"],
                "formula": item["formula"],
                "example_correct": item["example_correct"],
                "example_incorrect": item["example_incorrect"],
                "error_keywords": list(item["error_keywords"]),
                "sort_order": idx,
            },
        )
        if not cat.exercises.exists():
            for e_idx, (prompt, opts, correct, explanation) in enumerate(item["exercises"], start=1):
                GrammarExercise.objects.create(
                    category=cat,
                    prompt=prompt,
                    options=list(opts),
                    correct_answer=correct,
                    explanation=explanation,
                    cefr_level=item["cefr_level"],
                    sort_order=e_idx,
                )
        categories.append(cat)
    return categories


def recommend_grammar_for_student(user) -> list[dict[str, Any]]:
    """Recommend grammar topics linked to the student's recent Essay & Speaking errors."""
    from apps.essays.models import EssaySubmission
    from apps.speaking.models import SpeakingSubmission

    corpus_parts: list[str] = []
    for sub in EssaySubmission.objects.filter(student=user).order_by("-updated_at")[:5]:
        raw = sub.raw_result if isinstance(sub.raw_result, dict) else {}
        corpus_parts.append(str(sub.summary or ""))
        for crit in raw.get("criteria") or []:
            if isinstance(crit, dict):
                corpus_parts.append(" ".join(str(x) for x in (crit.get("errors") or [])))
                corpus_parts.append(str(crit.get("reason") or ""))

    for spk in SpeakingSubmission.objects.filter(user=user).order_by("-created_at")[:5]:
        fb = spk.feedback if isinstance(spk.feedback, dict) else {}
        corpus_parts.append(str(fb.get("grammar_feedback") or ""))
        for gc in fb.get("grammar_corrections") or []:
            if isinstance(gc, dict):
                corpus_parts.append(f"{gc.get('rule', '')} {gc.get('incorrect', '')}")

    corpus = " ".join(corpus_parts).lower()
    categories = list(GrammarCategory.objects.all().order_by("sort_order", "id"))
    recommendations: list[dict[str, Any]] = []
    for cat in categories:
        matched = [kw for kw in (cat.error_keywords or []) if str(kw).lower() in corpus]
        total_att = GrammarAttempt.objects.filter(student=user, category=cat).count()
        correct_att = GrammarAttempt.objects.filter(student=user, category=cat, is_correct=True).count()
        if matched or (total_att > 0 and correct_att < total_att):
            recommendations.append(
                {
                    "slug": cat.slug,
                    "title": cat.title,
                    "cefr_level": cat.cefr_level,
                    "matched_keywords": matched[:3],
                    "reason": "Essay/Speaking xatolari asosida tavsiya" if matched else "Mashqlarni mustahkamlash tavsiya etiladi",
                }
            )
    return recommendations[:4]
