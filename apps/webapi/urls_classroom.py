from django.urls import path
from . import views_classroom

app_name = "classroom"

urlpatterns = [
    # -- Teacher Classroom 6.0 ------------------------------------
    path("teacher/overview/", views_classroom.teacher_classroom_overview_view, name="teacher-overview"),
    path("teacher/groups/<int:group_id>/", views_classroom.teacher_group_detail_view, name="teacher-group-detail"),
    path("teacher/invitations/create/", views_classroom.teacher_create_invitation_view, name="teacher-invitation-create"),
    path("teacher/invitations/<int:inv_id>/revoke/", views_classroom.teacher_revoke_invitation_view, name="teacher-invitation-revoke"),
    path("teacher/invitations/<int:inv_id>/rotate/", views_classroom.teacher_rotate_invitation_view, name="teacher-invitation-rotate"),
    path("teacher/join-requests/", views_classroom.teacher_join_requests_view, name="teacher-join-requests"),
    path("teacher/join-requests/<int:req_id>/review/", views_classroom.teacher_review_join_request_view, name="teacher-join-request-review"),
    path("teacher/assign-test/", views_classroom.teacher_assign_test_wizard_view, name="teacher-assign-test"),

    # -- Student Classroom & Enrollment ---------------------------
    path("student/join/", views_classroom.student_join_group_view, name="student-join"),
    path("student/my-groups/", views_classroom.student_my_groups_view, name="student-my-groups"),

    # -- Access Resolution Preflight ------------------------------
    path("tests/<int:test_id>/access/", views_classroom.test_access_check_view, name="test-access-preflight"),

    # -- Group Lifecycle & Management (GRANDEC NEXT 8.0) ----------
    path("teacher/groups/<int:group_id>/dependencies/", views_classroom.teacher_group_dependencies_view, name="teacher-group-dependencies"),
    path("teacher/groups/<int:group_id>/archive/", views_classroom.teacher_archive_group_view, name="teacher-group-archive"),
    path("teacher/groups/<int:group_id>/restore/", views_classroom.teacher_restore_group_view, name="teacher-group-restore"),
    path("teacher/groups/<int:group_id>/delete/", views_classroom.teacher_delete_group_view, name="teacher-group-delete"),
    path("teacher/groups/<int:group_id>/transfer/", views_classroom.teacher_transfer_group_view, name="teacher-group-transfer"),
    path("teacher/groups/<int:group_id>/remove-student/", views_classroom.teacher_remove_student_view, name="teacher-group-remove-student"),

    # -- Leaderboards: Group vs Platform --------------------------
    path("groups/<int:group_id>/leaderboard/", views_classroom.classroom_group_leaderboard_view, name="group-leaderboard"),
    path("leaderboard/platform/", views_classroom.platform_leaderboard_view, name="platform-leaderboard"),
    path("profile/gamification-settings/", views_classroom.gamification_privacy_settings_view, name="gamification-settings"),

    # -- Essay Classroom & Review Center 8.0 -----------------------
    path("essays/<int:submission_id>/appeal/", views_classroom.student_request_essay_appeal_view, name="student-essay-appeal"),
    path("essays/<int:submission_id>/withdraw-appeal/", views_classroom.student_withdraw_essay_appeal_view, name="student-essay-withdraw-appeal"),
    path("teacher/essays/reviews/", views_classroom.teacher_list_essay_reviews_view, name="teacher-essay-reviews"),
    path("teacher/essays/<int:submission_id>/review/", views_classroom.teacher_submit_essay_review_view, name="teacher-essay-submit-review"),
    path("essays/<int:submission_id>/voice/", views_classroom.essay_voice_playback_view, name="essay-voice-playback"),
    path("groups/<int:group_id>/essays/<int:assignment_id>/gradebook/", views_classroom.classroom_group_essay_gradebook_view, name="group-essay-gradebook"),
]
