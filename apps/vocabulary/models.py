from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class VocabularyPack(models.Model):
    """
    Ustoz tomonidan AI yordamida generatsiya qilingan lug'at to'plami va 4 xil mashqlar.
    """

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vocabulary_packs",
        verbose_name=_("o'qituvchi"),
        null=True,
        blank=True,
    )
    group = models.ForeignKey(
        "courses.StudentGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vocabulary_packs",
        verbose_name=_("biriktirilgan guruh"),
    )
    title = models.CharField(_("to'plam nomi"), max_length=250)
    subject = models.CharField(_("fan"), max_length=50, default="english")
    raw_words_text = models.TextField(
        _("kiritilgan so'zlar ro'yxati"),
        help_text=_("Ustoz kiritgan xom so'zlar matni."),
    )
    word_count = models.PositiveIntegerField(_("so'zlar soni"), default=0)
    exercises_data = models.JSONField(
        _("4 xil mashqlar JSON formati"),
        default=dict,
        blank=True,
        help_text=_(
            "format_1_quiz, format_2_spelling, format_3_eng_uzb, format_4_uzb_eng"
        ),
    )
    created_at = models.DateTimeField(_("yaratilgan"), auto_now_add=True)
    updated_at = models.DateTimeField(_("yangilangan"), auto_now=True)

    class Meta:
        verbose_name = _("Lug'at to'plami")
        verbose_name_plural = _("Lug'at to'plamlari")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.word_count} so'z)"


class StudentWordMistake(models.Model):
    """
    Ebbinghaus 'Unutish egri chizig'i' (Spaced Repetition) bo'yicha o'quvchi xatolari.
    Talaba adashgan so'zlar bot viktorinasi orqali takrorlanadi.
    Ketma-ket 3 marta to'g'ri topilsa 'is_mastered' (Yod olindi) holatiga o'tadi.
    """

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="word_mistakes",
        verbose_name=_("o'quvchi"),
    )
    word = models.CharField(_("inglizcha so'z"), max_length=120, db_index=True)
    definition = models.TextField(_("ta'rifi / ma'nosi"), blank=True)
    translation_uz = models.CharField(
        _("o'zbekcha tarjimasi"), max_length=255, blank=True
    )
    mistake_count = models.PositiveIntegerField(_("xatolar soni"), default=1)
    consecutive_correct_streak = models.PositiveIntegerField(
        _("ketma-ket to'g'ri topishlar soni"), default=0
    )
    is_mastered = models.BooleanField(_("yod olinganmi"), default=False, db_index=True)
    last_reviewed_at = models.DateTimeField(
        _("oxirgi takrorlangan vaqt"), null=True, blank=True
    )
    next_review_at = models.DateTimeField(
        _("keyingi takrorlash vaqti"), null=True, blank=True, db_index=True
    )
    created_at = models.DateTimeField(_("yaratilgan"), auto_now_add=True)
    updated_at = models.DateTimeField(_("yangilangan"), auto_now=True)

    class Meta:
        verbose_name = _("O'quvchi xato qilgan so'zi")
        verbose_name_plural = _("O'quvchi xato qilgan so'zlari")
        unique_together = ("student", "word")
        ordering = ["is_mastered", "-mistake_count", "next_review_at"]

    def __str__(self) -> str:
        status = (
            "Mastered"
            if self.is_mastered
            else f"Streak {self.consecutive_correct_streak}/3"
        )
        return f"{self.student.get_full_name()}: {self.word} ({status})"

    def record_attempt(self, is_correct: bool) -> bool:
        """
        Natijani qayd qilish va Ebbinghaus oraliq takrorlash vaqtini yangilash.
        Returns True if newly mastered.
        """
        now = timezone.now()
        self.last_reviewed_at = now
        newly_mastered = False

        if is_correct:
            self.consecutive_correct_streak += 1
            if self.consecutive_correct_streak >= 3:
                self.is_mastered = True
                newly_mastered = True
                self.next_review_at = None
            else:
                # 1-marta to'g'ri bo'lsa 1 kundan keyin, 2-marta bo'lsa 3 kundan keyin
                days_ahead = 1 if self.consecutive_correct_streak == 1 else 3
                self.next_review_at = now + timezone.timedelta(days=days_ahead)
        else:
            self.consecutive_correct_streak = 0
            self.mistake_count += 1
            self.is_mastered = False
            # Xato qilsa yana tezroq takrorlash (4 soat yoki ertasi kuni)
            self.next_review_at = now + timezone.timedelta(hours=4)

        self.save()
        return newly_mastered


class GrammarCategory(models.Model):
    """Structured English Grammar topic mapped to CEFR & Essay/Speaking error tags."""

    slug = models.SlugField(_("slug"), max_length=64, unique=True)
    title = models.CharField(_("mavzu nomi"), max_length=150)
    cefr_level = models.CharField(_("CEFR darajasi"), max_length=8, default="B1", db_index=True)
    description = models.TextField(_("qisqa izoh"), blank=True, default="")
    formula = models.CharField(_("qoida formulasi"), max_length=255, blank=True, default="")
    example_correct = models.CharField(_("to'g'ri misol"), max_length=300, blank=True, default="")
    example_incorrect = models.CharField(_("xato misol"), max_length=300, blank=True, default="")
    error_keywords = models.JSONField(_("bog'liq xato kalit so'zlari"), default=list, blank=True)
    sort_order = models.PositiveIntegerField(_("tartib"), default=0)

    class Meta:
        verbose_name = _("Grammatika mavzusi")
        verbose_name_plural = _("Grammatika mavzulari")
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return f"[{self.cefr_level}] {self.title}"


class GrammarExercise(models.Model):
    """Interactive practice question inside a GrammarCategory."""

    category = models.ForeignKey(
        GrammarCategory,
        on_delete=models.CASCADE,
        related_name="exercises",
        verbose_name=_("mavzu"),
    )
    prompt = models.TextField(_("savol matni"))
    options = models.JSONField(_("variantlar"), default=list)
    correct_answer = models.CharField(_("to'g'ri javob"), max_length=255)
    explanation = models.TextField(_("tushuntirish"), blank=True, default="")
    cefr_level = models.CharField(_("CEFR darajasi"), max_length=8, default="B1")
    sort_order = models.PositiveIntegerField(_("tartib"), default=0)

    class Meta:
        verbose_name = _("Grammatika mashqi")
        verbose_name_plural = _("Grammatika mashqlari")
        ordering = ["sort_order", "id"]


class GrammarAttempt(models.Model):
    """Student attempt on a GrammarExercise for mastery & mistake-link tracking."""

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="grammar_attempts",
        verbose_name=_("o'quvchi"),
    )
    category = models.ForeignKey(
        GrammarCategory,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    exercise = models.ForeignKey(
        GrammarExercise,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attempts",
    )
    selected_answer = models.CharField(_("tanlangan javob"), max_length=255, blank=True, default="")
    is_correct = models.BooleanField(_("to'g'rimi"), default=False, db_index=True)
    source_tag = models.CharField(_("manba"), max_length=40, default="grammar_studio")
    created_at = models.DateTimeField(_("vaqt"), auto_now_add=True)

    class Meta:
        verbose_name = _("Grammatika urinishi")
        verbose_name_plural = _("Grammatika urinishlari")
        ordering = ["-created_at"]

