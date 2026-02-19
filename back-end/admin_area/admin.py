from django.contrib import admin
from django.urls import path
from django.template.response import TemplateResponse
from django.shortcuts import redirect
from django import forms
from django.core.exceptions import ValidationError

import csv
import io

from faculty.models import Instructor
from core.models import User  # Assuming User model exists in core.models

from course.models import Course
from request.models import Request


# ---------------------------
# Helpers (important part)
# ---------------------------
def _open_csv_text_stream(uploaded_file):
    """
    Returns a text stream for csv.DictReader with robust encoding handling.
    Priority:
      1) utf-8-sig (handles BOM; best for Excel UTF-8)
      2) utf-8
      3) cp1256 / windows-1256 (common Persian CSV from Windows/Excel)
    """
    raw = uploaded_file.file  # binary file-like

    for enc in ("utf-8-sig", "utf-8", "cp1256", "windows-1256"):
        try:
            raw.seek(0)
            return io.TextIOWrapper(raw, encoding=enc, newline="")
        except Exception:
            continue

    # fallback
    raw.seek(0)
    return io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")


def _normalize_reader_headers(reader):
    # remove BOM and trim spaces
    if reader.fieldnames:
        reader.fieldnames = [h.strip().lstrip("\ufeff") for h in reader.fieldnames]


def _clean_row(row: dict):
    # trim keys + string values
    clean = {}
    for k, v in row.items():
        kk = k.strip().lstrip("\ufeff") if isinstance(k, str) else k
        vv = v.strip() if isinstance(v, str) else v
        clean[kk] = vv
    return clean


# ---------------------------
# Instructor bulk upload
# ---------------------------
class BulkInstructorUploadForm(forms.Form):
    csv_file = forms.FileField(label="CSV File", required=True)


def add_bulk_upload_functionality(admin_class):
    def get_urls(self):
        urls = super(admin_class, self).get_urls()
        custom_urls = [
            path(
                "bulk_upload/",
                self.admin_site.admin_view(self.bulk_upload),
                name="bulk_upload_instructors",
            ),
        ]
        return custom_urls + urls

    def bulk_upload(self, request):
        if request.method == "POST":
            form = BulkInstructorUploadForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = form.cleaned_data["csv_file"]

                text_stream = _open_csv_text_stream(csv_file)
                reader = csv.DictReader(text_stream)
                _normalize_reader_headers(reader)

                created_instructors = []

                for row in reader:
                    row = _clean_row(row)

                    try:
                        username = row.get("username", "")
                        if not username:
                            raise ValidationError("Missing username.")

                        user, user_created = User.objects.get_or_create(
                            username=username,
                            defaults={
                                "first_name": row.get("first_name", ""),
                                "last_name": row.get("last_name", ""),
                                "email": row.get("email", ""),
                                "role": User.INSTRUCTOR,  # Assuming role field exists
                            },
                        )

                        # if user already exists, make sure role is instructor
                        if not user_created and getattr(user, "role", None) != User.INSTRUCTOR:
                            raise ValidationError(
                                f"User {user.username} exists but is not an instructor."
                            )

                        # Set the password only if it is provided in the CSV
                        if row.get("password"):
                            user.set_password(row["password"])
                            user.save()

                        instructor, instructor_created = Instructor.objects.get_or_create(
                            user=user,
                            defaults={
                                "staff_id": row.get("staff_id", ""),
                                "way_of_communication": row.get("way_of_communication", ""),
                                "research_fields": row.get("research_fields", ""),
                            },
                        )

                        if instructor_created:
                            created_instructors.append(user.username)

                    except Exception as e:
                        self.message_user(
                            request,
                            f"Error processing row for {row.get('username', 'Unknown')}: {e}",
                            level="error",
                        )

                self.message_user(
                    request,
                    f"{len(created_instructors)} instructors created successfully.",
                    level="success",
                )
                return redirect("..")
        else:
            form = BulkInstructorUploadForm()

        context = self.admin_site.each_context(request)
        context["form"] = form
        context["opts"] = self.model._meta
        return TemplateResponse(request, "admin/bulk_upload_instructors.html", context)

    admin_class.get_urls = get_urls
    admin_class.bulk_upload = bulk_upload
    return admin_class


from faculty.admin import InstructorAdmin
InstructorAdmin = add_bulk_upload_functionality(InstructorAdmin)


# ---------------------------
# Course bulk upload
# ---------------------------
class BulkCourseUploadForm(forms.Form):
    csv_file = forms.FileField(label="CSV File", required=True)


def add_bulk_upload_functionality_to_course(admin_class):
    def get_urls(self):
        urls = super(admin_class, self).get_urls()
        custom_urls = [
            path(
                "bulk_upload/",
                self.admin_site.admin_view(self.bulk_upload),
                name="bulk_upload_courses",
            ),
        ]
        return custom_urls + urls

    def bulk_upload(self, request):
        if request.method == "POST":
            form = BulkCourseUploadForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = form.cleaned_data["csv_file"]

                text_stream = _open_csv_text_stream(csv_file)
                reader = csv.DictReader(text_stream)
                _normalize_reader_headers(reader)

                created_courses = []

                for row in reader:
                    row = _clean_row(row)

                    try:
                        # instructor (optional)
                        instructor = None
                        if row.get("instructor_username"):
                            instructor = Instructor.objects.get(
                                user__username=row["instructor_username"]
                            )

                        # head_TA (optional)
                        head_ta_request = None
                        if row.get("head_ta_request_id"):
                            head_ta_request = Request.objects.get(
                                id=row["head_ta_request_id"]
                            )

                        condition_val = None
                        if row.get("condition"):
                            condition_val = float(row["condition"])

                        course, course_created = Course.objects.get_or_create(
                            name=row.get("name", ""),
                            semester=row.get("semester", ""),
                            defaults={
                                "instructor": instructor,
                                "head_TA": head_ta_request,
                                "condition": condition_val,
                            },
                        )

                        if course_created:
                            created_courses.append(course.name)
                        else:
                            # update if provided
                            if instructor is not None:
                                course.instructor = instructor
                            if head_ta_request is not None:
                                course.head_TA = head_ta_request
                            if row.get("condition"):
                                course.condition = condition_val
                            course.save()

                    except Exception as e:
                        self.message_user(
                            request,
                            f"Error processing row for {row.get('name', 'Unknown')}: {e}",
                            level="error",
                        )

                self.message_user(
                    request,
                    f"{len(created_courses)} courses created/updated successfully.",
                    level="success",
                )
                return redirect("..")
        else:
            form = BulkCourseUploadForm()

        context = self.admin_site.each_context(request)
        context["form"] = form
        context["opts"] = self.model._meta
        return TemplateResponse(request, "admin/bulk_upload_courses.html", context)

    admin_class.get_urls = get_urls
    admin_class.bulk_upload = bulk_upload
    return admin_class


from course.admin import CourseAdmin
CourseAdmin = add_bulk_upload_functionality_to_course(CourseAdmin)
