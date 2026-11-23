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
]
