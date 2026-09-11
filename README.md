# School OS

You are a senior product designer, UX architect, frontend engineer, SaaS architect, and accessibility specialist.

You are building the production frontend for:

FRONTLINE NEXUS

Tagline:

"We Develop. We Secure. We Connect."

Frontline Nexus is a modern, secure, AI-powered School Management System designed specifically for primary and secondary schools in Nigeria and the wider West African market.

IMPORTANT:

This is NOT a demo.

This is NOT a static UI prototype.

This is NOT a collection of disconnected pages.

Build a complete, production-quality frontend architecture with real navigation, real state management, realistic data flows, validation, loading states, empty states, error states, responsive layouts, role-based interfaces, and reusable components.

The backend will be developed separately using OpenCode/Django REST API and PostgreSQL.

Design the frontend so it can connect cleanly to a REST API later.

DO NOT create fake functionality and label it as complete.

Where backend endpoints are not yet available, create clean service/API abstraction layers and realistic mock data only for development, while keeping the architecture ready for immediate API integration.

==================================================

1. CORE PRODUCT VISION

==================================================

Frontline Nexus should feel like the operating system for a school.

The software should help schools:

- Manage students

- Manage teachers and staff

- Manage parents/guardians

- Manage classes

- Manage subjects

- Manage academic sessions and terms

- Take attendance

- Manage results and assessments

- Generate report cards

- Manage school fees

- Record cash payments

- Record bank transfers

- Process online payments

- Manage invoices

- Manage timetables

- Create lesson plans

- Communicate with parents

- Manage school announcements

- Automatically prepare student promotion

- Generate reports

- Use AI safely

- Work offline on teacher devices

- Manage subscriptions

- Manage school settings

- Maintain strong audit trails

The product must be extremely simple.

The goal is:

"Powerful underneath, incredibly simple on the surface."

A school administrator should not need technical knowledge to use Frontline Nexus.

==================================================

2. DESIGN PHILOSOPHY

==================================================

The UI must look like a premium modern SaaS product.

Design inspiration:

- Linear

- Stripe

- Notion

- Apple

- Modern education technology products

Do NOT copy their designs.

Create an original Frontline Nexus visual identity.

The design should be:

- Clean

- Professional

- Modern

- Friendly

- Calm

- Trustworthy

- Premium

- Minimal

- Mobile-first

- Accessible

- Fast

- Easy to understand

Avoid:

- Excessive gradients

- Excessive glassmorphism

- Huge cards

- Cluttered dashboards

- Tiny text

- Excessive animations

- Too many colors

- Unnecessary popups

- Complicated navigation

- "AI-generated looking" UI

- Generic admin dashboard templates

Primary visual language:

- White

- Soft neutral backgrounds

- Professional blue

- Dark navy text

- Subtle gray borders

- Very restrained status colors

Schools must be able to upload their own logo and configure their own branding.

==================================================

3. TYPOGRAPHY AND ACCESSIBILITY

==================================================

The system is used by elderly parents, teachers, administrators and users with varying levels of technical experience.

Use:

- Minimum body font size: 16px

- Large readable headings

- Strong contrast

- Clear labels

- Large touch targets

- Comfortable spacing

- Simple language

Buttons must clearly communicate actions.

Never use an icon without a tooltip or accessible label where the meaning isn't obvious.

All forms must have:

- Clear labels

- Helpful validation

- Error messages

- Success messages

- Required field indicators

- Keyboard accessibility

- Screen-reader-friendly labels

==================================================

4. RESPONSIVE DESIGN

==================================================

The application must work beautifully on:

- Cheap Android phones

- Modern smartphones

- Tablets

- Laptops

- Desktop computers

- Large monitors

Teacher PWA must be especially optimized for low-end Android phones.

Do not simply shrink the desktop UI for mobile.

Design mobile layouts intentionally.

On mobile, use:

- Bottom navigation where appropriate

- Large buttons

- Swipe-friendly interfaces

- Simple lists

- Sticky action buttons

- Touch-friendly attendance controls

==================================================

5. TECHNOLOGY

==================================================

Use:

- React

- Vite

- TypeScript

- TailwindCSS

- React Router

- TanStack Query for server state

- React Hook Form

- Zod validation

- IndexedDB for offline teacher functionality

