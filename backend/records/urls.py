from django.urls import path

from . import views

urlpatterns = [
    path('students/', views.StudentListCreateView.as_view()),
    path('students/stats/', views.StudentStatsView.as_view()),
    path('students/import/', views.StudentImportView.as_view()),
    path('students/<str:pk>/transfer/', views.StudentTransferView.as_view()),
    path('students/<str:pk>/', views.StudentDetailView.as_view()),
    path('staff/', views.StaffListView.as_view()),
    path('staff/<str:pk>/invite/', views.StaffInviteView.as_view()),
    path('staff/<str:pk>/', views.StaffDetailView.as_view()),
    path('invoices/generate/', views.InvoiceGenerateView.as_view()),
    path('invoices/', views.InvoiceListView.as_view()),
    path('fees/structure/', views.FeeStructureView.as_view()),
    path('payments/<str:pk>/verify/', views.PaymentVerifyView.as_view()),
    path('payments/<str:pk>/reverse/', views.PaymentReverseView.as_view()),
    path('payments/<str:pk>/cancel/', views.PaymentCancelView.as_view()),
    path('payments/', views.PaymentListView.as_view()),
    path('subscription/', views.SubscriptionView.as_view()),
    path('results/', views.ResultSheetListView.as_view()),
    path('attendance/roster/', views.AttendanceRosterView.as_view()),
    path('attendance/', views.AttendanceSubmitView.as_view()),
    path('academics/', views.AcademicsView.as_view()),
    path('academics/subjects/<str:name>/', views.AcademicSubjectDetailView.as_view()),
    path('academics/subjects/', views.AcademicSubjectsView.as_view()),
    path('academics/classes/<str:name>/', views.AcademicClassDetailView.as_view()),
    path('academics/classes/', views.AcademicClassesView.as_view()),
    path('timetable/', views.TimetableView.as_view()),
]