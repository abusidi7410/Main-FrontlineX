"""Create ACTIVE enrollments for students that have none.

Students imported from CSV (or created before enrollment existed) carry their
placement only in the denormalised `Student.class_name`/`Student.arm` mirror.
Every roster — attendance, results, class lists — reads ACTIVE enrollments,
so those students are invisible without this backfill.

Safe to re-run: a student with an existing ACTIVE enrollment in the school's
current session is skipped, and unresolvable class names are reported instead
of guessed.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from records.models import Enrollment, Section, Student
from records.services import academic as academic_service
from records.services import enrollment as enrollment_service
from schools.models import School


class Command(BaseCommand):
    help = 'Backfill ACTIVE enrollments from Student.class_name/arm mirrors.'

    def add_arguments(self, parser):
        parser.add_argument('--school', type=int, help='Only this school id')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        schools = School.objects.all()
        if options.get('school'):
            schools = schools.filter(id=options['school'])
        created = skipped = unmatched = 0
        for school in schools:
            session = academic_service.current_session(school)
            if session is None:
                self.stdout.write(self.style.WARNING(f'school {school.id}: no current session, skipped'))
                continue
            class_map = {c.name: c for c in school.school_classes.all()}
            section_map = {(s.class_obj_id, s.name): s for s in Section.objects.filter(school=school)}
            candidates = (
                Student.objects.filter(school=school, status=Student.Status.ACTIVE)
                .exclude(enrollments__status=Enrollment.Status.ACTIVE, enrollments__academic_session=session)
                .distinct()
            )
            for student in candidates:
                school_class = class_map.get((student.class_name or '').strip())
                if school_class is None:
                    # The student's mirrored class name was never provisioned as
                    # a SchoolClass row. Create it (with a best-effort level)
                    # so the placement can exist at all — an unmatched name
                    # would otherwise leave the student roster-less forever.
                    name = (student.class_name or '').strip()
                    if not name:
                        unmatched += 1
                        continue
                    from records.models import Level, SchoolClass

                    level_code = academic_service.guess_level_code(name)
                    level = None
                    if level_code:
                        level = school.levels.filter(code=level_code).first()
                    if level is None:
                        level = school.levels.order_by('sort_order').first()
                    if level is None:
                        unmatched += 1
                        continue
                    if not options['dry_run']:
                        school_class, _ = SchoolClass.objects.get_or_create(
                            school=school, name=name, defaults={'level': level},
                        )
                        class_map[name] = school_class
                        # Sections belong to the class being newly created, so
                        # the mirror rebuild needs the fresh map too.
                        section_map.update({
                            (s.class_obj_id, s.name): s
                            for s in Section.objects.filter(school=school, class_obj=school_class)
                        })
                    else:
                        created += 1
                        continue
                section = section_map.get((school_class.id, (student.arm or '').strip())) if student.arm else None
                if options['dry_run']:
                    created += 1
                    continue
                with transaction.atomic():
                    enrollment_service.activate_enrollment(
                        student=student, academic_session=session,
                        class_obj=school_class, section=section,
                        source=Enrollment.ActivationSource.MIGRATION,
                    )
                created += 1
        self.stdout.write(self.style.SUCCESS(
            f'created={created} skipped={skipped} unmatched_class={unmatched}',
        ))