- PWA architecture

- Reusable component system

Use a clean architecture.

Recommended structure:

src/

app/

components/

layouts/

pages/

features/

hooks/

services/

api/

auth/

permissions/

offline/

utils/

types/

constants/

Do not put everything into one giant component.

Create reusable components.

==================================================

6. AUTHENTICATION MODEL

==================================================

There must NOT be unrestricted public registration for every user type.

Only a SCHOOL ADMINISTRATOR can create/register a new school.

The public onboarding process is:

Create School

→ School Information

→ Choose Subscription

→ Payment

→ Payment Verification

→ School Activation

→ School Setup

Teachers, cashiers, parents, students and other staff do NOT create schools.

They are created/invited by the School Administrator.

==================================================

7. USER ROLES

==================================================

The frontend must support these roles.

PLATFORM / SOFTWARE PROVIDER:

1. SuperAdmin / Platform Manager

This is the Frontline Nexus company-level administrator.

Responsibilities:

- Manage schools

- View school subscriptions

- Activate/suspend schools

- Manage subscription plans

- View platform analytics

- Manage platform configuration

- Manage support

- View billing information

- Manage system-wide AI configuration

- Manage platform users

- Monitor system health

- Review security/audit events

- Manage tenants

IMPORTANT:

Platform Manager is NOT the same as School Administrator.

---

SCHOOL LEVEL ROLES:

2. School Administrator

Full school management.

Can:

- Manage students

- Manage teachers

- Manage staff

- Manage parents

- Manage classes

- Manage subjects

- Manage academic sessions

- Manage terms

- Manage fees

- Manage payments

- Manage attendance

- Manage results

- Manage timetable

- Manage lesson plans

- Manage reports

- Manage announcements

- Manage school settings

- Manage subscription

- Bulk import students

- Bulk import staff

- Manage permissions

---

3. Principal / Head Teacher

Can:

- View school overview

- Monitor academic performance

- View attendance

- Review results

- Approve results

- Review staff activity

- View reports

- View appropriate financial summaries

- Manage announcements

- Use AI school assistant within authorized permissions

---

4. Teacher

Can:

- View assigned classes

- View assigned students

- Take attendance

- Enter assessments

- Enter results

- Create lesson plans

- View timetable

- View assigned subjects

- Use Teacher AI Assistant

- View appropriate student academic information

Teacher MUST NOT access:

- School financial records

- Payroll

- Staff salaries

- Subscription details

- School-wide financial reports

- Other restricted administrative information

---

5. Cashier / Accountant / Bursar

Can:

- View invoices

- Record payments

- Record cash payments

- Record bank transfer payments

- View outstanding balances

- Generate receipts

- Reconcile cash

- View financial reports according to permissions

Cannot manage unrelated academic administration unless explicitly authorized.

---

6. Secretary / School Staff

Permissions should be configurable.

Examples:

- Student registration

- Parent records

- Communication

- Basic school administration

---

7. Parent / Guardian

Read-focused portal.

Can:

- View linked children

- View attendance

- View results

- View report cards

- View outstanding fees

- Make payments

- Download receipts

- View announcements

- Receive notifications

- Use Parent AI Assistant for permitted information

A parent can have multiple children under one account.

---

8. Student

Can:

- View timetable

- View results

- View attendance

- View assignments

- View learning materials

- View announcements

- Use student AI assistant according to school permissions

==================================================

8. SECURITY PRINCIPLE

==================================================

IMPORTANT:

Never rely on the frontend alone for authorization.

The backend will enforce authorization.

The frontend must nevertheless implement role-based navigation and permission-aware UI.

Never show restricted information simply because a user changes a URL.

Every protected page should check:

- Authentication

- User role

- School/tenant

- Permission

Design the application around:

User

→ Tenant/School

→ Role

→ Permissions

→ Subscription

→ Feature Access

==================================================

9. MULTI-TENANT SCHOOL MODEL

==================================================

Frontline Nexus is a multi-tenant SaaS.

All schools use:

ONE FRONTEND

ONE BACKEND

But each school's data is isolated.

Example:

schoolA.frontlinenexus.com

schoolB.frontlinenexus.com

schoolC.frontlinenexus.com

The frontend must support school branding.

After login, display:

- School logo

- School name

