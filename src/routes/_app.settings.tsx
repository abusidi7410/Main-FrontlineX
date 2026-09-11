import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSession } from "@/auth/session";
import { ROLE_LABELS } from "@/permissions";

export const Route = createFileRoute("/_app/settings")({
  head: () => ({
    meta: [
      { title: "Settings — Frontline Nexus" },
      {
        name: "description",
        content: "School profile, academic session, notification and security settings.",
      },
      { property: "og:title", content: "Settings — Frontline Nexus" },
      {
        property: "og:description",
        content: "School profile, academic session, notification and security settings.",
      },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: SettingsPage,
});

function SettingsPage() {
  const { session, can } = useSession();
  const school = session?.school;
  const readOnly = !can("settings.write");

  const [name, setName] = useState(school?.name ?? "");
  const [phone, setPhone] = useState(school?.phone ?? "");
  const [email, setEmail] = useState(school?.email ?? "");
  const [address, setAddress] = useState(school?.address ?? "");
  const [currentSession, setCurrentSession] = useState(school?.currentSession ?? "");
  const [currentTerm, setCurrentTerm] = useState(school?.currentTerm ?? "");
  const [notify, setNotify] = useState({
    payments: true,
    attendance: true,
    results: true,
    digest: false,
  });

  return (
    <PermissionGate permission="settings.read">
      <div className="space-y-6">
        <PageHeader
          title="Settings"
          description="Update your school details, academic calendar and how Frontline Nexus notifies your team."
        />

        {readOnly ? (
          <p
            className="rounded-xl border border-info/30 bg-info-soft px-4 py-3 text-sm"
            role="status"
          >
            You can view these settings but only a school administrator can change them.
          </p>
        ) : null}

        <Tabs defaultValue="school">
          <TabsList>
            <TabsTrigger value="school">School profile</TabsTrigger>
            <TabsTrigger value="academic">Academic session</TabsTrigger>
            <TabsTrigger value="notifications">Notifications</TabsTrigger>
            <TabsTrigger value="security">Security</TabsTrigger>
          </TabsList>

          <TabsContent value="school" className="mt-4">
            <form
              className="fn-panel grid gap-4 p-5 sm:grid-cols-2"
              onSubmit={(e) => {
                e.preventDefault();
                toast.success("School profile saved");
              }}
            >
              <div className="space-y-2">
                <Label htmlFor="school-name">School name</Label>
                <Input
                  id="school-name"
                  className="h-11"
                  value={name}
                  disabled={readOnly}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="school-phone">Phone number</Label>
                <Input
                  id="school-phone"
                  className="h-11"
                  inputMode="tel"
                  value={phone}
                  disabled={readOnly}
                  onChange={(e) => setPhone(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="school-email">Email address</Label>
                <Input
                  id="school-email"
                  className="h-11"
                  type="email"
                  value={email}
                  disabled={readOnly}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="school-address">Address</Label>
                <Input
                  id="school-address"
                  className="h-11"
                  value={address}
                  disabled={readOnly}
                  onChange={(e) => setAddress(e.target.value)}
                />
              </div>
              <div className="sm:col-span-2">
                <Button type="submit" disabled={readOnly}>
                  Save changes
                </Button>
              </div>
            </form>
          </TabsContent>

          <TabsContent value="academic" className="mt-4">
            <form
              className="fn-panel grid gap-4 p-5 sm:grid-cols-2"
              onSubmit={(e) => {
                e.preventDefault();
                toast.success("Academic session updated");
              }}
            >
              <div className="space-y-2">
                <Label htmlFor="session">Current session</Label>
                <Input
                  id="session"
                  className="h-11"
                  value={currentSession}
                  disabled={readOnly}
                  onChange={(e) => setCurrentSession(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="term">Current term</Label>
                <Input
                  id="term"
                  className="h-11"
                  value={currentTerm}
                  disabled={readOnly}
                  onChange={(e) => setCurrentTerm(e.target.value)}
                />
              </div>
              <p className="text-sm text-muted-foreground sm:col-span-2">
                Changing the term moves attendance, results and invoices to a new reporting period.
                Previous terms stay available in reports.
              </p>
              <div className="sm:col-span-2">
                <Button type="submit" disabled={readOnly}>
                  Save changes
                </Button>
              </div>
            </form>
          </TabsContent>

          <TabsContent value="notifications" className="mt-4">
            <div className="fn-panel divide-y p-0">
              {(
                [
                  [
                    "payments",
                    "Fee payments",
                    "Alert me when a payment is recorded or needs verification.",
                  ],
                  [
                    "attendance",
                    "Attendance gaps",
                    "Alert me when a class register isn't submitted by 10am.",
                  ],
                  [
                    "results",
                    "Result approvals",
                    "Alert me when result sheets are submitted for review.",
                  ],
                  [
                    "digest",
                    "Weekly digest",
                    "Email me a summary of school activity every Monday.",
                  ],
                ] as const
              ).map(([key, title, description]) => (
                <div key={key} className="flex items-center justify-between gap-4 p-5">
                  <div className="min-w-0">
                    <Label htmlFor={`notify-${key}`} className="font-medium">
                      {title}
                    </Label>
                    <p className="text-sm text-muted-foreground">{description}</p>
                  </div>
                  <Switch
                    id={`notify-${key}`}
                    checked={notify[key]}
                    onCheckedChange={(checked) => {
                      setNotify((prev) => ({ ...prev, [key]: checked }));
                      toast.success(`${title} notifications ${checked ? "enabled" : "disabled"}`);
                    }}
                  />
                </div>
              ))}
            </div>
          </TabsContent>

          <TabsContent value="security" className="mt-4">
            <div className="fn-panel space-y-4 p-5">
              <div>
                <h2 className="font-medium">Your access</h2>
                <p className="text-sm text-muted-foreground">
                  Signed in as {session?.user.fullName} ·{" "}
                  {session ? ROLE_LABELS[session.user.role] : "—"}
                </p>
              </div>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li>Sessions expire after 12 hours of inactivity on shared devices.</li>
                <li>
                  Every result approval, payment verification and export is written to the audit
                  trail.
                </li>
                <li>Teacher devices keep offline records encrypted on-device until they sync.</li>
              </ul>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  onClick={() => toast.success("Password reset link sent to your email")}
                >
                  Change password
                </Button>
                <Button
                  variant="outline"
                  onClick={() => toast.success("Signed out of all other devices")}
                >
                  Sign out other devices
                </Button>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </PermissionGate>
  );
}
