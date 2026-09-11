import { createFileRoute, Link } from "@tanstack/react-router";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import {
  ArrowLeftRight,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Upload,
  UserCheck,
  UserMinus,
} from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { IfAllowed } from "@/components/common/permission-gate";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { CLASSES } from "@/api/mock";
import { naira, numberFmt, percent } from "@/lib/format";
import { cn } from "@/lib/utils";
import { listStudents, reinstateStudent, suspendStudent } from "@/services/students.service";
import { useDebounced } from "@/hooks/use-debounced";
import { TransferStudentDialog } from "@/features/students/transfer-student-dialog";
import type { Student } from "@/types";

export const Route = createFileRoute("/_app/students/")({
  head: () => ({
    meta: [
      { title: "Students — Frontline Nexus" },
      {
        name: "description",
        content: "Search, filter and manage every student record in your school.",
      },
      { property: "og:title", content: "Students — Frontline Nexus" },
      {
        property: "og:description",
        content: "Search, filter and manage every student record in your school.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: StudentsPage,
});

const PAGE_SIZE = 10;

function initialsOf(name: string) {
  return name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function StudentsPage() {
  const [search, setSearch] = useState("");
  const [className, setClassName] = useState("all");
  const [status, setStatus] = useState("active");
  const [page, setPage] = useState(1);
  const [transferTarget, setTransferTarget] = useState<Student | null>(null);
  const debounced = useDebounced(search, 300);
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["students", { debounced, className, status, page }],
    queryFn: () =>
      listStudents({
        search: debounced,
        className: className === "all" ? "" : className,
        status: status === "all" ? "" : status,
        page,
        pageSize: PAGE_SIZE,
      }),
    placeholderData: keepPreviousData,
  });

  const invalidateStudents = () => queryClient.invalidateQueries({ queryKey: ["students"] });

  const suspend = useMutation({
    mutationFn: suspendStudent,
    onSuccess: (student) => {
      toast.success(`${student.firstName} ${student.lastName} has been suspended.`);
      void invalidateStudents();
    },
    onError: () => toast.error("We couldn't suspend this student. Please try again."),
  });

  const reinstate = useMutation({
    mutationFn: reinstateStudent,
    onSuccess: (student) => {
      toast.success(`${student.firstName} ${student.lastName} is active again.`);
      void invalidateStudents();
    },
    onError: () => toast.error("We couldn't reinstate this student. Please try again."),
  });

  const totalPages = query.data ? Math.max(1, Math.ceil(query.data.count / PAGE_SIZE)) : 1;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Students"
        description="Every learner in your school, with attendance, performance and fee status at a glance."
        actions={
          <IfAllowed permission="students.write">
            <Button asChild variant="outline" className="h-11">
              <Link to="/students/import">
                <Upload className="size-4" aria-hidden="true" /> Import
              </Link>
            </Button>
            <Button asChild className="h-11">
              <Link to="/students/new">
                <Plus className="size-4" aria-hidden="true" /> Add student
              </Link>
            </Button>
          </IfAllowed>
        }
      />

      <div className="fn-panel flex flex-col gap-3 p-4 sm:flex-row">
        <div className="relative flex-1">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            className="h-11 pl-9"
            placeholder="Search by name, admission number or guardian"
            aria-label="Search students"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
          />
        </div>
        <Select
          value={className}
          onValueChange={(value) => {
            setClassName(value);
            setPage(1);
          }}
        >
          <SelectTrigger className="h-11 sm:w-40" aria-label="Filter by class">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All classes</SelectItem>
            {CLASSES.map((option) => (
              <SelectItem key={option} value={option}>
                {option}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={status}
          onValueChange={(value) => {
            setStatus(value);
            setPage(1);
          }}
        >
          <SelectTrigger className="h-11 sm:w-40" aria-label="Filter by status">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="suspended">Suspended</SelectItem>
            <SelectItem value="graduated">Graduated</SelectItem>
            <SelectItem value="withdrawn">Withdrawn</SelectItem>
            <SelectItem value="transferred">Transferred</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {query.isError ? (
        <ErrorState onRetry={() => void query.refetch()} />
      ) : query.isPending ? (
        <ListSkeleton />
      ) : query.data.results.length === 0 ? (
        <EmptyState
          title="No students match your filters"
          description="Try a different name or class, or clear your filters to see the full roster."
          action={
            <Button
              variant="outline"
              onClick={() => {
                setSearch("");
                setClassName("all");
                setStatus("active");
              }}
            >
              Clear filters
            </Button>
          }
        />
      ) : (
        <>
          <div className="fn-panel overflow-x-auto">
            <table className="w-full min-w-[52rem] text-left">
              <caption className="sr-only">Student roster</caption>
              <thead className="border-b bg-muted/40 text-sm text-muted-foreground">
                <tr>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Student
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Class
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Attendance
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Average
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Fees owed
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Status
                  </th>
                  <th scope="col" className="px-4 py-3 text-right font-medium">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {query.data.results.map((student) => (
                  <tr key={student.id} className="hover:bg-muted/40">
                    <td className="px-4 py-3">
                      <Link
                        to="/students/$studentId"
                        params={{ studentId: student.id }}
                        className="group flex items-center gap-3"
                      >
                        <Avatar className="size-9 shrink-0">
                          <AvatarFallback className="bg-primary/10 text-xs font-semibold text-primary">
                            {initialsOf(`${student.firstName} ${student.lastName}`)}
                          </AvatarFallback>
                        </Avatar>
                        <span className="min-w-0">
                          <span className="block truncate font-medium text-primary group-hover:underline">
                            {student.firstName} {student.lastName}
                          </span>
                          <span className="block text-sm text-muted-foreground">
                            {student.admissionNumber}
                          </span>
                        </span>
                      </Link>
                    </td>
                    <td className="px-4 py-3 font-medium">
                      {student.className}
                      {student.arm}
                    </td>
                    <td
                      className={cn(
                        "px-4 py-3 tabular-nums",
                        student.attendanceRate >= 75 ? "text-success" : "text-warning",
                      )}
                    >
                      {percent(student.attendanceRate)}
                    </td>
                    <td className="px-4 py-3 tabular-nums">{percent(student.average)}</td>
                    <td
                      className={cn(
                        "px-4 py-3 tabular-nums",
                        student.outstandingFees > 0 ? "text-warning" : "text-muted-foreground",
                      )}
                    >
                      {naira(student.outstandingFees)}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={student.status} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <IfAllowed permission="students.write">
                        <StudentRowActions
                          student={student}
                          busy={
                            (suspend.isPending && suspend.variables === student.id) ||
                            (reinstate.isPending && reinstate.variables === student.id)
                          }
                          onSuspend={() => suspend.mutate(student.id)}
                          onReinstate={() => reinstate.mutate(student.id)}
                          onTransfer={() => setTransferTarget(student)}
                        />
                      </IfAllowed>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              Showing {query.data.results.length} of {numberFmt(query.data.count)} students
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                className="h-11"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </Button>
              <span className="text-sm text-muted-foreground">
                Page {page} of {totalPages}
              </span>
              <Button
                variant="outline"
                className="h-11"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}

      <TransferStudentDialog
        studentId={transferTarget?.id ?? ""}
        studentName={transferTarget ? `${transferTarget.firstName} ${transferTarget.lastName}` : ""}
        open={transferTarget !== null}
        onOpenChange={(open) => {
          if (!open) setTransferTarget(null);
        }}
      />
    </div>
  );
}

function StudentRowActions({
  student,
  busy,
  onSuspend,
  onReinstate,
  onTransfer,
}: {
  student: Student;
  busy: boolean;
  onSuspend: () => void;
  onReinstate: () => void;
  onTransfer: () => void;
}) {
  return (
    <div className="flex items-center justify-end">
      <DropdownMenu>
        <DropdownMenuTrigger asChild disabled={busy}>
          <Button
            variant="ghost"
            size="icon"
            aria-label={`More actions for ${student.firstName} ${student.lastName}`}
            disabled={busy}
          >
            <MoreHorizontal aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-44">
          <DropdownMenuLabel>
            {student.firstName} {student.lastName}
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            disabled={busy}
            onClick={() => (student.status === "suspended" ? onReinstate() : onSuspend())}
          >
            {student.status === "suspended" ? (
              <UserCheck aria-hidden="true" />
            ) : (
              <UserMinus aria-hidden="true" />
            )}
            {student.status === "suspended" ? "Reinstate" : "Suspend"}
          </DropdownMenuItem>
          {student.status === "active" ? (
            <DropdownMenuItem onClick={onTransfer}>
              <ArrowLeftRight aria-hidden="true" /> Transfer
            </DropdownMenuItem>
          ) : null}
          <DropdownMenuItem asChild>
            <Link to="/students/$studentId/edit" params={{ studentId: student.id }}>
              <Pencil aria-hidden="true" /> Edit details
            </Link>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