- Current academic session

- Current term

A user must never see another school's data.

==================================================

10. SCHOOL REGISTRATION

==================================================

Create a beautiful onboarding wizard.

Step 1:

School Information

- School name

- School type

- Address

- State

- LGA

- Phone

- Email

- Logo

- Website

Step 2:

Administrator Information

- Full name

- Phone

- Email

- Password

Validate Nigerian phone numbers.

Support:

+2348012345678

08012345678

Normalize internally.

Step 3:

Choose subscription.

Show:

- Student range

- Monthly price

- AI allowance

- Included features

- Storage

- Communication allowance

Step 4:

Payment.

Step 5:

Payment verification.

Step 6:

School activated.

Step 7:

Setup wizard.

==================================================

11. SUBSCRIPTION MODEL

==================================================

The system uses student-based subscription tiers.

Example tiers:

1–100 students

101–200

201–400

401–600

601–800

801–1,000

1,001–1,500

1,501–2,000

2,000+

Do not hard-code prices into UI components.

Store plan configuration centrally so prices can be updated.

During an active billing period, schools can grow.

Allow a reasonable growth/grace allowance.

Example:

Paid level:

400 students

Growth allowance:

30 students

Warning when approaching limit.

Do NOT immediately block a school when it adds a few students above its subscription level.

At renewal, calculate the subscription tier using the school's defined billing-period enrollment rule.

The frontend should clearly display:

Current students

Subscription level

Growth allowance

Next billing date

Estimated next subscription

AI usage

Storage usage

Example:

"523 active students"

"Current tier: 401–600"

"Next renewal: ₦25,000/month"

==================================================

12. STUDENT MANAGEMENT

==================================================

Create a beautiful student management experience.

Features:

- Add student

- Edit student

- View student profile

- Student photo

- Admission number

- Student ID

- Date of birth

- Gender

- Class

- Arm

- Academic enrollment

- Parent/guardian

- Attendance

- Results

- Fees

- Payment history

- Documents

- Promotion history

Use a student profile page with clear sections.

Student profile navigation:

Overview

Academics

Attendance

Results

Fees

Guardians

Documents

History

==================================================

13. BULK IMPORT

==================================================

Bulk import must be a major feature.

Support:

- Students

- Staff

- Teachers

Workflow:

Upload Excel/CSV

→ Parse

→ Validate

→ Detect duplicates

→ Count new records

→ Check subscription capacity

→ Preview

→ Show errors

→ Confirm

→ Import

Example:

"1,250 records detected"

"1,230 valid"

"12 duplicate admission numbers"

"8 missing required fields"

If importing new students would exceed the allowed growth threshold, show:

"Your school is approaching its student capacity."

Provide:

[Review Import]

[Upgrade Subscription]

Never silently reject the file.

==================================================

14. ACADEMIC MANAGEMENT

==================================================

Create:

Academic Sessions

Terms

Classes

Arms

Subjects

Teachers

Class assignments

Support Nigerian school structures:

Nursery

Primary 1–6

JSS 1–3

SS 1–3

But make everything configurable.

Schools can create custom classes.

==================================================

15. STUDENT ENROLLMENT AND PROMOTION

==================================================

Never overwrite historical class records.

Use enrollment history.

Example:

2024/2025 → JSS1

2025/2026 → JSS2

2026/2027 → JSS3

Create Promotion Center.

At end of session:

System evaluates:

- Results

- Average score

- Failed subjects

- Attendance

- School promotion rules

Display:

Promote

Promote with Conditions

Repeat

Graduate

Withdrawn

Transferred

AI may provide recommendations, but the authorized school administrator approves the final promotion.

Create:

"Approve Promotion"

"Approve All Eligible"

"Review"

==================================================

16. ATTENDANCE

==================================================

Teacher attendance must be extremely fast.

Teacher selects:

Class

Date

Subject/period where applicable

Then displays roster:

Ahmed Present

Aisha Present

Musa Absent

Fatima Late

Use large touch-friendly buttons.

Statuses:

Present

Absent

Late

Excused

Offline support:

Attendance must work with ZERO INTERNET.

Use IndexedDB.

Store pending attendance locally.

Show:

Offline Mode

"3 attendance records waiting to sync"

When online:

"Sync Now"

