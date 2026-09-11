import { useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Button } from "@/components/ui/button";
import { useSession } from "@/auth/session";
import { NAV_BY_ROLE } from "@/permissions/navigation";
import { listStudents } from "@/services/students.service";
import type { Student } from "@/types";

export function GlobalSearch() {
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const [students, setStudents] = useState<Student[]>([]);
  const navigate = useNavigate();
  const { role } = useSession();
  const navItems = useMemo(() => (role ? NAV_BY_ROLE[role] : []), [role]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!open || term.trim().length < 2) {
      setStudents([]);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      void listStudents({ search: term, pageSize: 6 }).then((page) => {
        if (!cancelled) setStudents(page.results);
      });
    }, 220);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [open, term]);

  return (
    <>
      <Button
        variant="outline"
        onClick={() => setOpen(true)}
        className="h-10 justify-start gap-2 text-muted-foreground md:w-64"
        aria-label="Search students, pages and records"
      >
        <Search className="size-4" aria-hidden="true" />
        <span className="hidden md:inline">Search…</span>
        <kbd className="ml-auto hidden rounded border bg-muted px-1.5 text-xs md:inline">⌘K</kbd>
      </Button>

      <CommandDialog open={open} onOpenChange={setOpen}>
        <CommandInput placeholder="Search students, pages…" value={term} onValueChange={setTerm} />
        <CommandList>
          <CommandEmpty>No matches. Try a student name or admission number.</CommandEmpty>
          {students.length > 0 ? (
            <CommandGroup heading="Students">
              {students.map((student) => (
                <CommandItem
                  key={student.id}
                  value={`${student.firstName} ${student.lastName} ${student.admissionNumber}`}
                  onSelect={() => {
                    setOpen(false);
                    void navigate({ to: `/students/${student.id}` });
                  }}
                >
                  {student.firstName} {student.lastName}
                  <span className="ml-auto text-xs text-muted-foreground">
                    {student.className}
                    {student.arm} · {student.admissionNumber}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          ) : null}
          <CommandGroup heading="Go to">
            {navItems.map((item) => (
              <CommandItem
                key={item.to}
                value={item.label}
                onSelect={() => {
                  setOpen(false);
                  void navigate({ to: item.to });
                }}
              >
                {item.label}
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </>
  );
}
