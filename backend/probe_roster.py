from django.db.models import Count

from records.models import Enrollment, Registration, Student

print('enrollments total:', Enrollment.objects.count())
print('enrolled student ids:', Enrollment.objects.values('student_id').distinct().count())
print('students total:', Student.objects.count())
print('students without any enrollment:', Student.objects.filter(enrollments__isnull=True).count())
print('registrations by status:', list(Registration.objects.values('status').annotate(c=Count('id'))))
print('students by status:', list(Student.objects.values('status').annotate(c=Count('id'))))