Show sync progress.

Handle conflicts gracefully.

==================================================

17. TEACHER PWA

==================================================

Teacher PWA must:

- Install on Android

- Work offline

- Cache required application data

- Store attendance locally

- Store grades locally

- Queue changes

- Sync when internet returns

Create offline indicator:

ONLINE

OFFLINE

Create sync center:

Pending

Synced

Failed

Conflicts

Never lose teacher data because of temporary internet failure.

==================================================

18. RESULTS AND ASSESSMENTS

==================================================

Create configurable assessment system.

Examples:

CA 1

CA 2

CA 3

Assignment

Project

Exam

Schools configure weighting.

Example:

CA 40%

Exam 60%

System calculates totals automatically.

Teacher enters scores.

System calculates:

Total

Grade

Remark

Average

Result workflow:

Draft

Submitted

Under Review

Approved

Published

Teachers cannot publish results without appropriate permission.

==================================================

19. REPORT CARDS

==================================================

Create report-card preview UI.

Include:

School logo

Student photo

Student details

Subjects

Scores

Grades

Remarks

Attendance

Teacher comment

Principal comment

Promotion status

Buttons:

Preview

Generate PDF

Download

Print

==================================================

20. FEES AND FINANCE

==================================================

Create complete fee management.

Fee structure:

Tuition

Books

Examination

Transport

Uniform

Other fees

Allow class-specific fee structures.

Automatically generate student invoices based on enrollment/class/term.

Display:

Total

Paid

Outstanding

Payment methods:

Cash

Bank Transfer

Card

Online Payment

POS

USSD

Cash payments require authorized financial staff.

Bank transfer can be:

Manual verification

or

Automatic gateway verification

Payment statuses:

Pending

Verified

Failed

Refunded

Reversed

Cancelled

Generate receipts.

==================================================

21. PAYMENT UI

==================================================

Parent can:

View outstanding balance

Select invoice

Choose payment method

Pay

View transaction status

Download receipt

School finance staff can:

Record cash

Record manual bank transfer

Verify payment

View transaction history

Reconcile cash

Generate reports

==================================================

22. TIMETABLE

==================================================

Create timetable management.

Include:

Classes

Subjects

Teachers

Rooms

Periods

Detect conflicts:

Teacher conflict

Class conflict

Room conflict

Eventually support AI-assisted timetable generation.

==================================================

23. LESSON PLANS

==================================================

Teacher can create:

- Lesson plan manually

- Generate with AI

- Save

- Edit

- Duplicate

- Print

- Reuse

Lesson plan fields:

Subject

Class

Topic

Duration

Learning objectives

Previous knowledge

Introduction

Teacher activities

Student activities

Materials

Assessment

Homework

==================================================

24. AI SYSTEM

==================================================

AI is a major Frontline Nexus feature.

Create an AI Assistant interface.

But NEVER make AI an unrestricted chatbot.

AI must operate according to:

User

→ School

→ Role

→ Permissions

→ Available AI tools

→ Authorized data

AI examples:

Teacher AI:

- Generate lesson plan

- Generate quiz

- Explain topic

- Analyze assigned class performance

- Create teaching material

Parent AI:

- Explain child's performance

- Summarize attendance

- Explain child's results

- Answer permitted school questions

Admin AI:

- School performance analysis

- Attendance analysis

- Fee summaries

- Student performance insights

- Staff insights according to permissions

- Generate reports

Accountant AI:

- Fee summary

- Outstanding balances

- Payment analysis

- Financial reports

IMPORTANT:

A teacher must NOT be able to ask:

"Show me the school's fee collection."

and receive financial information.

AI permission must be enforced by backend authorization.

Frontend must show permission-aware AI suggestions.

==================================================

25. AI CREDITS

==================================================

Every paid school receives AI.

Do not remove AI from small schools.

AI usage can scale by subscription.

Show:

AI Credits Used

AI Credits Remaining

Example:

1,842 / 2,500 credits

Show warnings at:

80%

90%

100%

Allow:

Buy More AI Credits

Upgrade Plan

Do not hard-code credit values.

==================================================

26. AI SECURITY

==================================================

Create frontend structures for:

AI permission states

AI usage

AI tool availability

AI errors

AI denied requests

AI audit information

Never send unrestricted school data to the AI.

