from django.db import models

from schools.models import School


class Student(models.Model):
    class Gender(models.TextChoices):
        MALE = 'male', 'Male'
        FEMALE = 'female', 'Female'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        SUSPENDED = 'suspended', 'Suspended'
        GRADUATED = 'graduated', 'Graduated'
        WITHDRAWN = 'withdrawn', 'Withdrawn'
        TRANSFERRED = 'transferred', 'Transferred'

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='students')
    admission_number = models.CharField(max_length=30)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    gender = models.CharField(max_length=10, choices=Gender.choices)
    date_of_birth = models.DateField(null=True, blank=True)
    class_name = models.CharField(max_length=50)
    arm = models.CharField(max_length=5, blank=True, default='')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    guardian_name = models.CharField(max_length=200, blank=True, default='')
    guardian_phone = models.CharField(max_length=20, blank=True, default='')
    photo = models.ImageField(upload_to='students/photos/', null=True, blank=True)
    transferred_to = models.ForeignKey(
        School, on_delete=models.SET_NULL, null=True, blank=True, related_name='incoming_transfers'
    )
    transferred_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['last_name', 'first_name']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'admission_number'], name='unique_admission_per_school'
            )
        ]

    def __str__(self):
        return f'{self.last_name}, {self.first_name} ({self.admission_number})'


class StaffMember(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INVITED = 'invited', 'Invited'
        SUSPENDED = 'suspended', 'Suspended'

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='staff')
    full_name = models.CharField(max_length=200)
    email = models.EmailField(blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    role = models.CharField(max_length=20, default='teacher')
    subjects = models.JSONField(default=list, blank=True)
    classes = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['full_name']

    def __str__(self):
        return self.full_name


class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        PRESENT = 'present', 'Present'
        ABSENT = 'absent', 'Absent'
        LATE = 'late', 'Late'
        EXCUSED = 'excused', 'Excused'

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='attendance_records')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance')
    class_name = models.CharField(max_length=50)
    subject = models.CharField(max_length=100, blank=True, default='')
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices)
    submitted_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'date', 'subject'], name='unique_attendance_per_student_day'
            )
        ]

    def __str__(self):
        return f'{self.student_id} {self.date} {self.status}'


class Invoice(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='invoices')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='invoices')
    term = models.CharField(max_length=50)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    items = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.student_id} {self.term} {self.total}'

    @property
    def status(self):
        if self.paid >= self.total:
            return 'paid'
        if self.paid > 0:
            return 'part_paid'
        return 'unpaid'


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = 'cash', 'Cash'
        BANK_TRANSFER = 'bank_transfer', 'Bank Transfer'
        CARD = 'card', 'Card'
        POS = 'pos', 'POS'
        USSD = 'ussd', 'USSD'
        ONLINE = 'online', 'Online'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        VERIFIED = 'verified', 'Verified'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'
        REVERSED = 'reversed', 'Reversed'
        CANCELLED = 'cancelled', 'Cancelled'

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='payments')
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=Method.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    reference = models.CharField(max_length=64, unique=True)
    note = models.TextField(blank=True, default='')
    recorded_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference} {self.amount} {self.status}'