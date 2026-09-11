import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
  Scripts,
} from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";

import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";
import { SessionProvider } from "@/auth/session";
import { Button } from "@/components/ui/button";
import { Toaster } from "@/components/ui/sonner";

function NotFoundComponent() {
  return (
    <div className="fn-grid-bg flex min-h-screen items-center justify-center px-4">
      <div className="fn-panel w-full max-w-md p-8 text-center sm:p-10">
        <p className="font-display text-7xl font-semibold tracking-[-0.03em] text-primary">404</p>
        <h1 className="mt-4 font-display text-xl font-semibold">Page not found</h1>
        <p className="mt-2 text-muted-foreground">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="mt-6">
          <Button asChild size="lg" className="w-full">
            <Link to="/">Go home</Link>
          </Button>
        </div>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  console.error(error);
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);

  return (
    <div className="fn-grid-bg flex min-h-screen items-center justify-center px-4">
      <div className="fn-panel w-full max-w-md p-8 text-center sm:p-10">
        <h1 className="font-display text-xl font-semibold tracking-[-0.02em]">
          This page didn't load
        </h1>
        <p className="mt-2 text-muted-foreground">
          Something went wrong while loading this information. Please try again.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <Button
            className="flex-1"
            size="lg"
            onClick={() => {
              router.invalidate();
              reset();
            }}
          >
            Retry
          </Button>
          <Button asChild variant="outline" size="lg" className="flex-1">
            <a href="/">Go home</a>
          </Button>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "Frontline Nexus — School Management System" },
      {
        name: "description",
        content:
          "Frontline Nexus is a secure, AI-powered school management system for primary and secondary schools in Nigeria and West Africa.",
      },
      {
        name: "description",
        content:
          "Frontline Nexus is a secure, AI-powered school management system for primary and secondary schools in Nigeria and West Africa.",
      },
      { name: "author", content: "Frontline Nexus" },
      { property: "og:site_name", content: "Frontline Nexus" },
      { property: "og:type", content: "website" },
      { property: "og:title", content: "Frontline Nexus — School Management System" },
      { property: "og:description", content: "We develop. We secure. We connect." },
      { property: "og:url", content: "https://frontlinenexus.com/" },
      { property: "og:image", content: "https://frontlinenexus.com/icons/icon-512.png" },
      { name: "twitter:card", content: "summary_large_image" },
      { name: "twitter:title", content: "Frontline Nexus — School Management System" },
      { name: "twitter:description", content: "We develop. We secure. We connect." },
      { name: "theme-color", content: "#2563eb" },
      { name: "apple-mobile-web-app-capable", content: "yes" },
      { name: "apple-mobile-web-app-status-bar-style", content: "default" },
      { name: "mobile-web-app-capable", content: "yes" },
    ],
    links: [
      { rel: "manifest", href: "/manifest.webmanifest" },
      { rel: "preconnect", href: "https://fonts.googleapis.com" },
      { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=DM+Sans:wght@500;600;700&display=swap",
      },
      { rel: "stylesheet", href: appCss },
      { rel: "icon", href: "/favicon.ico", type: "image/x-icon" },
      { rel: "icon", href: "/icons/icon.svg", type: "image/svg+xml" },
      { rel: "apple-touch-icon", href: "/icons/apple-touch-icon.png" },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();

  useEffect(() => {
    if (!import.meta.env.PROD) return;
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        {/* Required: nested routes render here. Removing <Outlet /> breaks all child routes. */}
        <Outlet />
        <Toaster position="top-center" richColors />
      </SessionProvider>
    </QueryClientProvider>
  );
}