The backend will provide authorized context.

==================================================

27. PARENT PORTAL

==================================================

Parent dashboard must be extremely simple.

Example:

Good morning, Mr. Abubakar

Ahmed

JSS 2A

Attendance

92%

Average

72%

Outstanding fees

₦45,000

Quick actions:

View Results

View Attendance

Pay Fees

Download Report Card

Messages

If parent has multiple children:

Ahmed

Aisha

Fatima

Allow easy switching between children.

==================================================

28. TEACHER DASHBOARD

==================================================

Teacher dashboard should show only what matters.

Example:

Good morning, Teacher Ibrahim.

Today:

JSS2 Mathematics

10:00 AM

Quick actions:

Take Attendance

Enter Results

Create Lesson Plan

View Classes

AI Assistant

Show:

Pending attendance

Pending assessments

Upcoming classes

Recent notifications

==================================================

29. CASHIER/ACCOUNTANT DASHBOARD

==================================================

Show:

Today's collection

Outstanding fees

Pending payments

Cash balance

Bank transfers

Recent transactions

Quick actions:

Record Payment

Verify Transfer

Generate Receipt

View Student Balance

==================================================

30. SCHOOL ADMIN DASHBOARD

==================================================

Do NOT create a dashboard full of meaningless charts.

Create an intelligent action-oriented dashboard.

Example:

Good morning, Mrs. Aisha.

School overview:

1,245 Students

87 Teachers

92% Attendance

₦4.2m Outstanding Fees

Attention Required:

⚠ 18 students have attendance below 70%

⚠ 23 results awaiting approval

⚠ ₦4.2m outstanding fees

⚠ Subscription renewal in 7 days

Quick Actions:

Add Student

Import Students

Add Staff

Take Attendance

Record Payment

Enter Results

Create Announcement

AI Assistant

==================================================

31. PLATFORM MANAGER DASHBOARD

==================================================

This is different from School Admin.

Show:

Total schools

Active schools

Trial/pending schools

Suspended schools

Total students

Monthly recurring revenue

Subscription distribution

AI usage

System health

Recent signups

Payment activity

Support tickets

Security alerts

Platform Manager can:

Create/manage subscription plans

Manage schools

View tenant status

Manage platform configuration

Review billing

Monitor system activity

Do not expose unrelated school data by default.

==================================================

32. NOTIFICATIONS

==================================================

Create centralized notifications.

Types:

Payment

Attendance

Result

Announcement

Subscription

AI usage

Security

System

Use notification center.

Support:

Read

Unread

Mark all as read

==================================================

33. SEARCH

==================================================

Implement global search.

Search:

Students

Teachers

Parents

Classes

Invoices

Payments

Results

Documents

Use keyboard shortcut:

Ctrl/Cmd + K

On mobile, provide an obvious search button.

==================================================

34. SCHOOL BRANDING

==================================================

Each school can upload:

Logo

School name

Primary branding color

Secondary branding color

Frontend should automatically apply branding carefully without breaking accessibility.

==================================================

35. SETTINGS

==================================================

School Settings:

School Profile

Academic Sessions

Terms

Classes

Subjects

Grading

Promotion Rules

Fee Structure

Attendance Rules

Staff

Roles & Permissions

Notifications

Branding

Subscription

AI Usage

Security

==================================================

36. SECURITY UI

==================================================

Create:

Security settings

Active sessions

Login history

Password change

Two-factor authentication placeholder

Audit logs for authorized administrators

Sensitive actions should require confirmation.

Examples:

Delete student

Change subscription

Publish results

Approve payments

Promote students

Suspend account

Use confirmation dialogs with clear consequences.

==================================================

37. EMPTY STATES

==================================================

Never show blank pages.

Examples:

"No students yet."

"Import your existing student list to get started."

Button:

[ Import Students ]

For attendance:

"No attendance recorded today."

[ Take Attendance ]

For payments:

"No payments recorded yet."

[ Record Payment ]

==================================================

38. ERROR STATES

==================================================

Errors must be friendly.

Never show raw technical errors such as:

500 Internal Server Error

Instead:

"Something went wrong while loading this information. Please try again."

Provide:

[ Retry ]

If offline:

"You're offline. Your changes will be saved and synchronized when internet access returns."

