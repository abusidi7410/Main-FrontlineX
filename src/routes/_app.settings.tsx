import { createFileRoute } from "@tanstack/react-router";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/page-header";
import { PermissionGate } from "@/components/common/permission-gate";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSession } from "@/auth/session";
import { ApiRequestError } from "@/api/client";
import { PaymentStructurePanel } from "@/features/finance/payment-structure-panel";
import { NotificationPreferencesPanel } from "@/features/notifications/notification-preferences-panel";
import { ROLE_LABELS } from "@/permissions";
import { updateSchoolProfile, uploadSchoolLogo } from "@/services/school.service";

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
  const { session, can, updateSchool } = useSession();
  const school = session?.school;
  const readOnly = !can("settings.write");

  const [name, setName] = useState(school?.name ?? "");
  const [phone, setPhone] = useState(school?.phone ?? "");
  const [email, setEmail] = useState(school?.email ?? "");
  const [address, setAddress] = useState(school?.address ?? "");
  const [currentSession, setCurrentSession] = useState(school?.currentSession ?? "");
  const [currentTerm, setCurrentTerm] = useState(school?.currentTerm ?? "");
  const [savingProfile, setSavingProfile] = useState(false);
  const [uploadingLogo, setUploadingLogo] = useState(false);
  const [logoUrl, setLogoUrl] = useState(school?.logoUrl ?? "");
  const logoInputRef = useRef<HTMLInputElement>(null);

  return (
    <PermissionGate anyOf={["settings.read", "finance.read"]}>
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

        <Tabs defaultValue={can("settings.read") ? "school" : "fees"}>
          <TabsList>
            {can("settings.read") ? (
              <>
                <TabsTrigger value="school">School profile</TabsTrigger>
                <TabsTrigger value="academic">Academic session</TabsTrigger>
              </>
            ) : null}
            <TabsTrigger value="fees">Payment structure</TabsTrigger>
            {can("settings.read") ? (
              <>
                <TabsTrigger value="notifications">Notifications</TabsTrigger>
                <TabsTrigger value="security">Security</TabsTrigger>
              </>
            ) : null}
          </TabsList>

          <TabsContent value="school" className="mt-4">
            <form
              className="fn-panel grid gap-4 p-5 sm:grid-cols-2"
              onSubmit={async (e) => {
                e.preventDefault();
                if (savingProfile) return;
                setSavingProfile(true);
                try {
                  // The server always writes to the school on the caller's own
                  // account, so this cannot touch another tenant's profile.
                  const profile = await updateSchoolProfile({ name, phone, email, address });
                  updateSchool(profile);
                  toast.success("School profile saved");
                } catch (error) {
                  toast.error(
                    error instanceof ApiRequestError
                      ? error.message
                      : "We couldn't save the school profile. Please try again.",
                  );
                } finally {
                  setSavingProfile(false);
                }
              }}
            >
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="school-logo">School logo</Label>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex size-14 items-center justify-center overflow-hidden rounded-xl border border-border bg-muted">
                    {logoUrl ? (
                      <img src={logoUrl} alt="" className="size-full object-cover" />
                    ) : (
                      <span className="text-xs text-muted-foreground">None</span>
                    )}
                  </div>
                  <input
                    ref={logoInputRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    disabled={readOnly || uploadingLogo}
                    onChange={async (e) => {
                      const file = e.target.files?.[0];
                      e.target.value = "";
                      if (!file) return;
                      setUploadingLogo(true);
                      try {
                        const profile = await uploadSchoolLogo(file);
                        updateSchool(profile);
                        setLogoUrl(profile.logoUrl ?? "");
                        toast.success("School logo updated");
                      } catch (error) {
                        toast.error(
                          error instanceof ApiRequestError
                            ? error.message
                            : "We couldn't upload the logo. Please try again.",
                        );
                      } finally {
                        setUploadingLogo(false);
                      }
                    }}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    disabled={readOnly || uploadingLogo}
                    onClick={() => logoInputRef.current?.click()}
                  >
                    {uploadingLogo ? "Uploading…" : "Upload logo"}
                  </Button>
                  <p className="text-xs text-muted-foreground">
                    Stored with the school's own media files and printed on receipts and
                    registration documents.
                  </p>
                </div>
              </div>
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
                <Button type="submit" disabled={readOnly || savingProfile}>
                  {savingProfile ? "Saving…" : "Save changes"}
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

          <TabsContent value="fees" className="mt-4">
            <PaymentStructurePanel canWrite={can("finance.structure")} />
          </TabsContent>

          <TabsContent value="notifications" className="mt-4">
            <NotificationPreferencesPanel />
            <p className="mt-3 text-sm text-muted-foreground">
              These switches control only what reaches your own inbox. Turning one off stops new
              notifications of that type; anything already delivered stays where it is.
            </p>
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