==================================================

39. LOADING STATES

==================================================

Use skeleton loaders.

Avoid unnecessary spinners.

For long operations show progress.

Example:

Importing students...

Step 2 of 4

Validating records...

==================================================

40. FORMS

==================================================

All forms must be carefully validated.

Nigerian phone number validation is mandatory.

Support:

+234...

080...

Normalize internally.

Validate:

- Email

- Phone

- Required fields

- Numbers

- Dates

- Scores

- Fees

- Student IDs

- Admission numbers

==================================================

41. DATA TABLES

==================================================

Tables must support:

Search

Filter

Sort

Pagination

Column selection where appropriate

Export

Mobile-friendly card view

Don't force huge desktop tables onto mobile.

==================================================

42. DESIGN SYSTEM

==================================================

Create reusable:

Button

Input

Select

DatePicker

Modal

Drawer

Card

Badge

Alert

Toast

Tabs

Table

Pagination

Dropdown

Avatar

Breadcrumb

Sidebar

Bottom navigation

Skeleton

Empty state

Confirmation dialog

File uploader

Progress indicator

Maintain consistent spacing and typography.

==================================================

43. SIDEBAR

==================================================

Desktop sidebar should be simple.

School Admin:

Dashboard

Students

Academics

Attendance

Results

Finance

Timetable

Lesson Plans

Communication

AI Assistant

Reports

Subscription

Settings

Group navigation logically.

Don't overwhelm the user.

Teacher:

Dashboard

My Classes

Attendance

Results

Lesson Plans

Timetable

AI Assistant

Notifications

Parent:

Home

My Children

Attendance

Results

Fees

Messages

AI Assistant

Profile

Accountant:

Dashboard

Students

Invoices

Payments

Reports

AI Assistant

Profile

Platform Manager:

Dashboard

Schools

Subscriptions

Users

AI

Analytics

Security

Support

Settings

==================================================

44. OFFLINE EXPERIENCE

==================================================

Teacher PWA should clearly communicate:

Online

Offline

Syncing

Synced

Sync Failed

Create Sync Center.

Example:

"5 changes waiting to sync"

[ Sync Now ]

After synchronization:

"All changes synchronized."

==================================================

45. PERFORMANCE

==================================================

The application should be optimized for Nigerian internet conditions.

Assume some users have:

- Slow 3G

- Unstable 4G

- Low-end Android devices

- Limited data

Therefore:

- Lazy load routes

- Optimize images

- Compress assets

- Minimize bundle size

- Cache intelligently

- Avoid unnecessary API calls

- Use pagination

- Use optimistic UI where safe

- Use IndexedDB for offline functionality

==================================================

46. MULTI-SCHOOL DOMAIN

==================================================

Support tenant-aware routing.

Example:

schoolname.frontlinenexus.com

or:

app.frontlinenexus.com/school/schoolname

Design the frontend so the backend can determine the school/tenant securely.

Never trust a user-provided school ID from the browser as authorization.

==================================================

47. BILLING EXPERIENCE

==================================================

Create a beautiful subscription page.

Show:

Current plan

Current student count

Growth allowance

AI usage

Storage

Billing date

Payment method

Next estimated bill

Example:

Current students:

523

Current tier:

401–600

Next renewal:

₦25,000

Renewal date:

September 1

AI usage:

1,842 / 2,500

Buttons:

Manage Subscription

Upgrade

Buy AI Credits

View Billing History

==================================================

48. ONBOARDING CHECKLIST

==================================================

After school activation show:

Complete your school setup

✓ School profile

✓ Academic session

○ Add classes

○ Add subjects

○ Import students

○ Import staff

○ Configure fees

○ Configure grading

Progress:

4 / 7 complete

This should disappear once setup is completed.

==================================================

49. USER EXPERIENCE RULE

==================================================

Every feature must answer:

"What does the user want to accomplish?"

Not:

"What database module are we displaying?"

Examples:

Instead of:

"Student CRUD"

Design:

"Add Student"

"Import Students"

"Find Student"

"View Student"

Instead of:

"Payment Management"

Design:

"Record Payment"

"Verify Transfer"

"View Outstanding Fees"

Instead of:

"Attendance Module"

Design:

"Take Attendance"

"View Attendance"

==================================================

50. IMPORTANT BUSINESS LOGIC UI

==================================================

Student limit:

- Warn before limit

- Show current usage

- Show growth allowance

- Show estimated next tier

- Provide upgrade option

Subscription:

- Payment required before school activation

- Show pending payment state

- Show active state

- Show grace period

- Show renewal

- Show suspended state

Do not hard-code business rules that belong to the backend.

Frontend should consume backend subscription status and permissions.

==================================================

51. DO NOT CREATE FAKE SECURITY

==================================================

Never implement security only visually.

The frontend should assume:

Backend controls:

- Authentication

- Authorization

- Tenant isolation

- Subscription enforcement

- AI permissions

- Payment verification

- Student limits

- Role permissions

Frontend reflects backend state.

==================================================

52. AUTHENTICATION SCREENS

==================================================

Create polished screens for:

School Administrator Registration

Login

Forgot Password

Reset Password

Change Password

Invite Activation

Account Activation

Session Expired

Unauthorized

School Suspended

Subscription Required

Payment Pending

Login should be extremely simple.

Example:

FRONTLINE NEXUS

Welcome back

Email or phone

Password

[ Sign In ]

Forgot password?

Don't have a school yet?

Create your school

Do NOT provide:

"Sign up as teacher"

"Sign up as parent"

"Sign up as student"

Those users are invited/created by their school.

==================================================

53. FINAL QUALITY REQUIREMENTS

==================================================

Before considering the frontend complete, check:

- Every navigation link works

- No dead buttons

- No broken routes

- No fake dropdowns

- Forms validate

- Modals work

- Search works

- Filters work

- Pagination works

- Responsive layouts work

- Mobile layouts work

- Loading states exist

- Empty states exist

- Error states exist

- Offline states exist

- Permission-aware UI exists

- Subscription states exist

- Student limit warnings exist

- AI usage states exist

- Authentication states exist

Do not leave placeholder text like:

"Coming soon"

unless the feature genuinely depends on a backend service that hasn't been implemented yet.

If backend functionality is unavailable, create a clean API service abstraction and mock adapter that can be replaced without rewriting the UI.

==================================================

54. MOST IMPORTANT REQUIREMENT

==================================================

Do not build the entire system as one giant dashboard.

Build a coherent product.

The experience should feel like:

"One simple school operating system."

Every role should see only what matters to them.

The School Administrator should feel:

"I can run my entire school from here."

The Teacher should feel:

"I can do my daily work quickly."

The Accountant should feel:

"I can manage school finances safely."

The Parent should feel:

"I can understand my child's school life without confusion."

The Student should feel:

"I can easily access what I need."

The Frontline Nexus Platform Manager should feel:

"I can safely operate thousands of schools from one platform."

==================================================

55. BUILD ORDER

==================================================

Build in this order:

PHASE 1

Design system

Authentication

Layouts

Role system

Navigation

School onboarding

PHASE 2

School dashboard

Student management

Bulk import

Staff management

Parent management

PHASE 3

Academic management

Classes

Subjects

Sessions

Terms

Enrollment

Promotion

PHASE 4

Teacher PWA

Attendance

Offline IndexedDB

Sync center

PHASE 5

Assessments

Results

Report cards

PHASE 6

Fees

Invoices

Payments

Receipts

Billing

PHASE 7

Timetable

Lesson plans

Communication

PHASE 8

AI assistant

AI credits

Role-based AI tools

AI permission UI

PHASE 9

Parent portal

Student portal

PHASE 10

Platform Manager

Subscriptions

Analytics

Security

Audit

==================================================

56. FINAL DESIGN REQUIREMENT

==================================================

Make Frontline Nexus visually impressive enough that when a school owner sees it for the first time, they immediately feel:

"This is professional."

But keep it simple enough that someone who is not technologically experienced can operate it without training.

The product must look premium without becoming complicated.

Prioritize:

CLARITY

SIMPLICITY

TRUST

SECURITY

SPEED

ACCESSIBILITY

PROFESSIONALISM

SCALABILITY

AI-POWERED AUTOMATION

Build the frontend as a serious production SaaS application, not a school-management template.

This project was built with [Lovable](https://lovable.dev).

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/0e537582-ac21-4bf0-b542-bbc12a210ea1).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
